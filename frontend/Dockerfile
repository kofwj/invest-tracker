# 与 CI / 开发机一致：jsdom 30 → undici 8 要求 node >=22.19（构建阶段只跑 vite build，
# 但保持同一 Node 主版本，避免依赖解析/引擎告警两边不一致）
FROM node:22-alpine AS build

WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
