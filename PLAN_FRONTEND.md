# Plan: Frontend moderno para el RouterOS Toolkit

> **Documento de planificación** — para ejecutar en sesiones futuras, fase por fase,
> con confirmación de Daniel al cierre de cada fase (workflow establecido del proyecto).
> Generado: 2026-07-02 · Estado del proyecto al planear: v1.2.0

---

## 1. Objetivo

Elevar el toolkit de terminal a una **aplicación web moderna** con paridad completa
respecto al menú actual (las 26 opciones), manteniendo los scripts CLI y `menu.py`
funcionando. Todo en español, responsive (usable desde el celular), y desplegado
con **Docker + docker-compose** en un equipo de la LAN.

## 2. Decisiones ya tomadas (por Daniel, 2026-07-02)

| Decisión | Elección |
|----------|----------|
| Frontend | **React 18 + Vite** (TypeScript) |
| Backend API | **FastAPI** (Python 3.12, reutiliza `lib/` tal cual) |
| Alcance v1 | **Paridad completa** con el menú (lecturas + escrituras) |
| Seguridad | **Login con contraseña propia** de la app (no la del router) |
| Despliegue | **Docker + docker-compose.yml** |

Notas de contexto:
- El "cero dependencias" se conserva para el CLI (`lib/`, `scripts/`, `menu.py`,
  `tests/` siguen siendo stdlib puro). Las dependencias web viven solo en
  `backend/` y `frontend/`, aisladas en sus imágenes Docker.
- El router es de producción (hEX lite, RouterOS v6.49.19). Toda escritura desde
  la web requiere confirmación explícita en la UI (equivalente al dict `CONFIRMAR`
  del menú) y las mismas salvaguardas que los scripts (reglas etiquetadas, reset
  QoS selectivo, whitelist persistente).

## 3. Arquitectura

```
┌─────────────┐     HTTP/WS      ┌──────────────────┐    API binaria 8728   ┌─────────┐
│  Navegador   │ ───────────────▶ │  web (nginx)      │                      │ MikroTik │
│  (React SPA) │                  │  sirve la SPA     │                      │ hEX lite │
└─────────────┘                  │  proxy /api, /ws  │                      └────▲────┘
                                  └────────┬─────────┘                           │
                                           │ red interna docker                  │
                                  ┌────────▼─────────┐                           │
                                  │  api (FastAPI)    │ ──────────────────────────┘
                                  │  + lib/ actual    │
                                  │  + config/, backups/ (volúmenes)
                                  └──────────────────┘
```

- **2 servicios** en compose: `api` (FastAPI/uvicorn) y `web` (nginx con la SPA
  compilada, que hace proxy de `/api` y `/ws` hacia `api`). Un solo puerto expuesto.
- **Sin base de datos** en v1: la configuración sigue en `config/*.json` y
  `config.env` (montados como volúmenes); los respaldos en `backups/`.
- El acceso al router se serializa con un **candado/pool de conexión** en el
  backend (el router v6 es modesto; evitar N conexiones API simultáneas).

## 4. Estructura de directorios propuesta

```
routeros-toolkit/
├── lib/                  # SIN CAMBIOS de filosofía (stdlib): protocolo + helpers
├── core/                 # NUEVO (stdlib): lógica de negocio extraída de scripts/
│   ├── __init__.py
│   ├── dispositivos.py   #   inventario, escaneo/clasificación
│   ├── monitoreo.py      #   consumo, interfaces, sistema, log
│   ├── bloqueos.py       #   lógica de mant_bloqueo
│   ├── horario.py        #   corte + whitelist (de horario_internet)
│   ├── qos.py            #   builders + deploy/diagnóstico/reset (de qos_*)
│   └── respaldo.py       #   snapshot + backup (de mant_respaldo)
├── scripts/              # CLI: quedan como capa fina de presentación sobre core/
├── menu.py               # sigue funcionando igual
├── tests/                # unittest stdlib: crece con tests de core/
├── backend/              # NUEVO: FastAPI (deps propias)
│   ├── app/
│   │   ├── main.py       #   creación de la app, routers, WS
│   │   ├── auth.py       #   login, sesiones/JWT, rate-limit
│   │   ├── deps.py       #   conexión al router (candado), settings
│   │   └── routers/      #   un router por sección (espeja core/)
│   ├── tests/            #   pytest + httpx (API con FakeAPI, sin router)
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/             # NUEVO: React + Vite + TypeScript
│   ├── src/
│   │   ├── pages/        #   una página por sección del menú
│   │   ├── components/   #   tablas, gráficas, diálogos de confirmación
│   │   ├── api/          #   cliente HTTP + hooks (TanStack Query) + WS
│   │   └── i18n/         #   textos en español centralizados
│   ├── Dockerfile        #   build multi-stage → nginx
│   └── nginx.conf
├── docker-compose.yml
└── PLAN_FRONTEND.md      # este documento
```

**Principio rector**: `core/` es la única fuente de lógica. `scripts/` (CLI) y
`backend/` (web) son dos presentaciones de lo mismo. `core/` se mantiene
**stdlib puro** para que el CLI siga sin dependencias y sea testeable con unittest.

## 5. Backend — API REST + WebSockets

### Autenticación
- `POST /api/auth/login` → valida contra `APP_PASSWORD_HASH` (variable de entorno,
  hash generado con `scripts/` o al primer arranque) → cookie de sesión httpOnly
  (o JWT corto). `POST /api/auth/logout`.
- Rate-limit en login (p. ej. 5 intentos/minuto). Todas las demás rutas exigen sesión.
- La contraseña del router **nunca** viaja al navegador; vive en `config.env`
  montado solo en el servicio `api`.

### Endpoints (paridad con el menú, agrupados por década)

| Sección (menú) | Endpoints |
|---|---|
| Información [1–9] | `GET /api/dispositivos` · `GET /api/interfaces` · `GET /api/sistema` |
| Monitoreo [10–19] | `GET /api/consumo?orden=actual\|total` · `WS /ws/monitor` (dashboard en vivo) |
| Mantenimiento [20–29] | `GET /api/log?lineas=50` · `WS /ws/log` (follow) · `GET/POST/DELETE /api/bloqueos` · `GET/POST /api/respaldos` (POST con `{"full": bool}`) |
| Identificación [30–39] | `GET /api/escaneo?filtro=apple\|mobile&online=bool` |
| Horario [40–49] | `GET /api/horario` (estado + en-curso + whitelist con EN RED) · `POST /api/horario` (crear/reemplazar) · `DELETE /api/horario` ⚠️ · `GET/PUT /api/horario/whitelist` |
| QoS [50–59] | `GET /api/qos/plan` (dry-run: reglas y colas que se crearían) · `POST /api/qos/desplegar` ⚠️ · `GET /api/qos/diagnostico` · `WS /ws/qos` (monitor) · `DELETE /api/qos` ⚠️ |
| Sistema [90–99] | `GET /api/validacion` (sys_validar como JSON estructurado) · `GET /api/config` (sin secretos) · `GET /api/salud` (healthcheck) |

- Las rutas ⚠️ (escrituras inmediatas) exigen el cuerpo `{"confirmar": true}` —
  el espejo del dict `CONFIRMAR` del menú — y la UI siempre muestra diálogo previo.
- Respuestas de error consistentes con los exit codes actuales: 401 sesión,
  502 conexión/login al router (`MikroTikConnectionError`), 400 trap/config
  (`MikroTikCommandError`), con el mismo estilo de mensajes en español + sugerencia.
- FastAPI genera documentación Swagger automática en `/api/docs` (protegida por login).

### WebSockets
- `/ws/monitor`, `/ws/log`, `/ws/qos`: el backend muestrea al router en su
  intervalo actual (3–5 s) y difunde a los clientes conectados (un solo muestreo
  compartido, no uno por pestaña).

## 6. Frontend — React + Vite

### Páginas (espejo de las secciones del menú)
1. **Login** — contraseña única.
2. **Dashboard** (inicio) — tarjetas: estado del router (CPU/RAM/uptime), corte de
   internet (en curso o no, próximo corte), QoS activo o no, top 5 consumidores,
   dispositivos conectados. Es el `mon_vivo` elevado.
3. **Dispositivos** — tabla del inventario con búsqueda/filtros (Apple, móviles,
   bloqueados), acciones por fila: bloquear/desbloquear ⚠️, agregar a whitelist.
4. **Monitoreo** — gráficas en vivo (WebSocket): consumo por dispositivo,
   tráfico por interfaz.
5. **Horario de internet** — estado visual del corte (reloj/franja horaria),
   editor de horario y días, gestión de lista blanca (con columna EN RED y
   nombres persistentes), eliminar corte ⚠️.
6. **QoS** — estado actual, visor del plan (dry-run renderizado como árbol de
   colas y tabla de reglas), desplegar ⚠️, diagnóstico con contadores,
   monitor en vivo por categoría, reset ⚠️.
7. **Mantenimiento** — visor de log (con follow), respaldos (crear/listar,
   badge de "último respaldo hace X días").
8. **Sistema** — validación completa renderizada (checks con ✓/⚠️/❌), info de
   configuración (sin secretos).

### Stack técnico del frontend
- **TypeScript** estricto; **TanStack Query** para datos/cache/reintentos;
  **Recharts** para gráficas; **Tailwind CSS** para estilos (tema oscuro por
  defecto, como la terminal actual); WebSocket nativo con hook propio.
- Diálogo de confirmación estándar para toda acción ⚠️ (mismo texto que
  `CONFIRMAR` del menú).
- Todos los textos en español, centralizados en `i18n/es.ts`.
- Responsive: el caso de uso "silenciar internet desde el celular" debe ser cómodo.

## 7. Docker / docker-compose

```yaml
# docker-compose.yml (esquema objetivo)
services:
  api:
    build: ./backend
    env_file: config.env              # credenciales del router (nunca en la imagen)
    environment:
      - APP_PASSWORD_HASH=${APP_PASSWORD_HASH}
    volumes:
      - ./config:/app/config          # qos.json, whitelist.json compartidos con el CLI
      - ./backups:/app/backups
    restart: unless-stopped
    healthcheck: {test: curl -f http://localhost:8000/api/salud}
    # sin puerto publicado: solo accesible vía web

  web:
    build: ./frontend
    ports:
      - "8080:80"                     # ÚNICO puerto expuesto a la LAN
    depends_on: [api]
    restart: unless-stopped
```

- **Backend Dockerfile**: `python:3.12-slim`, copia `lib/`, `core/`, `backend/`;
  `pip install -r requirements.txt`; usuario no-root; uvicorn.
- **Frontend Dockerfile**: multi-stage — `node:22` para `vite build` →
  `nginx:alpine` sirviendo `dist/` + proxy `/api` y `/ws` → `api:8000`.
- `.dockerignore` (config.env, backups, __pycache__, node_modules).
- Nota WSL2: si el host es Windows/WSL2, verificar que los contenedores alcanzan
  192.168.5.1 (red del router); documentar la alternativa `network_mode: host`
  o despliegue en un equipo Linux/NAS de la LAN.

## 8. Testing

- **`core/` + `lib/`**: siguen con unittest stdlib (los 119 tests actuales deben
  seguir verdes en todo momento; los tests de lógica migran/crecen con `core/`).
- **`backend/`**: pytest + httpx `TestClient`; el router se simula con el patrón
  `FakeAPI` ya existente (inyectado por dependencia). Cobertura mínima: auth
  (login/401/rate-limit), un endpoint por sección, todos los ⚠️ rechazan sin
  `confirmar:true`, mapeo de excepciones a códigos HTTP.
- **`frontend/`**: vitest para hooks/utilidades + tipado estricto como red principal.
- **CI (GitHub Actions)**: job 1 unittest (stdlib, sin deps), job 2 pytest backend,
  job 3 build frontend + vitest, job 4 `docker compose build`.

## 9. Fases de implementación

Cada fase termina con: tests verdes + verificación funcional + resumen + **confirmo de Daniel**.
Las escrituras al router real solo se prueban con su acuerdo explícito en esa fase.

### Fase 0 — Capa `core/` (sin web todavía)
Extraer la lógica de `scripts/*.py` a `core/` (stdlib); los scripts quedan como
capa de presentación fina. Los 119 tests migran los imports y se agregan tests
directos de `core/`. **Verificación**: suite completa + salida de los scripts CLI
byte-comparable contra referencia (mismo método de la Fase 1 original).

### Fase 1 — Backend FastAPI mínimo + Docker
Esqueleto de `backend/` con auth completa + endpoints de **lectura** (dispositivos,
sistema, horario, validación) + `docker-compose.yml` con los 2 servicios corriendo.
**Verificación**: pytest verde; `docker compose up` en el equipo de Daniel; login
y lecturas reales contra el router desde Swagger.

### Fase 2 — Frontend base
SPA con login, layout de navegación, Dashboard e Información/Dispositivos
(solo lectura). **Verificación**: build de producción servido por nginx del compose;
prueba desde PC y celular.

### Fase 3 — Tiempo real
WebSockets (`/ws/monitor`, `/ws/log`) + páginas Monitoreo y visor de log con gráficas.
**Verificación**: dos clientes simultáneos, un solo muestreo al router.

### Fase 4 — Escrituras: bloqueos + horario de internet
Endpoints y UI de bloqueo/desbloqueo, crear/eliminar horario, whitelist (con
confirmaciones). **Verificación**: ciclo completo contra el router real acordado
con Daniel (incluye el pendiente histórico: crear → eliminar → reprogramar y
confirmar reaplicación automática de whitelist).

### Fase 5 — QoS + respaldos
Visor del plan (dry-run), desplegar/diagnóstico/monitor/reset, página de respaldos.
**Verificación**: dry-run web idéntico al CLI; despliegue real solo si Daniel lo
decide (con respaldo previo desde la propia UI).

### Fase 6 — Cierre
Validación (sys_validar como página), hardening (headers de seguridad, revisión de
auth, `docker compose` con usuario no-root), documentación (README de despliegue,
CLAUDE.md, CHANGELOG) y corte de **v2.0.0**.

## 10. Riesgos y mitigaciones

| Riesgo | Mitigación |
|--------|------------|
| Router v6 modesto ante muchas conexiones API | Candado/pool único en el backend; WS con muestreo compartido |
| Escritura accidental desde la web | `confirmar:true` obligatorio + diálogo UI + auth; mismas reglas etiquetadas de siempre |
| Exponer el panel más allá de la LAN | Un solo puerto, documentar NO abrirlo al WAN; login con rate-limit; cookies httpOnly |
| WSL2 no alcanza la subred del router desde contenedores | Probar temprano en Fase 1; fallback `network_mode: host` o host Linux dedicado |
| Divergencia CLI ↔ web | `core/` como única fuente de lógica; tests que cubren ambos consumidores |
| Deriva del reloj rompe horarios | Ya cubierto: chequeo en validación; mostrarlo en el Dashboard |

## 11. Qué NO cambia

- `menu.py` y todos los `scripts/*.py` siguen funcionando exactamente igual.
- `lib/` y `core/` permanecen stdlib puro (el CLI conserva cero dependencias).
- `config.env` y `config/*.json` siguen siendo la fuente de configuración (gitignored).
- El workflow: fase → tests → verificación → confirmo → merge a main → siguiente.

## 12. Criterios de aceptación globales

1. Toda operación del menú actual es posible desde la web, con confirmación en las peligrosas.
2. `docker compose up -d` en un equipo de la LAN deja el panel operativo en `http://<host>:8080`.
3. Suite stdlib (unittest) + pytest + build frontend: todo verde en CI.
4. Un usuario sin la contraseña no puede leer ni escribir nada.
5. El CLI produce los mismos resultados que antes de la reorganización a `core/`.
6. Documentado: despliegue, variables de entorno, y mapa endpoint ↔ opción del menú.
