# 🌐 RouterOS Toolkit

Herramientas de diagnóstico y administración para routers **MikroTik RouterOS** vía API nativa (puerto 8728). Sin dependencias externas — solo Python 3 estándar.

---

## ✨ Características

| Categoría       | Herramienta                   | Descripción                                        |
|-----------------|-------------------------------|----------------------------------------------------|
| ✅ Validación    | `sys_validar.py`       | Verificación previa de conectividad y configuración|
| 📋 Info          | `info_dispositivos.py`          | Inventario de todos los dispositivos en red        |
| 📋 Info          | `mon_consumo.py`         | Ranking de consumo de ancho de banda por IP        |
| 📡 Monitoreo     | `mon_vivo.py`          | Dashboard en tiempo real (auto-refresh)            |
| 📡 Monitoreo     | `info_interfaces.py`       | Tráfico por interfaz física                        |
| 🔧 Mantenimiento | `mant_log.py`            | Visor del syslog del router (con `--follow`)       |
| 🔧 Mantenimiento | `mant_bloqueo.py`              | Bloqueo/desbloqueo de IPs vía firewall             |
| ⚙️ Sistema       | `info_sistema.py`           | CPU, RAM, uptime e información del hardware        |
| 🔍 Identificación| `scan_dispositivos.py`          | Clasifica dispositivos (Apple, móvil, IoT…) por OUI|
| ⏰ Horarios      | `horario_internet.py`     | Corte de internet programado; lista blanca persistente |
| 🚦 QoS           | `qos_desplegar.py`            | Despliega QoS (config en `config/qos.json`, con `--dry-run`) |
| 🚦 QoS           | `qos_diagnostico.py`          | Diagnostica si las reglas Mangle están marcando    |
| 🚦 QoS           | `qos_monitor.py`           | Monitor de tráfico por categoría en tiempo real    |
| 🚦 QoS           | `qos_reset.py`             | Elimina solo los elementos QoS (preserva otras reglas) |
| 💾 Respaldo      | `mant_respaldo.py`                | Snapshot local de la config + `.backup` completo (`--full`) |

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
python3 menu.py                          # menú interactivo (29 opciones)
python3 scripts/info_dispositivos.py       # o cualquier script standalone
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
│   ├── sys_validar.py  # Verificación previa
│   ├── info_*.py / mon_*.py   # Información y monitoreo de red
│   ├── mant_*.py / scan_*.py  # Mantenimiento (log, bloqueo, respaldo) e identificación
│   ├── horario_internet.py    # Corte de internet programado
│   ├── qos_*.py               # Suite QoS (desplegar/diagnóstico/monitor/reset)
│   ├── sys_validar.py         # Verificación previa del router
│   ├── README_QOS.md          # Guía de la suite QoS
│   ├── QOS_USAGE.md            # Manual detallado del despliegue QoS
│   └── QOS_QUICK_REFERENCE.md  # Referencia rápida QoS
├── backups/                   # Snapshots del router (en .gitignore)
├── tests/                     # Suite de tests (unittest, sin router)
├── index.md                   # Referencia técnica: protocolo API + todos los scripts
└── CLAUDE.md                  # Guía para asistentes de código (Claude Code)
```

---

## 📚 Documentación

| Documento | Contenido |
|-----------|-----------|
| [`README.md`](README.md) | Este archivo — visión general e inicio rápido |
| [`index.md`](index.md) | Referencia técnica: protocolo RouterOS API, referencia de uso de cada script con sus flags |
| [`scripts/README_QOS.md`](scripts/README_QOS.md) | Suite QoS: qué hace cada script `qos_*` y flujo típico |
| [`scripts/QOS_USAGE.md`](scripts/QOS_USAGE.md) | Manual completo del despliegue QoS: pasos, pruebas, troubleshooting |
| [`scripts/QOS_QUICK_REFERENCE.md`](scripts/QOS_QUICK_REFERENCE.md) | Referencia rápida QoS: clases de tráfico, prioridades, comandos |
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
- `mant_bloqueo`, `horario_internet`, `qos_desplegar` y `qos_reset` **modifican configuración real del router** (firewall, QoS, schedulers); el resto son de solo lectura

---

## 📄 Licencia

MIT
