# MikroTik Network Tools

Colección de scripts Python para monitoreo y diagnóstico de un router **MikroTik RouterOS v6.49.19** via la API nativa (puerto 8728).

---

## 📁 Estructura

```
mikrotik/
├── config.env                  # ← Credenciales del router (editar aquí)
├── index.md                    # Este archivo
├── lib/
│   ├── __init__.py
│   └── mikrotik_api.py         # Librería base reutilizable
└── scripts/
    ├── 01_list_devices.py      # Lista todos los dispositivos de la red
    ├── 02_top_consumers.py     # Top consumidores de ancho de banda
    ├── 03_live_monitor.py      # Monitor en vivo con auto-refresh
    └── 04_interface_stats.py   # Estadísticas por interfaz física
```

---

## ⚙️ Configuración

Edita `config.env` con los datos de tu router:

```env
MIKROTIK_HOST=192.168.5.1
MIKROTIK_PORT=8728
MIKROTIK_USER=admin
MIKROTIK_PASSWORD=tu_contraseña
```

Los scripts también respetan variables de entorno del sistema operativo  
(sobreescriben el archivo):

```bash
export MIKROTIK_PASSWORD="otra_clave"
python3 scripts/02_top_consumers.py
```

---

## 🚀 Uso — Arranque rápido

```bash
# Desde la raíz del proyecto:
cd /home/daniel/dev/support/
./mikrotik.sh

# O directamente desde la carpeta:
cd mikrotik/
./menu.py
```

El **menú principal** tiene 4 categorías y 13 opciones. Selecciona con números y Enter. Ctrl+C en cualquier script devuelve al menú.

---

## 📁 Estructura

```
/home/daniel/dev/support/
├── mikrotik.sh                 ← 🚀 LANZADOR (ejecutar desde aquí)
└── mikrotik/
    ├── menu.py                 ← Menú interactivo principal
    ├── config.env              ← Credenciales del router (editar aquí)
    ├── index.md                ← Esta documentación
    ├── lib/
    │   ├── __init__.py
    │   └── mikrotik_api.py     ← Librería base (API, colores, utilidades)
    └── scripts/
        ├── 01_list_devices.py      ← Inventario de dispositivos
        ├── 02_top_consumers.py     ← Top consumidores
        ├── 03_live_monitor.py      ← Monitor en vivo
        ├── 04_interface_stats.py   ← Tráfico por interfaz
        ├── 05_router_log.py        ← Log del router
        ├── 06_block_ip.py          ← Bloquear/desbloquear IPs
        └── 07_system_info.py       ← Info del sistema (CPU/RAM/uptime)
```

### `01_list_devices.py` — Inventario de dispositivos

Lista todos los dispositivos con IP asignada (DHCP o estática), su MAC,
nombre de host, puerto físico del switch y fabricante.

```bash
cd mikrotik/
python3 scripts/01_list_devices.py

# Buscar un dispositivo específico
python3 scripts/01_list_devices.py | grep -i samsung
python3 scripts/01_list_devices.py | grep ether5
```

**Salida ejemplo:**
```
  IP               MAC                HOSTNAME                   ESTADO     PUERTO   TIPO     FABRICANTE
─────────────────────────────────────────────────────────────────────────────────────────────────────────
  192.168.5.22     F0:2F:74:CB:97:3F  —                          estática   ether5   STATIC   ASUSTeK
  192.168.5.93     00:1E:C2:C6:4C:F1  Daniels-iMac               bound      ether3   DHCP     Apple
```

---

### `02_top_consumers.py` — Top consumidores (snapshot)

Analiza las conexiones activas y muestra qué dispositivo usa más internet
en este momento. Una sola consulta, resultado inmediato.

```bash
python3 scripts/02_top_consumers.py
python3 scripts/02_top_consumers.py --top 10
python3 scripts/02_top_consumers.py --sort total    # por GB acumulados
```

**Opciones:**
| Flag | Descripción | Default |
|------|-------------|---------|
| `--top N` | Mostrar los N primeros | 15 |
| `--sort rate\|total` | Ordenar por velocidad actual o total de sesión | `rate` |

---

### `03_live_monitor.py` — Monitor en vivo ⬅ uso frecuente

Dashboard que se refresca automáticamente. Muestra velocidad en tiempo
real de cada dispositivo. Presiona `Ctrl+C` para salir.

```bash
python3 scripts/03_live_monitor.py                # refresca cada 3s
python3 scripts/03_live_monitor.py --interval 5   # cada 5 segundos
python3 scripts/03_live_monitor.py --top 10       # mostrar top 10
```

**Opciones:**
| Flag | Descripción | Default |
|------|-------------|---------|
| `--interval N` | Segundos entre refrescos | 3 |
| `--top N` | Líneas a mostrar | 20 |

---

### `04_interface_stats.py` — Estadísticas por interfaz

Muestra el tráfico total y velocidad actual de cada interfaz física.
Útil para identificar qué puerto del router está saturado.

```bash
python3 scripts/04_interface_stats.py              # snapshot
python3 scripts/04_interface_stats.py --watch       # mide velocidad real (5s)
python3 scripts/04_interface_stats.py --watch --interval 10
```

**Opciones:**
| Flag | Descripción | Default |
|------|-------------|---------|
| `--watch` | Tomar dos muestras y calcular velocidad | off |
| `--interval N` | Segundos entre muestras | 5 |

---

## 🔌 Cómo funciona la conexión (RouterOS API)

MikroTik expone una API binaria propietaria en el **puerto TCP 8728** (sin TLS)
y **8729** (con TLS). No es necesario instalar nada extra en el router — está
habilitada por defecto.

### Protocolo

La comunicación se basa en **"sentences"** (oraciones), donde cada sentence
es una lista de **"words"** (palabras):

```
Sentence = [Word1, Word2, ..., WordN, \x00]   ← terminador = byte nulo
```

Cada word se prefija con su longitud codificada en 1–4 bytes:

| Longitud | Bytes usados | Codificación |
|----------|-------------|--------------|
| < 128 | 1 byte | `LL` |
| < 16384 | 2 bytes | `10LL LLLL` |
| < 2097152 | 3 bytes | `110L LLLL LLLL` |
| mayor | 4 bytes | `1110 LLLL ...` |

### Tipos de words

```
/ip/dhcp-server/lease/print    ← comando (empieza con /)
=name=valor                    ← parámetro (=clave=valor)
?src-address=192.168.5.1       ← filtro/query
!re                            ← respuesta: registro
!done                          ← respuesta: fin de resultados
!trap                          ← respuesta: error
```

### Flujo de login (RouterOS ≥ 6.43)

```
Cliente  →  /login =name=admin =password=secret
Router   →  !done
```

### Flujo de login legacy (RouterOS < 6.43 / MD5)

```
Cliente  →  /login =name=admin =password=secret
Router   →  !done =ret=<challenge_hex>
Cliente  →  /login =name=admin =response=00<MD5(\x00 + password + challenge)>
Router   →  !done
```

### Habilitación de la API en el router

Si la API está deshabilitada, desde WebFig o terminal:

```
/ip service enable api
/ip service set api port=8728
```

Para habilitar API con TLS (recomendado en producción):
```
/ip service enable api-ssl
/ip service set api-ssl port=8729
```

---

## 📊 Campos del Connection Tracking usados

Los scripts de bandwidth usan el comando `/ip/firewall/connection/print`.
Campos relevantes por conexión:

| Campo | Descripción |
|-------|-------------|
| `src-address` | IP:puerto de origen (LAN) |
| `dst-address` | IP:puerto de destino (WAN) |
| `orig-rate` | Bytes/s que el cliente **sube** al exterior |
| `repl-rate` | Bytes/s que el exterior **baja** al cliente |
| `orig-bytes` | Total bytes subidos (vía conntrack normal) |
| `repl-bytes` | Total bytes bajados (vía conntrack normal) |
| `orig-fasttrack-bytes` | Bytes subidos por FastTrack (aceleración HW) |
| `repl-fasttrack-bytes` | Bytes bajados por FastTrack |

> **Nota FastTrack:** MikroTik acelera conexiones TCP establecidas usando
> FastTrack, que bypasea el conntrack normal. Por eso se suman ambos campos
> (`bytes + fasttrack-bytes`) para obtener el total real.

---

## 🗺️ Mapa de red detectado

| IP | Hostname | MAC | Puerto | Tipo |
|----|----------|-----|--------|------|
| 192.168.5.22 | *(PC ASUS — IP estática)* | F0:2F:74:CB:97:3F | ether5 | STATIC |
| 192.168.5.21 | *(PC GIGABYTE — IP estática)* | D8:5E:D3:83:0A:D2 | ether3 | STATIC |
| 192.168.5.93 | Daniels-iMac | 00:1E:C2:C6:4C:F1 | ether3 | DHCP |
| 192.168.5.48/39 | deco-X55 (x2) | DC:62:79:FA:4A:… | ether3/4 | DHCP |
| 192.168.5.56/57 | H1c EZVIZ (x2) | 60:DC:81:… | ether3 | DHCP |
| 192.168.5.43 | Google-Home-Mini | 44:07:0B:52:26:B9 | ether3 | DHCP |
| 192.168.5.55 | Blink-Mini | 74:AB:93:A8:2F:63 | ether4 | DHCP |
| 192.168.5.87 | EPSON F5430E | B0:E8:92:F5:43:0E | ether4 | DHCP |

---

## 🔧 Requisitos

- Python 3.6+
- Sin dependencias externas (solo librería estándar)
- Acceso de red al router en puerto 8728
- Usuario con permisos de lectura en RouterOS (rol `read` es suficiente)
