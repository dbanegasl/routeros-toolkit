# 🌐 RouterOS Toolkit

Herramientas de diagnóstico y administración para routers **MikroTik RouterOS** vía API nativa (puerto 8728). Sin dependencias externas — solo Python 3 estándar.

---

## ✨ Características

| Categoría      | Herramienta                  | Descripción                                      |
|----------------|------------------------------|--------------------------------------------------|
| 📋 Info         | `01_list_devices.py`         | Inventario de todos los dispositivos en red      |
| 📋 Info         | `02_top_consumers.py`        | Ranking de consumo de ancho de banda por IP      |
| 📡 Monitoreo    | `03_live_monitor.py`         | Dashboard en tiempo real (auto-refresh)          |
| 📡 Monitoreo    | `04_interface_stats.py`      | Tráfico por interfaz física                      |
| 🔧 Mantenimiento| `05_router_log.py`           | Visor del syslog del router                      |
| 🔧 Mantenimiento| `06_block_ip.py`             | Bloqueo/desbloqueo de IPs vía firewall           |
| ⚙️ Sistema      | `07_system_info.py`          | CPU, RAM, uptime e información del hardware      |

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

### 3. Ejecutar

```bash
python3 menu.py
```

---

## 🗂️ Estructura del proyecto

```
routeros-toolkit/
├── menu.py                  # Menú principal interactivo
├── config.env.example       # Plantilla de configuración (safe to commit)
├── config.env               # Credenciales reales (en .gitignore)
├── lib/
│   ├── mikrotik_api.py      # Cliente RouterOS API + utilidades
│   └── __init__.py
├── scripts/
│   ├── 01_list_devices.py
│   ├── 02_top_consumers.py
│   ├── 03_live_monitor.py
│   ├── 04_interface_stats.py
│   ├── 05_router_log.py
│   ├── 06_block_ip.py
│   └── 07_system_info.py
└── index.md                 # Documentación técnica del protocolo API
```

---

## 🔌 Protocolo RouterOS API

La comunicación usa el protocolo binario nativo de MikroTik (puerto 8728):

- **Sentences**: listas de *words* con prefijo de longitud + terminador nulo
- **Login**: `/login =name=X =password=Y` → respuesta `!done` (RouterOS 6.43+)
- **FastTrack**: para obtener bytes reales se suma `orig-bytes + orig-fasttrack-bytes`

Ver [`index.md`](index.md) para documentación técnica completa.

---

## 📸 Preview

```
╔══════════════════════════════════════════════════╗
║         🌐 MIKROTIK ROUTEROS TOOLKIT             ║
║             Router: DUOTICS  │  hEX lite          ║
╚══════════════════════════════════════════════════╝

  📋 INFO
    1 · Listar dispositivos
    2 · Top consumidores
  📡 MONITOREO
    3 · Monitor en vivo
    4 · Estadísticas de interfaces
  🔧 MANTENIMIENTO
    5 · Ver log del router
    6 · Bloquear / desbloquear IP
  ⚙️  SISTEMA
    7 · Información del sistema

  0 · Salir

Selecciona una opción:
```

---

## ⚠️ Seguridad

- `config.env` está incluido en `.gitignore` — **nunca se sube al repo**
- Se recomienda crear un usuario de solo lectura en el router para operaciones de monitoreo
- La API escucha en la LAN; no exponer el puerto 8728 a internet

---

## 📄 Licencia

MIT
