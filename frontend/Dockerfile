# Multi-stage: build the SPA with Node, serve the static files with a non-root
# nginx. The final image contains only the built assets and nginx.

# --- Build ------------------------------------------------------------------
FROM node:20-alpine AS build
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm install
COPY . .
RUN npm run build

# --- Serve (non-root nginx) -------------------------------------------------
FROM nginxinc/nginx-unprivileged:1.27-alpine AS runtime
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 8080
