# Servicio web: nginx sirviendo la SPA + proxy /api y /ws → api:8000
# Fase 1: página placeholder; en la Fase 2 esto pasa a build multi-stage
# (node:22 `vite build` → nginx:alpine con dist/).
FROM nginx:alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY public/ /usr/share/nginx/html/
