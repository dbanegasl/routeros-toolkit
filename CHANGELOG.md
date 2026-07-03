# Changelog

Todos los cambios notables de este proyecto se documentan en este archivo.

El formato sigue [Keep a Changelog](https://keepachangelog.com/es/1.1.0/)
y el versionado sigue [SemVer](https://semver.org/lang/es/).

## [Sin publicar]

### Agregado (Fase 4 del plan de frontend — 2026-07-02)
- **Primeras escrituras desde la web**, todas con doble salvaguarda:
  el cuerpo `{"confirmar": true}` obligatorio en la API (sin él: 400 y
  cero cambios) y diálogo de confirmación ⚠️ en la UI (espejo del dict
  `CONFIRMAR` del menú CLI).
- **Bloqueos**: `GET/POST /api/bloqueos`, `DELETE /api/bloqueos/{ip}` —
  mismas reglas etiquetadas `BLOQUEADO-POR-MENU-*` del CLI, solo se
  gestionan las propias. En la página Dispositivos: botón
  Bloquear/Desbloquear por fila con badge 🚫.
- **Horario de internet**: `POST /api/horario` (crear/reemplazar el
  corte conservando la lista blanca), `DELETE /api/horario` (el archivo
  whitelist.json persiste) y `GET/PUT /api/horario/whitelist`. Página
  nueva **Horario**: estado del corte, editor de horario y días,
  lista blanca con toggles (todos los dispositivos de la red + los
  offline) y eliminación del corte.
- Tests: ciclo completo crear → eliminar → reprogramar con FakeAPI con
  estado que verifica la **reaplicación automática de la lista blanca**
  (el pendiente histórico), orden ACCEPT→DROP, preservación de reglas
  ajenas, validaciones de IP/hora/días/MAC. Backend: 53 tests.
- **Verificado contra el router real** (2026-07-02, acordado con
  Daniel): bloqueo/desbloqueo de una IP de prueba y el ciclo eliminar →
  reprogramar del corte real (01:01→06:01), con la whitelist de 18
  dispositivos reaplicada automáticamente desde config/whitelist.json.

### Corregido (Fase 4)
- **`lib`: un `!trap` dejaba el `!done` sin leer en el socket** — con
  conexiones reutilizadas (el backend web), el siguiente comando leía
  la respuesta desfasada y devolvía datos truncados (p. ej. el corte
  aparecía intermitentemente como inexistente). Ahora `command()` drena
  hasta `!done` antes de lanzar `MikroTikCommandError`; test de
  protocolo nuevo lo pinea. En el CLI nunca se manifestó (una conexión
  por script).
- **`core/horario.get_wan_interface` no detectaba la WAN en RouterOS
  v6** cuando la ruta default tiene gateway IP: la interfaz viene
  dentro de `gateway-status` ("… reachable via ether1") y no en un
  campo `interface`. Ahora se parsea de ahí (4 tests nuevos). Este bug
  también afectaba al CLI (`horario_internet.py` pedía la WAN a mano).
- Un `HTTPException` de validación ya no resetea la conexión
  persistente del backend.

### Agregado (Fase 3 del plan de frontend — 2026-07-02)
- **WebSockets con muestreo compartido** (`backend/app/ws.py`):
  `/ws/monitor` (consumo por dispositivo + velocidad real por interfaz)
  y `/ws/log` (syslog con niveles). Un solo bucle de muestreo por
  stream sin importar cuántas pestañas estén conectadas — el primer
  cliente lo arranca, el último lo detiene, todos reciben el mismo
  snapshot; conexión persistente al router bajo el mismo candado global
  (se reabre sola si falla). Sin sesión el socket se cierra con 4401.
  Verificado en vivo: dos clientes simultáneos recibieron timestamps
  idénticos (un solo muestreo al router).
- **Página Monitoreo**: gráfica en vivo del tráfico total (↓/↑, paleta
  validada para el tema oscuro con el validador de dataviz), tabla de
  consumo por dispositivo y tabla de interfaces con velocidad real.
- **Página Log**: visor en vivo del syslog con colores por nivel
  (como `mant_log.py`), filtro de texto y auto-scroll (follow).
- Hook `useWs` con reconexión automática (y vuelta al login si el
  servidor responde 4401). Recharts con carga diferida: el bundle
  inicial se mantiene en ~72 KB gzip.

### Corregido (Fase 3)
- RouterOS anota cada login/logout de la API y el backend generaba uno
  por petición HTTP **y otro por cada visita a Monitoreo/Log** (cada
  muestreador WS abría su propia conexión y la cerraba al salir de la
  página): el syslog del router se inundaba de "user admin logged
  in/out via api". Ahora **todo el backend comparte UNA conexión
  persistente** (`get_api` para HTTP y `usar_api` para el muestreo WS,
  ambos bajo el candado global): un !trap la deja viva, un error de red
  la resetea, tras 60 s de ocio se verifica con una lectura barata
  antes de reutilizarla, y el apagado hace logout limpio. Verificado:
  6 visitas a páginas WS + 3 peticiones HTTP = una sola línea de login
  en el syslog. Tests de backend: 36.

### Agregado (Fase 2 del plan de frontend — 2026-07-02)
- **SPA React + Vite + TypeScript** (`frontend/src/`): login contra la
  API, **Inicio** (tarjetas: estado del router con CPU/RAM/disco, corte
  de internet con en-curso y lista blanca, QoS activo/inactivo, top 5 de
  consumo, dispositivos conectados) y **Dispositivos** (inventario con
  búsqueda por nombre/IP/MAC y filtros DHCP/estática). Tema oscuro,
  responsive (barra inferior en el celular), textos centralizados en
  `src/i18n/es.ts`, datos con TanStack Query (polling ligero, 401 →
  vuelta al login), estilos con Tailwind CSS v4.
- **Endpoints nuevos**: `GET /api/consumo?orden=&top=` (top consumidores
  del connection tracking) y `GET /api/auth/sesion` (estado de sesión
  para la SPA). Tests de backend: 24.
- `src/lib/formato.ts` espeja `fmt_bytes`/`fmt_speed` de `lib/` y vitest
  pinea la paridad (mismos números en CLI y panel).
- Dockerfile del frontend ahora multi-stage: `node:22-alpine` compila la
  SPA (`tsc -b && vite build`) y `nginx:alpine` la sirve.

### Agregado (Fase 1 del plan de frontend — 2026-07-02)
- **Backend FastAPI** (`backend/`): API web sobre `lib/` + `core/` con
  autenticación completa — login contra `APP_PASSWORD_HASH` (PBKDF2
  stdlib, generador en `backend/generar_hash.py`), sesiones en cookie
  httpOnly, rate-limit de 5 intentos/min — y endpoints de **lectura**:
  `/api/dispositivos`, `/api/escaneo`, `/api/sistema`, `/api/interfaces`,
  `/api/horario` (con lista blanca y EN RED), `/api/validacion`,
  `/api/config` (sin secretos) y `/api/salud` (healthcheck público).
  Acceso al router serializado con candado global (una conexión a la
  vez). Errores mapeados como los exit codes del CLI: 502
  conexión/login, 400 trap de RouterOS, en español con sugerencia.
  Swagger en `/api/docs`.
- **Docker Compose** (`docker-compose.yml`): servicios `api` (sin puerto
  publicado) y `web` (nginx con placeholder + proxy `/api` y `/ws`;
  único puerto expuesto, configurable con `PANEL_PORT` en `.env`).
  Verificado en WSL2: los contenedores alcanzan el router directamente
  (no hizo falta `network_mode: host`).
- **Tests del backend** (`backend/tests/`, pytest + FakeAPI inyectada,
  sin router): 20 tests — login/401/429/503, logout, todas las rutas
  exigen sesión, un endpoint por sección y mapeo de excepciones a HTTP.
- `config.env.example` documenta `APP_PASSWORD_HASH` y
  `APP_SESSION_TTL`; nuevo `.env.example` con `PANEL_PORT`.

### Cambiado (Fase 0 del plan de frontend — 2026-07-02)
- **Nueva capa `core/`** (stdlib puro): la lógica de negocio de los
  scripts se extrajo a módulos reutilizables que reciben una API
  conectada y retornan datos, sin prints ni input:
  `core/dispositivos.py`, `core/monitoreo.py`, `core/bloqueos.py`,
  `core/horario.py`, `core/qos.py` y `core/respaldo.py`.
- **`scripts/*.py` quedan como capa de presentación** (argparse, tablas
  ANSI, confirmaciones interactivas) sobre `core/`. Comportamiento y
  salida idénticos: verificado corriendo cada script de solo lectura
  contra el router antes y después (solo difieren datos dinámicos como
  contadores y hora).
- **Tests**: los tests que cargaban scripts con `importlib` ahora
  importan `core/` directamente (`test_qos_builders`, `test_backup`,
  `test_schedule_status`); se agregó `tests/test_core.py` con 27 tests
  nuevos de la lógica extraída (consumo, clasificación, bloqueos,
  reglas de horario, filtros del reset QoS). Suite: 146 tests.

## [1.2.0] — 2026-07-02

Suite QoS en el menú, estado del corte de internet claro, respaldos,
y reorganización completa: scripts por sección y menú por décadas.

### Cambiado (reorganización 2026-07-02)
- **Scripts renombrados por sección** (prefijo = grupo de acción; ya no
  empiezan con número, lo que además los hace importables como módulos
  Python — preparación para un futuro frontend). Renombrados con `git mv`
  (el historial de cada archivo se conserva):

  | Antes | Ahora |
  |-------|-------|
  | `00_validate_router.py` | `sys_validar.py` |
  | `01_list_devices.py` | `info_dispositivos.py` |
  | `02_top_consumers.py` | `mon_consumo.py` |
  | `03_live_monitor.py` | `mon_vivo.py` |
  | `04_interface_stats.py` | `info_interfaces.py` |
  | `05_router_log.py` | `mant_log.py` |
  | `06_block_ip.py` | `mant_bloqueo.py` |
  | `07_system_info.py` | `info_sistema.py` |
  | `08_scan_devices.py` | `scan_dispositivos.py` |
  | `09_schedule_internet.py` | `horario_internet.py` |
  | `10_deploy_qos.py` | `qos_desplegar.py` |
  | `11_diagnose_qos.py` | `qos_diagnostico.py` |
  | `12_monitor_qos.py` | `qos_monitor.py` |
  | `13_reset_qos.py` | `qos_reset.py` |
  | `14_backup.py` | `mant_respaldo.py` |
  | `scripts/10_USAGE.md` | `scripts/QOS_USAGE.md` |
  | `scripts/10_QUICK_REFERENCE.md` | `scripts/QOS_QUICK_REFERENCE.md` |

- **Menú renumerado por décadas** — el primer dígito indica la sección:
  1–9 Información · 10–19 Monitoreo · 20–29 Mantenimiento ·
  30–39 Identificación · 40–49 Horario de internet · 50–59 QoS ·
  90–99 Sistema. Agregar opciones nuevas ya no desordena la numeración.
  Las confirmaciones quedaron en [43] eliminar corte, [51] desplegar QoS
  y [54] reset QoS.

### Añadido (arreglos rápidos 2026-07-02)
- **`14_backup.py`** — respaldo de configuración: snapshot JSON local de las
  secciones que el toolkit puede modificar (firewall, mangle, nat, colas,
  leases, schedulers) en `backups/` (gitignored); `--full` crea además un
  `.backup` completo restaurable en el router; `--list` muestra ambos.
  En el menú: opciones [28] y [29].
- **Chequeo de reloj y NTP en `00_validate_router.py`**: compara la hora del
  router contra la del PC (avisa si la deriva supera 2 minutos — los cortes
  por horario dependen de ella) y verifica que el cliente NTP esté activo.
- Helpers de reloj en la lib: `parse_router_date` / `get_router_datetime`
  (formatos de fecha v6 y v7), ahora compartidos por los scripts 00 y 09.

### Corregido
- **La opción [21] del menú (eliminar corte programado) ejecutaba
  `09 --remove` sin pedir confirmación** — ahora exige confirmación explícita
  como las demás opciones que modifican el router de inmediato.
- **Vista de estado del corte de internet (`09 --list`)**:
  - Los horarios que RouterOS v6 devuelve en formato de duración se
    normalizan (mostraba "1h1m → 6h1m" en vez de "01:01 → 06:01").
  - La cabecera distingue **corte programado** de **corte en curso**: una
    línea "Ahora mismo" indica si está bloqueando en este momento según el
    reloj del router (maneja rangos que cruzan medianoche; si el reloj del
    router no se puede leer, usa el de este PC y lo indica).
  - La lista blanca tiene columna **EN RED** (sí/no) y los dispositivos
    desconectados conservan su nombre desde `config/whitelist.json`
    (antes se mostraba "(no en red ahora)" perdiendo el nombre).
  - `tests/test_schedule_status.py`: 17 tests de la lógica (110 en total).

### Añadido
- **Suite QoS en el menú interactivo**: nueva sección "🚦 CALIDAD DE SERVICIO"
  con dry-run [22], desplegar [23], diagnosticar [24], monitor [25] y
  reset [26]; y validación completa del router [27] en SISTEMA (27 opciones).
- **Confirmación explícita en el menú** (dict `CONFIRMAR`) antes de lanzar
  opciones que modifican el router de inmediato (desplegar y reset QoS).
- `tests/test_menu.py`: integridad del menú — claves únicas, scripts
  existentes y que los mutadores inmediatos pidan confirmación (93 tests).

## [1.1.0] — 2026-07-02

Gran ola de mejoras en 5 fases: tests, consolidación DRY, configuración externa,
manejo de errores uniforme y documentación completa.

### Añadido
- **Suite de tests** (`tests/`, 87 tests con `unittest`, sin router ni dependencias):
  protocolo binario RouterOS (codificación de longitudes, login moderno y MD5,
  parsing de respuestas), utilidades, mapeo de dispositivos, configuración JSON,
  constructores de reglas QoS (fijan el plan exacto por defecto) y `run_script`.
- **`lib/app_config.py`**: sistema de configuración JSON en `config/`
  (`load_json_config`/`save_json_config`, override vía `MIKROTIK_CONFIG_DIR`,
  mensajes claros ante JSON corrupto). Plantillas `.example` versionadas;
  archivos reales en `.gitignore`.
- **`config/qos.json`**: toda la configuración del despliegue QoS (dispositivo
  prioritario, interfaces, ancho de banda, umbral bulk) sale del código.
- **`config/whitelist.json`**: la lista blanca del corte de internet (script 09)
  ahora **persiste** — sobrevive a `--remove` y se reaplica automáticamente al
  reprogramar un horario. Ya no se pierde el historial de dispositivos permitidos.
- **`10_deploy_qos.py --dry-run`**: imprime cada regla Mangle y cada cola que se
  crearía, sin tocar el router.
- **`scripts/00_validate_router.py`**: verificación previa de conectividad y
  configuración.
- **`run_script()`** en la lib: los 14 scripts terminan con mensajes de error
  claros en español con sugerencias (nunca tracebacks) y exit codes fijos
  (0 OK, 1 conexión/login, 2 RouterOS/config, 130 Ctrl+C).
- **`get_lan_prefix(api)`**: la subred LAN se detecta desde `/ip/address` del
  router (override con `MIKROTIK_LAN_PREFIX`); se eliminaron los literales
  `192.168.` repartidos por los scripts.
- `MIKROTIK_TIMEOUT` configurable en `config.env`.
- Excepciones tipadas: `MikroTikConnectionError` y `MikroTikCommandError`.
- Documentación: `CLAUDE.md` (guía de arquitectura), suite QoS documentada
  (`scripts/README_QOS.md`, `10_USAGE.md`, `10_QUICK_REFERENCE.md`) y este
  `CHANGELOG.md`.

### Cambiado
- **Consolidación DRY**: helpers duplicados entre scripts (mapeo de nombres,
  `print_header`, formateadores de bytes/velocidad, caché OUI) movidos a
  `lib/mikrotik_api.py` como versión canónica única; patrón de import
  unificado (`from lib import ...`) en los 14 scripts.
- Las reglas Mangle y colas del QoS se construyen con funciones puras
  (`build_mangle_rules`/`build_queue_tree`) cubiertas por tests; los límites
  escalan en proporción al ancho de banda configurado.
- Documentación reescrita y sincronizada (`README.md`, `index.md`, docs QoS):
  conteos de reglas corregidos (el número real es 23 reglas Mangle, 16 colas).

### Corregido
- **Login MD5 (RouterOS < 6.43)**: el challenge `=ret=` se ignoraba y el login
  quedaba a medias; ahora se detecta y responde correctamente.
- **`13_reset_qos.py` era destructivo**: borraba TODAS las reglas de firewall,
  mangle y colas (incluidos los bloqueos del script 06 y horarios del 09).
  Ahora solo elimina elementos etiquetados QoS (comentarios `QoS *`, colas
  `QoS_*`/`DL-*`/`UL-*`) y rehabilita FastTrack, preservando todo lo demás.

## [1.0.0] — 2026-06

Versión inicial del toolkit.

### Añadido
- Cliente del protocolo binario RouterOS API (puerto 8728) desde cero, solo
  librería estándar de Python (`lib/mikrotik_api.py`).
- Menú interactivo (`menu.py`) y scripts numerados standalone:
  inventario de dispositivos (01), top de consumo (02), monitor en vivo (03),
  estadísticas por interfaz (04), visor de log (05), bloqueo de IPs (06),
  info del sistema (07), identificación de dispositivos por OUI (08),
  corte de internet programado con lista blanca (09).
- Suite QoS (10–13): despliegue Mangle + Queue Tree con host prioritario,
  diagnóstico, monitor en tiempo real y reset.
- Caché de fabricantes MAC (`lib/oui_cache.json`, macvendors.com).
- Credenciales vía `config.env` (gitignored, plantilla `.example`).
