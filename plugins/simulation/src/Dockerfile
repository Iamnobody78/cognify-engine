# ===== bottlesumo-pi Dashboard Backend（含同进程治理引擎）=====
# 多阶段构建:
#   stage 1: 拉取 agent-governance-v2（独立公共仓库, ARG 锁定 ref）→ 安装引擎依赖
#   stage 2: 安装 dashboard 依赖 → 复制源码 → 启动 uvicorn
#
# 架构说明 (GAP-5.1 / v3.0 解耦前): 引擎与 dashboard 同进程集成，
# 镜像内 GOV_AGENTS_V2_PATH=/app/engine；未来解耦为独立服务后移除本 stage。

# ---------- stage 1: engine ----------
FROM python:3.11-slim AS engine
ARG GOV_ENGINE_REPO=https://github.com/Iamnobody78/agent-governance-v2.git
ARG GOV_ENGINE_REF=main
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && git clone --depth 1 --branch ${GOV_ENGINE_REF} ${GOV_ENGINE_REPO} /engine \
    && rm -rf /engine/.git \
    && pip install --no-cache-dir -r /engine/requirements.txt \
    && apt-get purge -y git \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

# ---------- stage 2: runtime ----------
FROM python:3.11-slim AS runtime
WORKDIR /app
COPY --from=engine /engine /app/engine
COPY dashboard/backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY dashboard/backend/ /app/

ENV GOV_AGENTS_V2_PATH=/app/engine
ENV PYTHONUNBUFFERED=1
ENV GOV_LOG_FORMAT=json
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health', timeout=3)" || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
