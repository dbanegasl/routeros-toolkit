# QoS Scripts — MikroTik RouterOS v6.49.19

> 💡 Toda la suite está disponible también desde el **menú interactivo**
> (`python3 menu.py`, sección "🚦 CALIDAD DE SERVICIO"): dry-run [50],
> desplegar [51], diagnosticar [52], monitor [53] y reset [54]. Las
> opciones que modifican el router (51 y 54) piden confirmación.

## 📋 Scripts disponibles

### 1. **qos_desplegar.py** — DESPLEGAR QoS
Aplica la configuración completa de QoS (Mangle + Queue Tree). Los
parámetros (dispositivo prioritario, interfaces, ancho de banda) se leen
de `config/qos.json` (plantilla: `config/qos.json.example`).

```bash
python3 scripts/qos_desplegar.py             # desplegar
python3 scripts/qos_desplegar.py --dry-run   # ver qué haría SIN tocar el router
```

**Qué hace:**
- ✅ Verifica router y conexión
- ✅ Fija IP estática de Kevin (192.168.5.22)
- ✅ Deshabilita FastTrack
- ✅ Limpia configuración QoS previa
- ✅ Aplica 23 reglas Mangle
- ✅ Crea 16 colas Queue Tree (8 download + 8 upload)

**Resultado:**
- Kevin: 75% ancho de banda (priority 1)
- Trabajo: 15% ancho de banda (priority 3)
- Streaming: 7% ancho de banda (priority 5)
- Resto: residual (priority 7+8)

---

### 2. **qos_diagnostico.py** — DIAGNOSTICAR QoS
Verifica si las reglas Mangle están funcionando correctamente.

```bash
python3 scripts/qos_diagnostico.py
```

**Qué muestra:**
- ✅ Contadores de cada regla Mangle (bytes/packets)
- ✅ Queues de Queue Tree activas
- ✅ Cuál categoría (Kevin, Bulk, etc) está usando más ancho
- ✅ Si hay errores de configuración

---

### 3. **qos_monitor.py** — MONITOREAR EN TIEMPO REAL
Muestra en tiempo real cuánto ancho de banda usa cada categoría.

```bash
python3 scripts/qos_monitor.py
```

**Qué muestra (cada 5 segundos):**
- 🔴 CRÍTICO (DNS/ICMP)
- 🎮 KEVIN (Gaming + OBS)
- 💼 TRABAJO (SSH/VPN)
- 🎬 STREAMING (Netflix/HBO)
- 🌐 WEB (HTTP)
- 📡 RESTO (Sin clasificar)
- 📥 BULK (Descargas >30MB)

**Presiona Ctrl+C para salir**

---

### 4. **qos_reset.py** — ELIMINAR EL QoS
Borra las reglas Mangle del QoS (comentario `QoS *`) y las colas
`QoS_*`/`DL-*`/`UL-*`, y rehabilita FastTrack. **No toca** reglas de otros
gestores (bloqueos de mant_bloqueo, horarios de horario_internet, reglas manuales).

```bash
python3 scripts/qos_reset.py
```

**Uso:**
- Después de desplegar QoS si algo sale mal
- Para volver a estado limpio y reintentar
- Antes de actualizar RouterOS

---

## 🔄 Flujo típico

```
1. Desplegar QoS
   python3 scripts/qos_desplegar.py

2. Diagnosticar si funciona
   python3 scripts/qos_diagnostico.py

3. Monitorear en tiempo real (durante tests)
   python3 scripts/qos_monitor.py

4. Si algo sale mal, eliminar todo
   python3 scripts/qos_reset.py
   
5. Volver a intentar desde paso 1
```

---

## 📊 Ancho de banda configurado

Asume **100 Mbps** total (fibra típica).

| Categoría | Download | Upload | Priority | Garantizado |
|-----------|----------|--------|----------|-------------|
| CRÍTICO   | 3 Mbps   | 2 Mbps | 1        | 3M / 2M    |
| KEVIN     | **30M**  | **30M**| 2        | 30M / 30M  |
| TRABAJO   | 10 Mbps  | 5 Mbps | 3        | 10M / 5M   |
| STREAMING | 8 Mbps   | 2 Mbps | 5        | 8M / 2M    |
| WEB       | 5 Mbps   | 2 Mbps | 6        | 5M / 2M    |
| RESTO     | 3 Mbps   | 1 Mbps | 7        | 3M / 1M    |
| **BULK**  | **2 Mbps**| **512k**| 8       | 2M / 512k  |

---

## ⚡ Cambiar ancho de banda total

Si tu velocidad es **50 Mbps** o **200 Mbps**, edita `config/qos.json`:

```json
{
  "descarga_total_mbps": 50,
  "subida_total_mbps": 50,
  "interfaz_wan": "ether1",
  "bridge_lan": "bridge1"
}
```

Todos los límites del árbol de colas se escalan en proporción
(el plan por defecto asume 100 Mbps). Verifica con `--dry-run` antes
de redesplegar.

---

## 🚨 Troubleshooting

**P: Kevin sigue teniendo lag aunque despliegue QoS**
R: Ejecuta diagnóstico, revisa si las reglas Mangle tienen >0 bytes. Si no, las reglas no están marcando.

**P: Queue Tree aparece pero no limita**
R: Este es un problema conocido de RouterOS v6.49.19 con tráfico local (bridge). Considera actualizar a RouterOS v7.

**P: ¿Puedo cambiar la prioridad de Kevin a aún más alta?**
R: Priority 1 es la máxima. Si quieres garantizar 100%, usa `limit-at` (pero ojo: rompe otros tráfico).

---

## 📝 Última actualización

- **Fecha:** 2026-07-02
- **RouterOS:** v6.49.19
- **Usuario:** Kevin KUTOGG (192.168.5.22)
- **Estado:** ✅ Funcional para descargas pesadas sin afectar stream
