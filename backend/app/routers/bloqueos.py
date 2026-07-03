"""
routers/bloqueos.py — Bloquear / desbloquear IPs en el firewall ⚠️
==================================================================

Espeja core/bloqueos.py (mant_bloqueo): reglas DROP etiquetadas
BLOQUEADO-POR-MENU-*, solo se gestionan las propias. Las escrituras
exigen {"confirmar": true} — el espejo del dict CONFIRMAR del menú.
"""

import ipaddress

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.bloqueos import (reglas_bloqueo, buscar_bloqueo,
                           bloquear_ip, desbloquear_ip)
from ..auth import require_session
from ..deps import get_api

router = APIRouter(prefix="/api", tags=["bloqueos"],
                   dependencies=[Depends(require_session)])


class BloqueoBody(BaseModel):
    ip: str
    confirmar: bool = False


class ConfirmarBody(BaseModel):
    confirmar: bool = False


def _exigir_confirmacion(confirmar: bool):
    if not confirmar:
        raise HTTPException(
            status_code=400,
            detail="Esta acción modifica el firewall del router: "
                   "envía \"confirmar\": true para ejecutarla.")


def _validar_ip(ip: str) -> str:
    try:
        return str(ipaddress.ip_address(ip))
    except ValueError:
        raise HTTPException(status_code=400,
                            detail=f"'{ip}' no es una dirección IP válida.")


@router.get("/bloqueos")
def listar(api=Depends(get_api)):
    """IPs bloqueadas por este toolkit (reglas propias, nada más)."""
    reglas = reglas_bloqueo(api)
    return {
        "total": len(reglas),
        "bloqueos": [
            {"id": r.get(".id", ""), "ip": r.get("src-address", ""),
             "comentario": r.get("comment", "")}
            for r in reglas
        ],
    }


@router.post("/bloqueos")
def bloquear(body: BloqueoBody, api=Depends(get_api)):
    """⚠️ Agrega la regla DROP para esta IP (al inicio de forward)."""
    _exigir_confirmacion(body.confirmar)
    ip = _validar_ip(body.ip)
    if buscar_bloqueo(api, ip):
        raise HTTPException(status_code=409,
                            detail=f"{ip} ya está bloqueada.")
    bloquear_ip(api, ip)
    return {"mensaje": f"IP bloqueada: {ip}"}


@router.delete("/bloqueos/{ip}")
def desbloquear(ip: str, body: ConfirmarBody, api=Depends(get_api)):
    """⚠️ Elimina la(s) regla(s) de bloqueo de esta IP."""
    _exigir_confirmacion(body.confirmar)
    ip = _validar_ip(ip)
    eliminadas = desbloquear_ip(api, ip)
    if not eliminadas:
        raise HTTPException(status_code=404,
                            detail=f"No hay regla de bloqueo para {ip}.")
    return {"mensaje": f"Desbloqueo exitoso: {ip}",
            "reglas_eliminadas": eliminadas}
