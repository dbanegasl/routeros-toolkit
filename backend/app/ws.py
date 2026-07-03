"""
ws.py — WebSockets con muestreo compartido (/ws/monitor y /ws/log)
==================================================================

Un solo bucle de muestreo por stream, sin importar cuántas pestañas
estén conectadas: el primer cliente lo arranca, el último lo detiene,
y todos reciben el MISMO snapshot. El muestreo usa usar_api de deps:
la MISMA conexión persistente que las peticiones HTTP — navegar entre
páginas del panel no genera logins/logouts en el syslog del router.

Autenticación: la misma cookie de sesión del resto de la API; sin
sesión válida el socket se cierra con código 4401.
"""

import asyncio
import os
import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from starlette.concurrency import run_in_threadpool

from core.monitoreo import snapshot_consumo, obtener_log, nivel_log
from core.qos import filtrar_colas_qos
from lib import build_name_map, get_lan_prefix
from .auth import _sesion_valida
from .deps import usar_api

router = APIRouter()

CIERRE_SIN_SESION = 4401


def _intervalo() -> float:
    """Segundos entre muestreos (APP_WS_INTERVALO, default 3)."""
    return float(os.environ.get("APP_WS_INTERVALO", 3))


class Muestreador:
    """Bucle de muestreo compartido entre todos los clientes de un stream."""

    def __init__(self, muestrear):
        self.muestrear = muestrear      # función BLOQUEANTE api → dict
        self.clientes: set[WebSocket] = set()
        self._tarea: asyncio.Task | None = None

    async def conectar(self, ws: WebSocket):
        self.clientes.add(ws)
        if self._tarea is None or self._tarea.done():
            self._tarea = asyncio.create_task(self._bucle())

    def desconectar(self, ws: WebSocket):
        self.clientes.discard(ws)
        if not self.clientes and self._tarea:
            self._tarea.cancel()
            self._tarea = None

    def _tomar_muestra(self) -> dict:
        """Corre en el threadpool, con la conexión compartida de deps."""
        return usar_api(self.muestrear)

    async def _bucle(self):
        while self.clientes:
            try:
                datos = await run_in_threadpool(self._tomar_muestra)
            except Exception as e:
                datos = {"error": f"No se pudo leer el router: {e}"}
            datos["ts"] = time.time()
            for ws in list(self.clientes):
                try:
                    await ws.send_json(datos)
                except Exception:
                    self.clientes.discard(ws)
            await asyncio.sleep(_intervalo())


# ---------------------------------------------------------------------------
# Streams
# ---------------------------------------------------------------------------

class _EstadoMonitor:
    """Cache del muestreo de monitor: nombres (lento, cada 60 s) y la
    muestra anterior de interfaces para calcular velocidades reales."""
    nombres: dict = {}
    nombres_ts: float = 0.0
    ifaces_prev: dict = {}
    ifaces_prev_ts: float = 0.0


def _muestra_monitor(api) -> dict:
    ahora = time.time()
    if ahora - _EstadoMonitor.nombres_ts > 60:
        _EstadoMonitor.nombres = build_name_map(api)
        _EstadoMonitor.nombres_ts = ahora

    lan = get_lan_prefix(api)
    data, total_conns = snapshot_consumo(api, lan)
    dispositivos = sorted(
        (
            {
                "ip": ip,
                "nombre": _EstadoMonitor.nombres.get(ip, ip),
                "dl_rate": d["dl_rate"],
                "ul_rate": d["ul_rate"],
                "dl_total": d["dl_total"],
                "ul_total": d["ul_total"],
                "conexiones": d["conns"],
            }
            for ip, d in data.items()
            if d["dl_total"] + d["ul_total"] > 0
        ),
        key=lambda x: x["dl_rate"] + x["ul_rate"],
        reverse=True,
    )

    # Interfaces: velocidad real por delta entre muestras consecutivas
    stats = {i["name"]: i for i in api.command("/interface/print")}
    dt = ahora - _EstadoMonitor.ifaces_prev_ts
    interfaces = []
    for nombre, s in sorted(stats.items()):
        tx, rx = int(s.get("tx-byte", 0)), int(s.get("rx-byte", 0))
        prev = _EstadoMonitor.ifaces_prev.get(nombre)
        if prev and 0 < dt < 60:
            tx_rate = max(0, tx - prev[0]) * 8 / dt
            rx_rate = max(0, rx - prev[1]) * 8 / dt
        else:
            tx_rate = rx_rate = 0
        interfaces.append({
            "nombre": nombre,
            "activa": s.get("running") == "true",
            "tx_rate": round(tx_rate),
            "rx_rate": round(rx_rate),
            "tx_total": tx,
            "rx_total": rx,
        })
        _EstadoMonitor.ifaces_prev[nombre] = (tx, rx)
    _EstadoMonitor.ifaces_prev_ts = ahora

    return {
        "conexiones_totales": total_conns,
        "dispositivos": dispositivos[:20],
        "interfaces": interfaces,
    }


def _muestra_log(api) -> dict:
    entradas = obtener_log(api, lineas=100)
    return {
        "entradas": [
            {
                "hora": e.get("time", ""),
                "topics": e.get("topics", ""),
                "mensaje": e.get("message", ""),
                "nivel": nivel_log(e.get("topics", "")),
            }
            for e in entradas
        ]
    }


class _EstadoQos:
    """Muestra anterior de cada cola QoS para calcular velocidad real."""
    prev: dict = {}       # nombre de cola → (bytes, timestamp)


def _muestra_qos(api) -> dict:
    """Colas QoS con velocidad (bits/s) por delta entre muestras."""
    ahora = time.time()
    colas = []
    for q in filtrar_colas_qos(api.command("/queue/tree/print")):
        nombre = q.get("name", "")
        total = int(q.get("bytes", 0))
        previa = _EstadoQos.prev.get(nombre)
        rate = 0.0
        if previa and 0 < ahora - previa[1] < 60:
            rate = max(0, total - previa[0]) * 8 / (ahora - previa[1])
        _EstadoQos.prev[nombre] = (total, ahora)
        colas.append({
            "nombre": nombre,
            "mark": q.get("packet-mark", ""),
            "bytes": total,
            "rate": round(rate),
            "descartados": int(q.get("dropped", 0)),
            "maximo": q.get("max-limit", ""),
        })
    return {"activo": bool(colas), "colas": colas}


muestreador_monitor = Muestreador(_muestra_monitor)
muestreador_log = Muestreador(_muestra_log)
muestreador_qos = Muestreador(_muestra_qos)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

async def _atender(ws: WebSocket, muestreador: Muestreador):
    await ws.accept()
    if not _sesion_valida(ws.cookies.get("sesion", "")):
        await ws.close(code=CIERRE_SIN_SESION, reason="Sesión inválida")
        return
    await muestreador.conectar(ws)
    try:
        # Mantener el socket abierto; los datos van solo servidor → cliente
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        muestreador.desconectar(ws)


@router.websocket("/ws/monitor")
async def ws_monitor(ws: WebSocket):
    await _atender(ws, muestreador_monitor)


@router.websocket("/ws/log")
async def ws_log(ws: WebSocket):
    await _atender(ws, muestreador_log)


@router.websocket("/ws/qos")
async def ws_qos(ws: WebSocket):
    await _atender(ws, muestreador_qos)
