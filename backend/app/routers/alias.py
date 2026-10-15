"""
routers/alias.py — Alias de dispositivos (nombre propio por MAC)
================================================================

El alias vive en config/alias.json (compartido con el CLI) y tiene
prioridad sobre el hostname/fabricante en todo el toolkit: Dispositivos,
lista blanca, Monitoreo y los scripts. No toca el router, así que no
exige {"confirmar": true}.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from lib import load_aliases, set_alias
from .. import ws
from ..auth import require_session

router = APIRouter(prefix="/api", tags=["alias"],
                   dependencies=[Depends(require_session)])


class AliasBody(BaseModel):
    alias: str = ""                  # vacío = quitar el alias


@router.get("/alias")
def ver_alias():
    """Mapa MAC → alias."""
    return {"alias": load_aliases()}


@router.put("/alias/{mac}")
def guardar_alias(mac: str, body: AliasBody):
    """Guarda el alias de una MAC (alias vacío lo quita)."""
    try:
        aliases = set_alias(mac, body.alias)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    ws.invalidar_nombres()           # el monitor en vivo lo refleja ya
    mac = mac.strip().upper()
    alias = aliases.get(mac, "")
    return {
        "mensaje": (f"Alias guardado: {alias}." if alias
                    else "Alias eliminado."),
        "mac": mac,
        "alias": alias,
    }
