# ===== bottlesumo-pi Dashboard Frontend（React+Vite 构建 → nginx 托管）=====
FROM node:20-alpine AS build
WORKDIR /app
COPY dashboard/frontend/package.json dashboard/frontend/package-lock.json* ./
RUN npm ci || npm install
COPY dashboard/frontend/ ./
RUN npm run build

FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY dashboard/frontend/nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
