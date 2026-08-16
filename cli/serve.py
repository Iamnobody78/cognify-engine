#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
serve.py — cognify serve: 认知服务 API + 治理网关 (PRODUCT-ROADMAP P0/P1)
========================================================================
端点:
  GET  /health                 存活检查
  POST /mce    {"input": str}  认知编译 (MCE)
  POST /vce    {"input": str}  价值扫描 (VCE)
  POST /cee    {"input": str, "vce": {...}}  演化推演 (CEE)
  POST /governance/evaluate {"path","method","body"}  五层治理裁决 (P1)

运行: python cli/serve.py [--port 8080]
"""
import json
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

TRI = Path(r"C:\Users\ivy\.aionui-tri-sync")
PROD = Path(r"C:\Users\ivy\AppData\Roaming\AionUi\aionui\conversations\2026\07\27\aionrs-temp-48324704\cognify-engine")
GOV_REPO = PROD / "plugins/governance/src"
sys.path.insert(0, str(TRI / "daemon"))
sys.path.insert(0, str(GOV_REPO))

from fastapi import FastAPI, Request  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402
import uvicorn  # noqa: E402

import cve_s  # noqa: E402

app = FastAPI(title="Cognify Engine API", version="2.1.0",
              description="认知服务 (MCE/VCE/CEE) + 治理网关 (五层裁决)")

_gateway = None


def _gw():
    global _gateway
    if _gateway is None:
        try:
            from src.protocol_gateway import ProtocolGateway
            _gateway = ProtocolGateway()
        except Exception as exc:  # noqa: BLE001
            _gateway = exc
    return _gateway


@app.get("/health")
def health():
    return {"status": "ok", "service": "cognify-engine",
            "version": "2.1.0"}


@app.post("/mce")
async def mce(req: Request):
    body = await req.json()
    text = body.get("input", "")
    if not isinstance(text, str) or not text.strip():
        return JSONResponse({"error": "input 必须为非空字符串"}, status_code=400)
    try:
        return {"endpoint": "/mce", "input": text[:200],
                "mce": cve_s.mce_compile(text)}
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.post("/vce")
async def vce(req: Request):
    body = await req.json()
    text = body.get("input", "")
    if not isinstance(text, str) or not text.strip():
        return JSONResponse({"error": "input 必须为非空字符串"}, status_code=400)
    try:
        return {"endpoint": "/vce", "input": text[:200],
                "vce": cve_s.vce_scan(text)}
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.post("/cee")
async def cee(req: Request):
    body = await req.json()
    text = body.get("input", "")
    vce_res = body.get("vce")
    if not isinstance(text, str) or not text.strip():
        return JSONResponse({"error": "input 必须为非空字符串"}, status_code=400)
    try:
        if vce_res is None:
            vce_res = cve_s.vce_scan(text)
        return {"endpoint": "/cee", "input": text[:200],
                "cee": cve_s.cee_plan(text, vce_res)}
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.post("/governance/evaluate")
async def governance_evaluate(req: Request):
    """五层治理裁决: ALLOW / ALLOW_WITH_WARNING / ESCALATE / DENY / SUSPEND。"""
    body = await req.json()
    path = body.get("path", "/")
    method = body.get("method", "POST")
    payload = body.get("body")
    gw = _gw()
    if isinstance(gw, Exception):
        return JSONResponse({"error": f"网关不可用: {gw}"}, status_code=503)
    try:
        result = gw.evaluate_verified(path, method, payload)
        return {"endpoint": "/governance/evaluate", "path": path,
                "method": method, "verdict": result}
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"error": str(exc)}, status_code=500)


# ---- 产品化公开 API (PRODUCT-ROADMAP-PUSH L3) ----
@app.post("/api/v1/mce/compile")
async def api_mce(req: Request):
    return await mce(req)


@app.post("/api/v1/vce/scan")
async def api_vce(req: Request):
    return await vce(req)


@app.post("/api/v1/cee/evolve")
async def api_cee(req: Request):
    return await cee(req)


@app.post("/api/v1/govern/evaluate")
async def api_govern(req: Request):
    return await governance_evaluate(req)


@app.get("/api/v1/meta/status")
def api_meta_status():
    try:
        st = json.loads((TRI / "meta/status.json").read_text(encoding="utf-8"))
        return {"active": st.get("active_count"), "health": st.get("overall_health")}
    except Exception:  # noqa: BLE001
        return {"error": "meta/status.json 不可用"}


@app.get("/api/v1/health")
def api_health():
    return health()


def main():
    port = 8080
    args = sys.argv[1:]
    for i, a in enumerate(args):
        if a == "--port" and i + 1 < len(args):
            port = int(args[i + 1])
    print(f"[serve] Cognify Engine API :{port} (MCE/VCE/CEE + 治理网关)")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")


if __name__ == "__main__":
    main()
