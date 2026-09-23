# ---- 构建阶段 ----
FROM node:22-alpine AS build
WORKDIR /build
COPY package.json ./
# 锁文件存在时优先使用锁文件
COPY package-lock.json* ./
RUN npm install --no-audit --no-fund
COPY . .
RUN npm run build

# ---- 运行阶段：Nginx 静态托管 + /api 反代 ----
FROM nginx:stable-alpine
COPY --from=build /build/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80

HEALTHCHECK --interval=15s --timeout=5s --retries=5 \
    CMD wget -qO- http://127.0.0.1/ >/dev/null 2>&1 || exit 1

CMD ["nginx", "-g", "daemon off;"]
