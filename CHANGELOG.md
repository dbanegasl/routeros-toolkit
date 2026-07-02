# Changelog

Todos los cambios notables de este proyecto se documentan en este archivo.

El formato sigue [Keep a Changelog](https://keepachangelog.com/es/1.1.0/)
y el versionado sigue [SemVer](https://semver.org/lang/es/).

## [Sin publicar]

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
