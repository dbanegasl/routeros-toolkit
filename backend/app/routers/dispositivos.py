"""
routers/dispositivos.py — Información e identificación de dispositivos
======================================================================

Espeja core/dispositivos.py: inventario (opción 1 del menú) y escaneo
avanzado (opción 30). Solo lecturas.
"""

from fastapi import APIRouter, Depends, Query

from core.dispositivos import (inventario_dispositivos, escanear_red,
                               filtrar_dispositivos)
from ..auth import require_session
from ..deps import get_api

router = APIRouter(prefix="/api", tags=["dispositivos"],
                   dependencies=[Depends(require_session)])


@router.get("/dispositivos")
def dispositivos(api=Depends(get_api)):
    """Inventario completo: leases DHCP + IPs estáticas detectadas en ARP."""
    dispositivos = inventario_dispositivos(api)
    return {"total": len(dispositivos), "dispositivos": dispositivos}


@router.get("/escaneo")
def escaneo(api=Depends(get_api),
            filtro: str = Query(default="",
                                description="apple | mobile | iot | unknown")):
    """Escaneo con clasificación (Apple, móvil, IoT, MAC privada…).

    No consulta macvendors.com (sin lookup online): responde solo con la
    base OUI local y el cache persistido.
    """
    resultados, desconocidos, _ = escanear_red(api)
    resultados = filtrar_dispositivos(resultados, filtro)
    return {
        "total": len(resultados),
        "sin_fabricante": len(desconocidos),
        "dispositivos": resultados,
    }
