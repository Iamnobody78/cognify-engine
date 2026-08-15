#!/usr/bin/env python3
"""
vision_proxy.py — A1: codex-vision-proxy 轻量本地等价物 (DeepSeek 视觉桥)
=======================================================================
PM ROUND 11 Phase A1 交付物。让纯文本主模型 (DeepSeek v4-pro) 通过 Ollama VL
后端获得"看图"能力, 采用"原生协议优先, 视觉兜底"原则 (G3CA v1.1 / arXiv:2608.03327)。

协议: EVAI-V1R Recognize 阶段服务端 | 签名: EVAI-V1R/A1
设计约束 (PM 裁决):
  1. 视觉调用按需触发 (auto 模式): 仅当工具失败 (MCP element_not_found) 时调用
  2. 输出结构化 JSON: objects / coordinates / confidence / anomaly
  3. 端点为本地 HTTP 服务, 供 outer_loop.py / MCP 工具链调用

降级链 (TASK-006, PM 裁决 2 2026-08-06): qwen2.5vl:7b 主用 (过门控 3/3, 热 74-84s)
           -> qwen2.5vl:3b 快速 fallback (隔离热 25.3s, class 合并封顶 0.35 仅离线信号)
           -> LLaVA-NeXT -> Florence-2-base。CPU 实测 (2026-08-06, frame_0000.png):
           7b 冷 218.2s / 热 74-84s (3/3 过 0.6 门控, confidence=0.65)
           | 3b 冷 225.3s / 热 25.3s (0/3 过门控, class 合并封顶 0.35)
           瓶颈 = 视觉编码器 + 模型加载; 7b 默认 + 超时 120s 降级 3b (FALLBACK_TRIGGERED)
           + keep_alive 30m 驻留 + 启动预热。

用法:
  python3 scripts/vision_proxy.py [--port 8766] [--model qwen2.5vl:7b]
端:
  GET  /health      -> {"status":"ready","model":...,"backend":"ollama","gpu":false}
  POST /insight     -> 接收 {"image": base64 或路径}, 返回 VL 洞察 JSON
  POST /ground      -> 接收 {"image":..., "query":"机器人"}, 返回像素坐标
"""

import argparse
import base64
import json
import os
import sys
import time
import threading
import asyncio
import urllib.request
import tempfile

# ---------- Ollama 客户端 ----------
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")

# TASK-006 (PM 2026-08-06 裁决 2): 7b 主用 + 3b 快速 fallback
# - 7b: 过门控 3/3 唯一实时通路, 热推理 74-84s
# - 3b: class 合并 0.35 封顶被门控拦截, 仅保留快速回退 (隔离热推理 25.3s)
DEFAULT_MODEL = "qwen2.5vl:7b"
FALLBACK_MODEL = "qwen2.5vl:3b"
PRIMARY_TIMEOUT_S = 125  # PM: 7b 超时容错 120s + 5s 余量
FALLBACK_TIMEOUT_S = 300  # 3b 冷加载覆盖 (~225s)


def ollama_generate(model: str, prompt: str, images_b64: list, timeout: int = 300) -> dict:
    """调用 Ollama /api/generate, 返回响应 JSON。timeout 300s 覆盖 CPU 冷加载。"""
    payload = {
        "model": model,
        "prompt": prompt,
        "images": images_b64,
        "stream": False,
        "keep_alive": "30m",  # 驻留 30min — 热启动 ~25s vs 冷启动 ~220s (CPU 实测)
        "options": {"temperature": 0.1},
    }
    req = urllib.request.Request(
        f"{OLLAMA_URL}/api/generate",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def encode_image(image_arg: str) -> list:
    """image_arg 可以是 base64 字符串或本地文件路径。"""
    if image_arg.startswith(("data:", "iVBOR", "/9j/")) or "base64" in image_arg[:100]:
        # 已编码 (可能是 data URL)
        if image_arg.startswith("data:"):
            return [image_arg.split(",", 1)[1]]
        return [image_arg]
    # 本地路径
    with open(image_arg, "rb") as f:
        return [base64.b64encode(f.read()).decode("utf-8")]


INSIGHT_PROMPT = """你是 BottleSumo 机器人的视觉感知器 (EVAI-V1R Recognize)。
分析这张仿真画面, 输出严格 JSON (不要任何其他文字):
{
  "objects": [{"class": "robot|opponent|dohyo|edge_zone", "position_px": [x, y], "confidence": 0.0-1.0}],
  "robot": {"x": 0.0, "y": 0.0, "heading_deg": 0.0},
  "opponent": {"x": 0.0, "y": 0.0, "heading_deg": 0.0},
  "edge_min": 0.0,
  "zone": "safe|danger|edge",
  "anomaly": null
}
画面坐标系: 原点在 dohyo 圆心 (半径 0.40m), 边缘带 0.32-0.40m 为危险区。
只输出 JSON。"""

GROUND_PROMPT_TMPL = """在画面中定位: {query}
输出严格 JSON: {{"found": true/false, "center_px": [x, y], "bbox": [x1, y1, x2, y2], "confidence": 0.0-1.0}}
只输出 JSON。"""


def parse_json_response(text: str) -> dict:
    """从 VL 输出中提取第一个 JSON 对象 (容忍 ```json 围栏)。"""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # 找第一个 { 到最后一个 }
        s, e = text.find("{"), text.rfind("}")
        if s != -1 and e != -1 and e > s:
            return json.loads(text[s : e + 1])
        raise ValueError(f"VL 输出非 JSON: {text[:200]}")


def _compute_confidence(parsed: dict) -> float:
    """EVAI-V1R 洞察置信度 (确定性启发式, PM 裁决: <0.6 丢弃防编造)。

    基准 0.5; 加分: schema 完整 +0.25, edge_min 数值合法 +0.10, 对象置信度存在 +0.10;
    减分: class 合并("|") -0.35 (3b 已知缺陷), 默认位置 [0,0] -0.15, zone 非法 -0.15。
    3b 合并 class 输出 -> ~0.2-0.4 (触发门控丢弃); 规范输出 -> ~0.85+ (注入)。
    """
    c = 0.5
    required = ("objects", "robot", "opponent", "edge_min", "zone")
    if all(k in parsed for k in required):
        c += 0.25
    try:
        em = float(parsed.get("edge_min"))
        if 0.0 <= em <= 1.0:
            c += 0.10
    except (TypeError, ValueError):
        pass
    objs = parsed.get("objects") or []
    if any(isinstance(o, dict) and isinstance(o.get("confidence"), (int, float))
           for o in objs):
        c += 0.10
    # 减分: class 合并 = 感知失败/编造信号 (PM 裁决: 硬性封顶, 加分救不回)
    merged = any(isinstance(o, dict) and isinstance(o.get("class"), str)
                 and "|" in o["class"] for o in objs)
    if merged:
        return round(min(c, 0.35), 2)
    for key in ("robot", "opponent"):
        v = parsed.get(key)
        if isinstance(v, dict) and v.get("x") == 0.0 and v.get("y") == 0.0:
            c -= 0.15
    if parsed.get("zone") not in ("safe", "danger", "edge"):
        c -= 0.15
    return round(max(0.05, min(0.95, c)), 2)


# ---------- FastAPI 服务 ----------
def build_app(model: str):
    from fastapi import FastAPI, Request, HTTPException
    from fastapi.responses import JSONResponse

    app = FastAPI(title="vision_proxy (EVAI-V1R/A1)", version="1.0.0")

    @app.get("/health")
    async def health():
        return {
            "status": "ready",
            "model": model,
            "backend": "ollama",
            "gpu": False,  # 本机无独显, CPU 推理
            "mode": "auto",  # 按需触发, 非默认开启
            "timestamp": time.time(),
        }

    @app.post("/insight")
    async def insight(request: Request):
        body = await request.json()
        image = body.get("image")
        frame_name = os.path.basename(body.get("frame_name") or "frame.png")
        out_dir = body.get("out_dir")
        # A4_7B_COMPARE (PM 2026-08-06): 请求级模型覆盖 — 实验时按帧指定模型, 无需重启
        # TASK-006 (PM 裁决 2): 默认 7b; 超时/错误自动降级 3b (FALLBACK_TRIGGERED)
        use_model = body.get("model") or model
        if not image:
            raise HTTPException(400, "missing 'image' (base64 or path)")
        t0 = time.time()
        fallback_meta = {}
        try:
            # asyncio.to_thread: ollama_generate 是同步阻塞调用 (最长 300s),
            # 直接调用会阻塞 uvicorn 事件循环 -> 后续请求/响应交错延迟 (A4 实测 74.67s 完成
            # 但客户端 120s 超时). 线程池执行后事件循环保持响应性.
            # PRIMARY_TIMEOUT_S=125: PM 7b 容错 120s + 余量; 超过即降级 3b
            resp = await asyncio.to_thread(
                ollama_generate, use_model, INSIGHT_PROMPT, encode_image(image),
                PRIMARY_TIMEOUT_S if use_model == DEFAULT_MODEL else 300)
        except Exception as e:
            if use_model == DEFAULT_MODEL:
                # 7b 超时/错误 -> 降级 3b (快速 fallback, 隔离热推理 25.3s)
                try:
                    resp = await asyncio.to_thread(
                        ollama_generate, FALLBACK_MODEL, INSIGHT_PROMPT,
                        encode_image(image), FALLBACK_TIMEOUT_S)
                    use_model = FALLBACK_MODEL
                    fallback_meta = {
                        "fallback_triggered": True,
                        "fallback_from": DEFAULT_MODEL,
                        "fallback_to": FALLBACK_MODEL,
                        "fallback_reason": str(e)[:200],
                    }
                    print(f"[vision_proxy] FALLBACK_TRIGGERED: 7b -> 3b ({str(e)[:80]})",
                          flush=True)
                except Exception as e2:
                    return JSONResponse(
                        {"status": "error", "error": f"7b: {e}; 3b fallback: {e2}"},
                        status_code=502)
            else:
                return JSONResponse({"status": "error", "error": str(e)}, status_code=502)
        try:
            parsed = parse_json_response(resp.get("response", "{}"))
        except ValueError as e:
            return JSONResponse(
                {"status": "parse_error", "raw": resp.get("response", ""), "error": str(e)},
                status_code=422,
            )
        # A3 标准化: 顶层 confidence 字段 (PM 裁决门控基准)
        parsed["confidence"] = _compute_confidence(parsed)
        parsed["_meta"] = {
            "model": use_model,
            "latency_s": round(time.time() - t0, 2),
            "mode": "on_demand",
        }
        parsed["_meta"].update(fallback_meta)
        # A3 落盘: 与帧同目录写 insight_<frame>.json (PM 裁决)
        if out_dir:
            try:
                os.makedirs(out_dir, exist_ok=True)
                stem = frame_name[:-4] if frame_name.lower().endswith(".png") else frame_name
                ipath = os.path.join(out_dir, f"insight_{stem}.json")
                with open(ipath, "w", encoding="utf-8") as f:
                    json.dump(parsed, f, ensure_ascii=False, indent=2)
                parsed["_meta"]["written_to"] = ipath
            except OSError as e:
                parsed["_meta"]["write_error"] = str(e)
        return parsed

    @app.post("/ground")
    async def ground(request: Request):
        body = await request.json()
        image = body.get("image")
        query = body.get("query", "机器人")
        if not image:
            raise HTTPException(400, "missing 'image'")
        t0 = time.time()
        try:
            resp = ollama_generate(model, GROUND_PROMPT_TMPL.format(query=query), encode_image(image))
        except Exception as e:
            return JSONResponse({"status": "error", "error": str(e)}, status_code=502)
        try:
            parsed = parse_json_response(resp.get("response", "{}"))
        except ValueError as e:
            return JSONResponse(
                {"status": "parse_error", "raw": resp.get("response", ""), "error": str(e)},
                status_code=422,
            )
        parsed["_meta"] = {"model": model, "latency_s": round(time.time() - t0, 2)}
        return parsed

    return app


def main():
    ap = argparse.ArgumentParser(description="vision_proxy (EVAI-V1R/A1)")
    ap.add_argument("--port", type=int, default=8766)
    ap.add_argument("--model", default=os.environ.get("VISION_MODEL", DEFAULT_MODEL))
    args = ap.parse_args()

    # 启动前健康自检: 模型是否已 pull
    try:
        req = urllib.request.Request(f"{OLLAMA_URL}/api/tags")
        with urllib.request.urlopen(req, timeout=5) as resp:
            tags = json.loads(resp.read().decode("utf-8"))
        names = [m["name"] for m in tags.get("models", [])]
        if args.model not in names:
            print(f"[vision_proxy] WARN: model '{args.model}' 未安装, 请执行: ollama pull {args.model}")
            print(f"[vision_proxy] 已安装: {', '.join(names)}")
            # 尝试降级链 (TASK-006: 主 7b 未装 -> 3b 优先)
            for fallback in ("qwen2.5vl:3b", "llava:7b", "qwen2.5:7b"):
                if fallback in names:
                    args.model = fallback
                    print(f"[vision_proxy] 降级至: {fallback}")
                    break
    except Exception as e:
        print(f"[vision_proxy] WARN: ollama 不可达 ({e}), 启动但不自检")

    import uvicorn

    # 启动后台预热: 1x1 黑色 PNG 完整热起 ViT 编码器 + 权重驻留 (keep_alive 30m)
    def _warmup():
        time.sleep(1.0)
        tiny = base64.b64encode(
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\xcf\xc0\x00\x00\x00\x03\x00\x01\x87\x16\xff\xfd\x00\x00\x00\x00IEND\xaeB`\x82"
        ).decode("utf-8")
        try:
            t0 = time.time()
            resp = ollama_generate(args.model, "输出 JSON: {\"ok\": true}", [tiny])
            print(f"[vision_proxy] warmup OK ({args.model}, {time.time()-t0:.1f}s)", flush=True)
        except Exception as e:
            print(f"[vision_proxy] warmup FAIL: {e}", flush=True)

    threading.Thread(target=_warmup, daemon=True).start()

    print(f"[vision_proxy] EVAI-V1R/A1 serving model={args.model} on :{args.port} (CPU, auto-mode)")
    app = build_app(args.model)
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="info")


if __name__ == "__main__":
    main()
