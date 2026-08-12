# Build tĩnh Web App (React/Vite) rồi phục vụ qua Nginx. Biến VITE_* là build-time (Vite
# bake thẳng vào bundle JS lúc `npm run build`) — đổi API_BASE sau khi build đòi build lại
# image, không đọc được từ biến môi trường container lúc chạy như backend Python.
FROM node:20-alpine AS build
WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

ARG VITE_API_BASE=http://localhost:8083
ARG VITE_WS_BASE=
ARG VITE_API_KEY=
ENV VITE_API_BASE=$VITE_API_BASE
ENV VITE_WS_BASE=$VITE_WS_BASE
ENV VITE_API_KEY=$VITE_API_KEY

RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
