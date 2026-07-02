# 🌐 RouterOS Toolkit

Herramientas de diagnóstico y administración para routers **MikroTik RouterOS** vía API nativa (puerto 8728). Sin dependencias externas — solo Python 3 estándar.

---

## ✨ Características

| Categoría       | Herramienta                   | Descripción                                        |
|-----------------|-------------------------------|----------------------------------------------------|
| ✅ Validación    | `00_validate_router.py`       | Verificación previa de conectividad y configuración|
| 📋 Info          | `01_list_devices.py`          | Inventario de todos los dispositivos en red        |
| 📋 Info          | `02_top_consumers.py`         | Ranking de consumo de ancho de banda por IP        |
| 📡 Monitoreo     | `03_live_monitor.py`          | Dashboard en tiempo real (auto-refresh)            |
| 📡 Monitoreo     | `04_interface_stats.py`       | Tráfico por interfaz física                        |
| 🔧 Mantenimiento | `05_router_log.py`            | Visor del syslog del router (con `--follow`)       |
| 🔧 Mantenimiento | `06_block_ip.py`              | Bloqueo/desbloqueo de IPs vía firewall             |
| ⚙️ Sistema       | `07_system_info.py`           | CPU, RAM, uptime e información del hardware        |
| 🔍 Identificación| `08_scan_devices.py`          | Clasifica dispositivos (Apple, móvil, IoT…) por OUI|
| ⏰ Horarios      | `09_schedule_internet.py`     | Corte de internet programado; lista blanca persistente |
| 🚦 QoS           | `10_deploy_qos.py`            | Despliega QoS (config en `config/qos.json`, con `--dry-run`) |
| 🚦 QoS           | `11_diagnose_qos.py`          | Diagnostica si las reglas Mangle están marcando    |
| 🚦 QoS           | `12_monitor_qos.py`           | Monitor de tráfico por categoría en tiempo real    |
| 🚦 QoS           | `13_reset_qos.py`             | Elimina solo los elementos QoS (preserva otras reglas) |

---

## 🚀 Inicio rápido

### 1. Requisitos

- Python 3.6+
- RouterOS 6.x o 7.x
- API habilitada en el router (puerto 8728)

> **Habilitar la API en MikroTik:**  
> `IP → Services → api` → Enabled ✓  
> O desde terminal: `/ip service enable api`

### 2. Configuración

```bash
git clone https://github.com/TU_USUARIO/routeros-toolkit.git
cd routeros-toolkit
cp config.env.example config.env
```

Edita `config.env` con tus datos:

```env
MIKROTIK_HOST=192.168.1.1
MIKROTIK_PORT=8728
MIKROTIK_USER=admin
MIKROTIK_PASSWORD=tu_contraseña
```

Las variables de entorno del sistema (`MIKROTIK_HOST`, `MIKROTIK_PORT`, `MIKROTIK_USER`, `MIKROTIK_PASSWORD`) sobreescriben el archivo.

### 3. Ejecutar

```bash
python3 menu.py                          # menú interactivo (21 opciones)
python3 scripts/01_list_devices.py       # o cualquier script standalone
```

### 4. Tests (opcional, no requiere router)

```bash
python3 -m unittest discover -s tests -v
```

Todos los scripts usan exit codes consistentes (`0` OK, `1` conexión/login, `2` RouterOS/config, `130` Ctrl+C) y muestran errores como mensajes claros con sugerencias, nunca tracebacks.

---

## 🗂️ Estructura del proyecto

```
routeros-toolkit/
├── menu.py                    # Menú principal interactivo (punto de entrada)
├── config.env.example         # Plantilla de credenciales (safe to commit)
├── config.env                 # Credenciales reales (en .gitignore)
├── config/
│   ├── qos.json.example       # Plantilla: configuración del despliegue QoS
│   ├── whitelist.json.example # Plantilla: lista blanca del corte de internet
│   └── *.json                 # Archivos reales (en .gitignore)
├── lib/
│   ├── __init__.py
│   ├── mikrotik_api.py        # Cliente RouterOS API + utilidades compartidas
│   ├── app_config.py          # Configuración JSON de la aplicación (config/)
│   └── oui_cache.json         # Caché de fabricantes MAC (macvendors.com)
├── scripts/
│   ├── 00_validate_router.py  # Verificación previa
│   ├── 01–09_*.py             # Herramientas de info, monitoreo y control
│   ├── 10–13_*.py             # Suite QoS (deploy / diagnose / monitor / reset)
│   ├── README_QOS.md          # Guía de la suite QoS
│   ├── 10_USAGE.md            # Manual detallado del despliegue QoS
│   └── 10_QUICK_REFERENCE.md  # Referencia rápida QoS
├── tests/                     # Suite de tests (unittest, sin router)
├── index.md                   # Referencia técnica: protocolo API + todos los scripts
└── CLAUDE.md                  # Guía para asistentes de código (Claude Code)
```

---

## 📚 Documentación

| Documento | Contenido |
|-----------|-----------|
| [`README.md`](README.md) | Este archivo — visión general e inicio rápido |
| [`index.md`](index.md) | Referencia técnica: protocolo RouterOS API, referencia de uso de cada script (00–09) con sus flags |
| [`scripts/README_QOS.md`](scripts/README_QOS.md) | Suite QoS: qué hace cada script (10–13) y flujo típico |
| [`scripts/10_USAGE.md`](scripts/10_USAGE.md) | Manual completo del despliegue QoS: pasos, pruebas, troubleshooting |
| [`scripts/10_QUICK_REFERENCE.md`](scripts/10_QUICK_REFERENCE.md) | Referencia rápida QoS: clases de tráfico, prioridades, comandos |
| [`QOS_IMPLEMENTATION_SUMMARY.txt`](QOS_IMPLEMENTATION_SUMMARY.txt) | Resumen histórico de la implementación QoS |
| [`CLAUDE.md`](CLAUDE.md) | Arquitectura y convenciones para asistentes de código |

---

## 🔌 Protocolo RouterOS API

La comunicación usa el protocolo binario nativo de MikroTik (puerto 8728):

- **Sentences**: listas de *words* con prefijo de longitud + terminador nulo
- **Login**: `/login =name=X =password=Y` → respuesta `!done` (RouterOS 6.43+)
- **FastTrack**: para obtener bytes reales se suma `orig-bytes + orig-fasttrack-bytes`

Ver [`index.md`](index.md) para documentación técnica completa.

---

## ⚠️ Seguridad

- `config.env` está incluido en `.gitignore` — **nunca se sube al repo**
- Se recomienda crear un usuario de solo lectura en el router para operaciones de monitoreo
- La API escucha en la LAN; no exponer el puerto 8728 a internet
- Los scripts 06, 09, 10 y 13 **modifican configuración real del router** (firewall, QoS, schedulers); el resto son de solo lectura

---

## 📄 Licencia

MIT
