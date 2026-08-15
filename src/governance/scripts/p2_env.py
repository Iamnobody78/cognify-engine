#!/usr/bin/env python3
"""P2 gpt-researcher 配置助手 — p2_env.py (零依赖).

write-template: 若 .env 不存在则从模板生成 (含占位 key, 绝不覆盖已有文件)
validate:       校验 .env 完整性 (key 是否已填/模型前缀/检索器)

用法:
  python scripts/p2_env.py write-template [--env .env] [--force]
  python scripts/p2_env.py validate [--env .env]

退出码: 0 通过; 1 校验告警 (如 key 未填); 2 用法错误。
"""

import argparse
import pathlib
import sys

TEMPLATE = """# P2 gpt-researcher 配置 — 由 scripts/p2_env.py 生成, 勿提交
# 官方文档: https://docs.gptr.dev (DeepSeek / Ollama provider 均已验证)
#
# ── 模式 A: 本地 Ollama (零 API Key, 默认) ──
# 前置: ollama serve 已运行; 已拉取模型: ollama pull qwen2.5:7b
FAST_LLM="ollama:qwen2.5:7b"
SMART_LLM="ollama:qwen2.5:7b"
STRATEGIC_LLM="ollama:qwen2.5:7b"
OLLAMA_BASE_URL="http://localhost:11434"
EMBEDDING="ollama:bge-m3"
#
# ── 模式 B: DeepSeek API (需 key; 使用前注释掉模式 A 三行 LLM) ──
# FAST_LLM="deepseek:deepseek-chat"
# SMART_LLM="deepseek:deepseek-chat"
# STRATEGIC_LLM="deepseek:deepseek-reasoner"
# DEEPSEEK_API_KEY="sk-REPLACE_ME"
#
# 搜索后端: duckduckgo (免费无 key, 包名 ddgs) | searxng (自托管) | tavily (需 key)
RETRIEVER="duckduckgo"
"""

PLACEHOLDERS = ("sk-REPLACE_ME", "sk-你的DeepSeek密钥", "", "sk-")
KNOWN_RETRIEVERS = {"duckduckgo", "searxng", "tavily", "you", "google", "bing", "ddgs"}
KNOWN_MODELS = {"deepseek-chat", "deepseek-reasoner", "deepseek-v4-flash", "deepseek-v4-pro"}
KNOWN_OLLAMA_MODELS = {"qwen2.5:7b", "qwen2.5:0.5b", "llama3.1:8b", "llama3.2:3b", "gemma2:9b", "qwen2.5"}


def _reconfigure():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def _parse_env(path: pathlib.Path) -> dict:
    """解析 .env 的 KEY="value" 行 (忽略注释/空行)。"""
    env = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        env[key.strip()] = val.strip().strip('"').strip("'")
    return env


def write_template(env_path: pathlib.Path, force: bool = False) -> int:
    if env_path.exists() and not force:
        print(f"⏭️  .env 已存在: {env_path} (未覆盖; 用 --force 或先 validate)")
        return 1
    env_path.write_text(TEMPLATE, encoding="utf-8")
    print(f"✅ 已生成 .env 模板: {env_path}")
    print("   默认 Ollama 零-key 模式: 确认 ollama serve 运行中即可 validate")
    print("   如需 DeepSeek: 注释模式A三行, 取消模式B注释并填 DEEPSEEK_API_KEY")
    return 0


def validate(env_path: pathlib.Path) -> int:
    if not env_path.exists():
        print(f"ERROR: .env 不存在: {env_path} — 先运行 write-template", file=sys.stderr)
        return 2
    env = _parse_env(env_path)
    issues = []

    # 判断模式: 任一 LLM 为 deepseek: → 必须填 key; 全 ollama: → 零 key 可过
    llm_fields = ("FAST_LLM", "SMART_LLM", "STRATEGIC_LLM")
    has_deepseek = any(str(env.get(f, "")).startswith("deepseek:") for f in llm_fields)
    has_ollama = any(str(env.get(f, "")).startswith("ollama:") for f in llm_fields)

    embed = env.get("EMBEDDING", "")
    embed_ollama = embed.startswith("ollama:")
    if embed and ":" not in embed:
        issues.append(f"EMBEDDING 应形如 <provider>:<model> (当前: {embed!r})")
    elif embed:
        prov = embed.split(":", 1)[0]
        if prov not in ("ollama", "openai", "cohere", "google"):
            issues.append(f"EMBEDDING provider {prov!r} 不受支持 (ollama/openai/cohere/google)")
    has_ollama = has_ollama or embed_ollama

    if has_deepseek:
        key = env.get("DEEPSEEK_API_KEY", "")
        if not key or key in PLACEHOLDERS or key.startswith("sk-REPLACE_ME"):
            issues.append("DEEPSEEK_API_KEY 未填写 (占位符) — 使用 DeepSeek 模式必需")
        elif not key.startswith("sk-") or len(key) < 20:
            issues.append(f"DEEPSEEK_API_KEY 格式可疑 (len={len(key)}, 期望 sk- 开头 ≥20 字符)")

    for field in llm_fields:
        val = env.get(field, "")
        if val.startswith("deepseek:"):
            model = val.split(":", 1)[1]
            if model not in KNOWN_MODELS:
                issues.append(f"{field} 模型 {model!r} 不在已知列表 {sorted(KNOWN_MODELS)}")
        elif val.startswith("ollama:"):
            model = val.split(":", 1)[1]
            if not model:
                issues.append(f"{field} ollama 模型为空 (应如 ollama:qwen2.5:7b)")
            elif model not in KNOWN_OLLAMA_MODELS:
                issues.append(f"{field} ollama 模型 {model!r} 不在已知列表 {sorted(KNOWN_OLLAMA_MODELS)}"
                              f" — 如已本地拉取, 请加入 KNOWN_OLLAMA_MODELS")
        else:
            issues.append(f"{field} 应形如 deepseek:<model> 或 ollama:<model> (当前: {val!r})")

    if has_ollama:
        base_url = env.get("OLLAMA_BASE_URL", "")
        if not base_url:
            issues.append("OLLAMA_BASE_URL 未填写 (ollama 模式必需, 如 http://localhost:11434)")
        elif not base_url.startswith(("http://", "https://")):
            issues.append(f"OLLAMA_BASE_URL 格式可疑 (当前: {base_url!r}, 期望 http(s)://...)")

    retriever = env.get("RETRIEVER", "").lower()
    if retriever not in KNOWN_RETRIEVERS:
        issues.append(f"RETRIEVER {retriever!r} 不在已知列表 {sorted(KNOWN_RETRIEVERS)}")
    elif retriever == "tavily":
        issues.append("RETRIEVER=tavily 需要 TAVILY_API_KEY — 推荐改用 duckduckgo")

    if issues:
        print(f"⚠️  校验失败 ({len(issues)} 项):")
        for i in issues:
            print(f"  - {i}")
        return 1
    mode = "ollama(零key)" if (has_ollama and not has_deepseek) else "deepseek"
    print(f"✅ .env 校验通过 ({mode} 模式, key/模型/检索器均就绪)")
    return 0


def main(argv=None) -> int:
    _reconfigure()
    ap = argparse.ArgumentParser(description="P2 gpt-researcher 配置助手")
    ap.add_argument("cmd", choices=["write-template", "validate"])
    ap.add_argument("--env", default=".env", help=".env 路径 (默认 ./ .env)")
    ap.add_argument("--force", action="store_true", help="write-template 强制覆盖")
    args = ap.parse_args(argv)
    env_path = pathlib.Path(args.env)
    if args.cmd == "write-template":
        return write_template(env_path, args.force)
    return validate(env_path)


if __name__ == "__main__":
    sys.exit(main())
