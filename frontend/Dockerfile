FROM node:20-alpine AS build

WORKDIR /app

ARG VITE_API_BASE=https://argusai-backend-1007754127412.us-central1.run.app
ARG VITE_ADMIN_PASSWORD=argusai2026
ENV VITE_API_BASE=$VITE_API_BASE
ENV VITE_ADMIN_PASSWORD=$VITE_ADMIN_PASSWORD

COPY package*.json ./
RUN npm ci

COPY . .
RUN npm run build

FROM node:20-alpine

WORKDIR /app
RUN npm install -g serve@14

COPY --from=build /app/dist ./dist

CMD ["sh", "-c", "serve -s dist -l tcp://0.0.0.0:${PORT:-8080}"]
