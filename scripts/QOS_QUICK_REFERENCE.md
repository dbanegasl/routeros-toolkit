# Quick Reference — qos_desplegar.py

## 🚀 Uso rápido

```bash
# Desplegar QoS
python3 scripts/qos_desplegar.py

# Revertir (si algo falla)
python3 scripts/qos_desplegar.py --rollback
```

---

## ✅ Qué implementa

| Concepto | Cantidad | Detalle |
|----------|----------|---------|
| Reglas Mangle | 23 | Marcado automático de tráfico por criterios (puerto, IP, volumen) |
| Colas Queue Tree | 16 | Árbol jerárquico de prioridades (8 download + 8 upload) |
| Prioridades | 8 | P1 (crítico) → P8 (bulk), con garantías de ancho de banda |
| Clases de tráfico | 8 | DNS, Kevin, Trabajo, Streaming, Web, Resto, Bulk, + Crítico |

---

## 📊 Clases de tráfico

| Marca | Descripción | P | Gbb | Mbps | Límite |
|-------|-------------|---|-----|------|--------|
| `pkt_critico` | DNS (53), ICMP (ping) | 1 | ✓ | 3 DL / 2 UL | 92 |
| `pkt_kevin` | IP 192.168.5.22 | 2 | ✓ | 25 DL / 20 UL | 92 |
| `pkt_trabajo` | SSH, RDP, VPN, dev | 3 | ✓ | 20 DL / 15 UL | 92 |
| `pkt_streaming` | HTTPS (443) non-Kevin | 5 | ✓ | 15 DL / 8 UL | 92 |
| `pkt_web` | HTTP (80) non-Kevin | 6 | ✓ | 10 DL / 5 UL | 92 |
| `pkt_resto` | Unclassified | 7 | ✓ | 5 DL / 3 UL | 92 |
| `pkt_bulk` | TCP >30MB non-Kevin | 8 | ✓ | 4 DL / 2 UL | 50 DL / 30 UL |

**P** = Prioridad | **Gbb** = Garantizado incluso saturado | **Mbps** = Ancho mín.

---

## 🔧 Comandos incluidos

### Paso 0 — Verificación
```
/interface print
/ip firewall filter print where action=fasttrack-connection
/ip dhcp-server lease print where mac-address=F0:2F:74:CB:97:3F
```

### Paso 1 — IP estática Kevin
```
/ip dhcp-server lease add mac-address=F0:2F:74:CB:97:3F address=192.168.5.22
```

### Paso 2 — Deshabilitar FastTrack
```
/ip firewall filter set [where action=fasttrack-connection] disabled=yes
```

### Paso 3 — Limpiar previos
```
/ip firewall mangle remove [find]
/queue tree remove [find]
```

### Paso 4 — Mangle (23 reglas)
```
/ip firewall mangle/add ...  # DNS, ICMP, Kevin, Trabajo, Streaming, Web, Bulk, Resto
```

### Paso 5 — Queue Tree (16 colas)
```
/queue tree/add ...  # QoS_Download, QoS_Upload, DL-1 a DL-8, UL-1 a UL-8
```

### Paso 6 — Verificar
```
/ip firewall mangle print
/queue tree print
/system resource print
```

---

## 📈 Métricas esperadas

Después del despliegue, verificar en **Winbox → Queues → Tree**:

```
Nombre              Bytes       Packets    Dropped    Estado
─────────────────────────────────────────────────────────────
DL-1-Critico        12345       234        0          ✓ Normal
DL-2-Kevin          8923456     45123      0          ✓ Normal (sube cuando Kevin juega)
DL-3-Trabajo        1234567     8932       0          ✓ Normal
DL-8-Bulk           156234567   234567     42         ✓ Normal (alta prioridad baja)
...
```

- **DL-2-Kevin** debe ver tráfico cuando Kevin está jugando/streamando
- **DL-8-Bulk** debe ver tráfico cuando hay descargas >30MB
- **Dropped** debe ser bajo (<1% de packets)

---

## ⚠️ Pre-requisitos

✓ RouterOS 6.49.19+  
✓ API habilitada (`/ip service enable api`)  
✓ config.env con credenciales válidas  
✓ Kevin conectado (MAC: F0:2F:74:CB:97:3F)  
✓ Interfaz WAN: `ether1`  

---

## ❌ Si algo falla

```bash
# Revertir todo:
python3 scripts/qos_desplegar.py --rollback

# Verificar interfaces:
python3 scripts/info_dispositivos.py

# Verificar recursos:
python3 scripts/info_sistema.py

# Consultar documentación completa:
cat scripts/QOS_USAGE.md
```

---

**Última actualización:** 2026-07-02 | **Plan:** QoS_MikroTik_Kevin_KUTOGG_v2.md
