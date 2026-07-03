"""
routers/monitoreo.py — Consumo de red por dispositivo
=====================================================

Espeja core/monitoreo.py (mon_consumo): snapshot del connection tracking
agrupado por IP LAN. El monitoreo en vivo (WebSocket) llega en la Fase 3.
"""

from fastapi import APIRouter, Depends, Query

from core.monitoreo import snapshot_consumo, ordenar_consumo
from lib import build_name_map, get_lan_prefix
from ..auth import require_session
from ..deps import get_api

router = APIRouter(prefix="/api", tags=["monitoreo"],
                   dependencies=[Depends(require_session)])


@router.get("/consumo")
def consumo(api=Depends(get_api),
            orden: str = Query(default="actual",
                               pattern="^(actual|total)$",
                               description="actual = velocidad ahora · "
                                           "total = acumulado de sesión"),
            top: int = Query(default=15, ge=1, le=100)):
    """Top consumidores: velocidad actual y acumulado por dispositivo."""
    lan = get_lan_prefix(api)
    nombres = build_name_map(api)
    data, total_conns = snapshot_consumo(api, lan)
    ranked = ordenar_consumo(data, por="rate" if orden == "actual" else "total")

    dispositivos = [
        {
            "ip": ip,
            "nombre": nombres.get(ip, ip),
            "dl_rate": d["dl_rate"],
            "ul_rate": d["ul_rate"],
            "dl_total": d["dl_total"],
            "ul_total": d["ul_total"],
            "conexiones": d["conns"],
        }
        for ip, d in ranked
        if d["dl_total"] + d["ul_total"] > 0
    ][:top]

    return {"conexiones_totales": total_conns,
            "dispositivos": dispositivos}
