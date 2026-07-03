# Servicio web: build de la SPA (node) → nginx sirviendo dist/
# + proxy /api y /ws → api:8000
FROM node:22-alpine AS build
WORKDIR /build
COPY package.json package-lock.json ./
RUN npm ci
COPY index.html vite.config.ts tsconfig.json ./
COPY src/ src/
RUN npm run build

# Imagen no-root: nginx corre como usuario `nginx` (uid 101) y escucha
# en 8080 (los puertos <1024 requieren root)
FROM nginxinc/nginx-unprivileged:alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /build/dist/ /usr/share/nginx/html/
