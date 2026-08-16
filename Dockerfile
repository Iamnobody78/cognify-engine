# Cognify Engine — Docker 镜像
FROM python:3.12-slim

WORKDIR /app

# 依赖
COPY pyproject.toml .
RUN pip install --no-cache-dir -e . || pip install --no-cache-dir fastapi uvicorn

# 代码
COPY . .

# 端口
EXPOSE 8080

# 启动认知服务 API
CMD ["python", "cli/cognify.py", "serve", "--port", "8080"]
