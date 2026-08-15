# syntax=docker/dockerfile:1
# governance-gateway — 阶段 C1 容器化 (多阶段构建)
# 运行时: python:3.11-slim + tree-sitter 硬锁 (0.21.3 / 1.5.0, 与本地/CI 完全一致)

# ── 构建阶段: 需要 gcc 编译 tree-sitter C 扩展 ──────────────
FROM python:3.11-slim AS builder
WORKDIR /build

# 先装构建依赖 (利用层缓存)
RUN apt-get update && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
# 复制源码以便 setuptools 找到包 (无 src 布局错误)
COPY src ./src
RUN pip install --no-cache-dir \
    "tree-sitter==0.21.3" \
    "tree-sitter-languages==1.5.0" \
    && pip install --no-cache-dir .

# ── 运行时镜像 ──────────────────────────────────────────────
FROM python:3.11-slim AS runtime
WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=UTC

COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

COPY src ./src
COPY config ./config
COPY queries ./queries

# 非 root 运行
RUN useradd --create-home --uid 10001 gateway
USER gateway

EXPOSE 9000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:9000/v1/health', timeout=3).status==200 else 1)"

CMD ["python", "-m", "src.main"]
