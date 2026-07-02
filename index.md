# MikroTik Network Tools — Referencia técnica

Colección de scripts Python para monitoreo y administración de routers **MikroTik RouterOS** vía la API nativa (puerto 8728).

Este documento es la **referencia técnica completa**: configuración, uso de cada script con sus flags, y detalles del protocolo RouterOS API. Para una visión general del proyecto ver [`README.md`](README.md).

---

## ⚙️ Configuración

Edita `config.env` con los datos de tu router:

```env
MIKROTIK_HOST=192.168.1.1
MIKROTIK_PORT=8728
MIKROTIK_USER=admin
MIKROTIK_PASSWORD=tu_contraseña
```

Los scripts también respetan variables de entorno del sistema operativo (sobreescriben el archivo):

```bash
export MIKROTIK_PASSWORD="otra_clave"
python3 scripts/mon_consumo.py
```

Orden de resolución de `load_config()`: ruta explícita → variable `MIKROTIK_ENV_FILE` → `config.env` en la raíz del proyecto → variables de entorno del sistema (prioridad máxima).

Opcionales: `MIKROTIK_TIMEOUT` (segundos de espera, default 15) y `MIKROTIK_LAN_PREFIX` (fuerza el prefijo de la subred LAN; normalmente se detecta automáticamente desde `/ip/address`).

**Exit codes de todos los scripts:** `0` OK · `1` error de conexión o login · `2` error de RouterOS o de configuración · `130` cancelado con Ctrl+C. Los errores siempre se muestran como mensajes claros con sugerencias, nunca tracebacks.

---

## 🚀 Uso — Arranque rápido

```bash
# Desde la raíz del proyecto:
python3 menu.py
```

El **menú principal** tiene 7 categorías y 29 opciones. Selecciona con números y Enter. `Ctrl+C` en cualquier script devuelve al menú. El primer dígito indica la sección (1–9 Información, 10s Monitoreo, 20s Mantenimiento, 30s Identificación, 40s Horario, 50s QoS, 90s Sistema). Las opciones que modifican el router de forma inmediata (eliminar corte [43], desplegar QoS [51] y eliminar QoS [54]) piden confirmación explícita antes de ejecutarse.

Todos los scripts funcionan también standalone desde la raíz del proyecto.

La lógica de negocio vive en **`core/`** (stdlib puro, sin prints): los scripts de `scripts/` son la capa de presentación CLI sobre esos módulos (`core/dispositivos.py`, `core/monitoreo.py`, `core/bloqueos.py`, `core/horario.py`, `core/qos.py`, `core/respaldo.py`). Sobre esa misma capa corre el **panel web** (`backend/` FastAPI + `frontend/` nginx, vía `docker compose up -d`): endpoints de lectura protegidos por login propio de la app, documentados en `/api/docs` (Swagger). Ver README § Panel web.

---

## 📖 Referencia de scripts

### `sys_validar.py` — Verificación previa

Chequeo completo antes de operar: identidad, interfaces, IPs, FastTrack, estado QoS y tráfico. Indica el próximo paso según lo que encuentre.

```bash
python3 scripts/sys_validar.py
```

Sin flags. Solo lectura.

---

### `info_dispositivos.py` — Inventario de dispositivos

Lista todos los dispositivos con IP asignada (DHCP o estática), su MAC, hostname, puerto físico del switch y fabricante.

```bash
python3 scripts/info_dispositivos.py

# Buscar un dispositivo específico
python3 scripts/info_dispositivos.py | grep -i samsung
python3 scripts/info_dispositivos.py | grep ether5
```

Sin flags. Solo lectura.

---

### `mon_consumo.py` — Top consumidores (snapshot)

Analiza las conexiones activas (connection tracking) y muestra qué dispositivo usa más internet en este momento. Una sola consulta, resultado inmediato.

```bash
python3 scripts/mon_consumo.py
python3 scripts/mon_consumo.py --top 10
python3 scripts/mon_consumo.py --sort total    # por GB acumulados
```

| Flag | Descripción | Default |
|------|-------------|---------|
| `--top N` | Mostrar los N primeros | 15 |
| `--sort rate\|total` | Ordenar por velocidad actual o total de sesión | `rate` |
| `--no-color` | Deshabilitar colores ANSI | off |

---

### `mon_vivo.py` — Monitor en vivo

Dashboard que se refresca automáticamente. Muestra velocidad en tiempo real de cada dispositivo. `Ctrl+C` para salir.

```bash
python3 scripts/mon_vivo.py                # refresca cada 3s
python3 scripts/mon_vivo.py --interval 5   # cada 5 segundos
python3 scripts/mon_vivo.py --top 10
```

| Flag | Descripción | Default |
|------|-------------|---------|
| `--interval N` | Segundos entre refrescos | 3 |
| `--top N` | Líneas a mostrar | 20 |

---

### `info_interfaces.py` — Estadísticas por interfaz

Tráfico total y velocidad actual de cada interfaz física. Útil para identificar qué puerto del router está saturado.

```bash
python3 scripts/info_interfaces.py               # snapshot
python3 scripts/info_interfaces.py --watch       # mide velocidad real
python3 scripts/info_interfaces.py --watch --interval 10
```

| Flag | Descripción | Default |
|------|-------------|---------|
| `--watch` | Tomar dos muestras y calcular velocidad | off |
| `--interval N` | Segundos entre muestras | 5 |

---

### `mant_log.py` — Log del router

Muestra el syslog de RouterOS con colores por nivel (error rojo, warning amarillo, info normal, debug gris).

```bash
python3 scripts/mant_log.py                # últimas 50 líneas
python3 scripts/mant_log.py --lines 100
python3 scripts/mant_log.py --follow       # modo follow (Ctrl+C para salir)
python3 scripts/mant_log.py --filter dhcp  # filtrar por texto
```

| Flag | Descripción | Default |
|------|-------------|---------|
| `--lines N` | Número de líneas a mostrar | 50 |
| `--follow` | Actualización continua | off |
| `--filter TEXTO` | Solo entradas que contengan el texto | — |

---

### `mant_bloqueo.py` — Bloquear / desbloquear IPs ⚠️ modifica firewall

Agrega o quita reglas `drop` en la cadena FORWARD. Solo gestiona sus propias reglas (comentario `BLOQUEADO-POR-MENU-<IP>`), nunca toca reglas ajenas.

```bash
python3 scripts/mant_bloqueo.py                    # modo interactivo con confirmación
python3 scripts/mant_bloqueo.py --block 192.168.5.22
python3 scripts/mant_bloqueo.py --unblock 192.168.5.22
python3 scripts/mant_bloqueo.py --list
```

| Flag | Descripción |
|------|-------------|
| `--block IP` | Bloquear esta IP |
| `--unblock IP` | Desbloquear esta IP |
| `--list` | Listar IPs bloqueadas por este script |

---

### `info_sistema.py` — Información del sistema

Modelo, versión de RouterOS, uptime, CPU, RAM, temperatura (si el hardware la reporta), disco e interfaces activas.

```bash
python3 scripts/info_sistema.py
python3 scripts/info_sistema.py --watch   # refresca cada 3s
```

| Flag | Descripción | Default |
|------|-------------|---------|
| `--watch` | Actualización continua | off |

---

### `scan_dispositivos.py` — Identificación avanzada de dispositivos

Combina DHCP, ARP y (opcionalmente) macvendors.com para clasificar cada dispositivo: Apple, móvil, IoT, MAC privada/aleatoria, etc. Los resultados online se guardan en `lib/oui_cache.json` para no repetir consultas.

```bash
python3 scripts/scan_dispositivos.py                  # solo base OUI local
python3 scripts/scan_dispositivos.py --lookup         # consulta macvendors.com (~1 req/s)
python3 scripts/scan_dispositivos.py --filter apple
python3 scripts/scan_dispositivos.py --filter mobile
python3 scripts/scan_dispositivos.py --filter unknown
```

| Flag | Descripción |
|------|-------------|
| `--lookup` | Consultar macvendors.com para OUIs desconocidos (más lento) |
| `--filter TIPO` | Filtrar: `apple`, `mobile`, `unknown` |

---

### `horario_internet.py` — Corte de internet por horario ⚠️ modifica firewall

Bloquea internet a **todos** los dispositivos en un horario definido, excepto los de la lista blanca (reglas ACCEPT por MAC). Los nuevos dispositivos quedan bloqueados por defecto. Solo gestiona sus propias reglas (comentarios `HORARIO-INTERNET` y `HORARIO-PERMITIDO`). Requiere hora correcta en el router (NTP).

**Persistencia:** la lista blanca se guarda en `config/whitelist.json` y **sobrevive a `--remove`** — al programar un nuevo corte se reaplica automáticamente. `--list` detecta desincronización entre el archivo y las reglas del router.

```bash
python3 scripts/horario_internet.py            # configurar horario (interactivo)
python3 scripts/horario_internet.py --list     # ver estado y lista blanca
python3 scripts/horario_internet.py --allow    # gestionar lista blanca
python3 scripts/horario_internet.py --remove   # eliminar todas las reglas
```

| Flag | Descripción |
|------|-------------|
| `--list` | Ver el corte programado, si está **en curso ahora** (según el reloj del router), y la lista blanca con columna EN RED |
| `--allow` | Gestionar lista blanca (persiste en `config/whitelist.json`) |
| `--remove` | Borrar las reglas del router (la whitelist del archivo se conserva) |

`--list` distingue el **corte programado** (la regla existe) del **corte en curso** (está bloqueando en este momento), maneja rangos que cruzan medianoche, y normaliza los tiempos que RouterOS v6 devuelve en formato de duración (`1h1m` → `01:01`). Los dispositivos de la lista blanca que no están conectados conservan su nombre desde `config/whitelist.json`.

---

### `mant_respaldo.py` — Respaldo de configuración

Snapshot local en JSON (en `backups/`, gitignored) de todas las secciones que el toolkit puede modificar: firewall filter/mangle/nat, colas, leases DHCP, schedulers y direcciones IP, con metadatos del router. El modo por defecto y `--list` son de **solo lectura**. Úsalo antes de desplegar QoS o tocar firewall.

```bash
python3 scripts/mant_respaldo.py             # snapshot local (solo lectura)
python3 scripts/mant_respaldo.py --full      # + .backup completo EN el router
python3 scripts/mant_respaldo.py --list      # ver respaldos locales y del router
```

| Flag | Descripción |
|------|-------------|
| *(sin flags)* | Snapshot JSON local de las secciones mutables |
| `--full` | Además ejecuta `/system/backup/save` — el `.backup` restaurable queda en el router (Files en Winbox) |
| `--list` | Lista snapshots locales y archivos `.backup` del router |

El directorio local es `backups/` (override: `MIKROTIK_BACKUP_DIR`).

---

### Suite QoS (`qos_*.py`) ⚠️ modifica mangle, colas y FastTrack

Despliegue, diagnóstico, monitoreo y reset de QoS (Mangle + Queue Tree). La configuración (dispositivo prioritario, interfaces WAN/bridge, ancho de banda total, umbral bulk) vive en **`config/qos.json`** (plantilla: `config/qos.json.example`); sin archivo se usan los valores del plan original. Documentación dedicada:

- [`scripts/README_QOS.md`](scripts/README_QOS.md) — visión general y flujo típico
- [`scripts/QOS_USAGE.md`](scripts/QOS_USAGE.md) — manual completo con troubleshooting
- [`scripts/QOS_QUICK_REFERENCE.md`](scripts/QOS_QUICK_REFERENCE.md) — referencia rápida

```bash
python3 scripts/qos_desplegar.py              # desplegar
python3 scripts/qos_desplegar.py --dry-run    # mostrar reglas SIN tocar el router
python3 scripts/qos_desplegar.py --rollback   # revertir
python3 scripts/qos_diagnostico.py            # verificar marcado de tráfico
python3 scripts/qos_monitor.py             # monitor por categoría (5s)
python3 scripts/qos_reset.py               # borrar SOLO lo del QoS (reglas 'QoS *', colas QoS_*/DL-*/UL-*)
```

---

## 🔌 Cómo funciona la conexión (RouterOS API)

MikroTik expone una API binaria propietaria en el **puerto TCP 8728** (sin TLS) y **8729** (con TLS). No es necesario instalar nada extra en el router.

### Protocolo

La comunicación se basa en **"sentences"** (oraciones), donde cada sentence es una lista de **"words"** (palabras):

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
?src-address=192.168.1.1       ← filtro/query
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

Los scripts de bandwidth usan el comando `/ip/firewall/connection/print`. Campos relevantes por conexión:

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

## 🔧 Requisitos

- Python 3.6+
- Sin dependencias externas (solo librería estándar)
- Acceso de red al router en puerto 8728
- Usuario con permisos de lectura en RouterOS (rol `read` es suficiente para los scripts de monitoreo; `mant_bloqueo`, `horario_internet`, `qos_desplegar` y `qos_reset` requieren permisos de escritura)
