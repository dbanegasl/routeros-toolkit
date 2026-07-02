# Changelog

Todos los cambios notables de este proyecto se documentan en este archivo.

El formato sigue [Keep a Changelog](https://keepachangelog.com/es/1.1.0/)
y el versionado sigue [SemVer](https://semver.org/lang/es/).

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
