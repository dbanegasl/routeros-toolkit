# 📜 Instrucciones de Uso — Script qos_desplegar.py

## 🎯 Descripción

El script `qos_desplegar.py` implementa automáticamente todas las reglas del plan QoS definido en `QoS_MikroTik_Kevin_KUTOGG_v2.md`.

**Qué hace:**
1. ✓ Verifica interfaces, FastTrack e IPs
2. ✓ Asigna IP estática a Kevin (192.168.5.22) por MAC
3. ✓ Deshabilita FastTrack (obligatorio para que QoS funcione)
4. ✓ Limpia configuración QoS previa
5. ✓ Aplica 23 reglas Mangle (Kevin prioritario; toda la LAN no-Kevin como bulk)
6. ✓ Crea 16 colas Queue Tree (jerarquía de prioridades)
7. ✓ Verifica que todo esté en lugar

---

## 📋 Requisitos

1. **MikroTik hEX lite** con **RouterOS v6.49.19+**
2. **API habilitada** en el router (puerto 8728)
   - En Winbox: `IP → Services → api` → Enable
   - O en terminal: `/ip service enable api`
3. **Credenciales configuradas** en `config.env`

---

## 🚀 Uso

### Verificar configuración

```bash
cd /home/daniel/dev/support/mikrotik
cat config.env | grep MIKROTIK
```

Debe mostrar algo como:
```
MIKROTIK_HOST=192.168.1.1
MIKROTIK_PORT=8728
MIKROTIK_USER=admin
MIKROTIK_PASSWORD=tu_contraseña
```

### Ejecutar el despliegue

```bash
python3 scripts/qos_desplegar.py
```

El script mostrará un resumen de cada paso:

```
======================================================================
  🌐 Despliegue Plan QoS MikroTik — Kevin KUTOGG v2
======================================================================

Conectando a 192.168.1.1:8728...
✓ Conectado

======================================================================
  PASO 0: Verificación previa
======================================================================

📋 Interfaces disponibles:
  • ether1 (running: true)
  • ether2 (running: true)
  ...

→ PASO 1: Fijar IP estática de Kevin (192.168.5.22)
----------------------------------------------------------------------
  ℹ️  Creando nuevo lease para Kevin...
  ✓ IP estática creada

→ PASO 2: Deshabilitar FastTrack
----------------------------------------------------------------------
  ✓ Regla FastTrack deshabilitada: Default fast track

→ PASO 3: Limpiar configuración QoS previa
----------------------------------------------------------------------
  ℹ️  No hay reglas Mangle previas
  ℹ️  No hay colas Queue Tree previas

→ PASO 4: Aplicar reglas Mangle (marcado de tráfico)
----------------------------------------------------------------------
  📝 Aplicando 23 reglas Mangle...
    ✓ [ 1/23] QoS P1 - DNS UDP
    ✓ [ 2/23] QoS P1 - DNS TCP (DNSSEC)
    ✓ [ 3/23] QoS P1 - ICMP Ping
    ...
  ✓ 23 reglas Mangle aplicadas

→ PASO 5: Crear árbol de colas Queue Tree
----------------------------------------------------------------------
  📝 Creando 16 colas Queue Tree...
    ✓ [ 1/16] QoS_Download — Cola raiz download - trafico hacia LAN
    ✓ [ 2/16] QoS_Upload — Cola raiz upload - trafico saliente
    ✓ [ 3/16] DL-1-Critico — DNS + ICMP - pasan siempre
    ...
  ✓ 16 colas Queue Tree creadas

→ PASO 6: Verificación final
======================================================================
  ✅ Plan QoS desplegado exitosamente
======================================================================
```

---

## ⚙️ Parámetros

### Despliegue normal
```bash
python3 scripts/qos_desplegar.py
```

### Dry-run (ver todo lo que haría SIN tocar el router)
```bash
python3 scripts/qos_desplegar.py --dry-run
```
Imprime cada regla Mangle y cada cola que se crearía. Úsalo siempre
después de cambiar `config/qos.json` y antes de redesplegar.

### Rollback (revertir toda la configuración)
```bash
python3 scripts/qos_desplegar.py --rollback
```

**Nota:** El rollback solo borra reglas Mangle y colas Queue Tree, y rehabilita FastTrack. No toca firewall.filter ni otras configuraciones.

### Configuración (config/qos.json)

Los valores del despliegue ya no están en el código — se leen de `config/qos.json` (plantilla en `config/qos.json.example`):

```json
{
  "dispositivo_prioritario": {"nombre": "Kevin KUTOGG", "mac": "F0:2F:74:CB:97:3F", "ip": "192.168.5.22"},
  "interfaz_wan": "ether1",
  "bridge_lan": "bridge1",
  "descarga_total_mbps": 100,
  "subida_total_mbps": 100,
  "umbral_bulk_mb": 30
}
```

Sin el archivo se usan estos mismos valores por defecto (el plan original).

---

## 🧪 Pruebas después del despliegue

### 1. Verificar que QoS está activo
```bash
# Desde cualquier máquina con acceso al router
# En Winbox: Queues → Queue Tree
# Deberían aparecer 16 colas con nombres DL-* y UL-*
```

### 2. Probar con tráfico
```bash
# En Kevin (192.168.5.22):
ping 162.254.197.35 -t  # Servidor Steam

# En otra máquina:
wget https://example.com/archivo-grande.iso &  # Descarga pesada
```

**Resultado esperado:**
- Ping de Kevin mantiene < 20 ms incluso durante descarga pesada
- `DL-2-Kevin` en Queue Tree acumula bytes mientras juega
- `DL-8-Bulk` acumula bytes de cualquier equipo de la LAN que no sea Kevin
- Cuando Kevin activa OBS, el scheduler cede prioridad automáticamente

### 3. Monitorear en Winbox
```
Queues → Tree
  → Presionar F5 o Refresh para ver estadísticas en vivo
  → Buscar columnas: Packets, Bytes, Dropped
```

---

## ❌ Troubleshooting

### Problema: "Connection refused"
**Causa:** API no está disponible en el router o credenciales incorrectas

**Solución:**
```bash
# En el router (Winbox → New Terminal):
/ip service enable api
/ip service print
# Debe mostrar: api — running, enabled

# Verificar credenciales:
cat config.env
```

### Problema: "Login failed"
**Causa:** Usuario o contraseña incorrectos

**Solución:**
```bash
# En Winbox → System → Users, verificar usuario y contraseña
# Actualizar config.env
```

### Problema: Reglas Mangle no se aplican
**Causa:** FastTrack sigue activo

**Solución:**
```bash
# El script lo hace automáticamente, pero si sigues con problemas:
# En Winbox → IP → Firewall → Filter
# Buscar reglas con action=fasttrack-connection
# Deshabilitarlas manualmente (disabled=yes)
```

### Problema: Cola Queue Tree no ve tráfico (bytes = 0)
**Causa:** La interfaz WAN o LAN no coincide con el nombre configurado.

**Solución:**
```bash
# Verificar nombres exactos de interfaz WAN y bridge LAN:
# En Winbox → Interfaces
# O ejecutar:
python3 scripts/info_dispositivos.py

# En este router:
# QoS_Download usa parent=bridge1
# QoS_Upload usa parent=ether1
```

---

## 📊 Jerarquía de prioridades (QoS Tree)

```
QoS_Download (85 Mbps max)
├── DL-1-Critico        P1  (DNS + ICMP)       → 3 Mbps guaranteed
├── DL-2-Kevin          P2  (Gaming + OBS)     → 30 Mbps guaranteed ⭐
├── DL-3-Trabajo        P3  (SSH, VPN, RDP)    → 8 Mbps guaranteed
├── DL-5-Streaming      P5  (Netflix, HBO)     → 6 Mbps guaranteed
├── DL-6-Web            P6  (HTTP general)     → 3 Mbps guaranteed
├── DL-7-Resto          P7  (Unclassified)     → 1 Mbps guaranteed
└── DL-8-Bulk           P8  (>30 MB downloads) → 1 Mbps guaranteed / 12 Mbps max

QoS_Upload (85 Mbps max)
├── UL-1-Critico        P1  → 2 Mbps guaranteed
├── UL-2-Kevin          P2  → 30 Mbps guaranteed (OBS stream) ⭐
├── UL-3-Trabajo        P3  → 5 Mbps guaranteed
├── UL-5-Streaming      P5  → 1 Mbps guaranteed
├── UL-6-Web            P6  → 1 Mbps guaranteed
├── UL-7-Resto          P7  → 512 kbps guaranteed / 2 Mbps max
└── UL-8-Bulk           P8  → 256 kbps guaranteed / 1 Mbps max
```

En el perfil actual, `192.168.5.22` es la única IP privilegiada. Todo el resto de
`192.168.5.0/24` entra en `pkt_bulk`, con límites estrictos para proteger el
stream de Kevin incluso si otro dispositivo descarga, actualiza juegos o hace
streaming.

---

## 🔄 Cambios frecuentes

### Cambiar umbral de descarga pesada (actualmente 30 MB)
Editar `config/qos.json`:

```json
{ "umbral_bulk_mb": 10 }
```

Verificar con `--dry-run` y redesplegar:
```bash
python3 scripts/qos_desplegar.py --dry-run
python3 scripts/qos_desplegar.py
```

### Cambiar el dispositivo prioritario o el ancho de banda
Editar `dispositivo_prioritario` / `descarga_total_mbps` / `subida_total_mbps`
en `config/qos.json`. Los límites de todas las colas se escalan en
proporción al ancho de banda configurado (el plan asume 100 Mbps).

### Añadir dispositivo a prioridad baja (como los niños)
Editar `build_mangle_rules()` en el script y añadir antes del BLOQUE 3:

```python
{
    'chain': 'prerouting',
    'action': 'mark-connection',
    'src-address': '192.168.5.30',  # IP del dispositivo
    'new-connection-mark': 'conn_bulk',
    'passthrough': 'yes',
    'comment': 'QoS P8 - Nino 1 siempre bulk'
}
```

(Hay tests que fijan el plan por defecto — ejecuta
`python3 -m unittest discover -s tests` después de tocar las reglas.)

---

## 📝 Notas técnicas

- **RouterOS v6.49.19:** Usa Queue Tree + Mangle (sin CAKE ni FQ-CoDel disponible)
- **connection-bytes:** Solo funciona en `chain=forward` (no en prerouting)
- **parents:** `QoS_Download` usa `bridge1` (tráfico hacia LAN) y `QoS_Upload` usa `ether1` (tráfico hacia internet)
- **LAN no-Kevin:** Todo `192.168.5.0/24` excepto `192.168.5.22` se marca como bulk
- **FastTrack:** Debe estar **deshabilitado** o el QoS nunca verá el tráfico
- **IP de Kevin:** Se fija por MAC (F0:2F:74:CB:97:3F) para que persista tras reboot

---

## 🆘 Soporte

Si algo falla:

1. **Ejecutar verificación:**
   ```bash
   python3 scripts/info_dispositivos.py
   python3 scripts/info_sistema.py
   ```

2. **Revertir:**
   ```bash
   python3 scripts/qos_desplegar.py --rollback
   ```

3. **Verificar manual en Winbox:**
   - IP → Firewall → Mangle (debe haber 23 reglas)
   - Queues → Tree (debe haber ~16 colas)

---

**Documento actualizado:** 2026-07-02
**Compatible con:** RouterOS 6.49.19 — MikroTik hEX lite
