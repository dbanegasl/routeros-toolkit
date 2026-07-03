"""
routers/horario.py — Corte de internet por horario ⚠️
=====================================================

Espeja horario_internet.py: estado (corte + en-curso + whitelist con
EN RED), crear/reemplazar el corte, eliminarlo, y gestionar la lista
blanca persistente. Mismas reglas etiquetadas del CLI
(HORARIO-INTERNET / HORARIO-PERMITIDO); solo se tocan las propias.
Las escrituras exigen {"confirmar": true}.
"""

import re
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.horario import (get_drop_rule, get_allow_rules, parse_drop_time,
                          corte_en_curso, get_router_now, load_whitelist,
                          save_whitelist, remove_all_rules, apply_all_rules,
                          aplicar_solo_whitelist, get_wan_interface,
                          DAYS_LABEL, ALL_DAYS)
from lib import build_device_map
from ..auth import require_session
from ..deps import get_api

router = APIRouter(prefix="/api", tags=["horario"],
                   dependencies=[Depends(require_session)])

RE_HORA = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")
RE_MAC = re.compile(r"^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$")


def _exigir_confirmacion(confirmar: bool):
    if not confirmar:
        raise HTTPException(
            status_code=400,
            detail="Esta acción modifica el firewall del router: "
                   "envía \"confirmar\": true para ejecutarla.")


def _validar_hora(valor: str, campo: str) -> str:
    if not RE_HORA.match(valor):
        raise HTTPException(
            status_code=400,
            detail=f"'{valor}' no es una hora válida para {campo} (HH:MM).")
    return f"{valor}:00"


def _validar_dias(dias: list) -> list:
    if not dias:
        return list(ALL_DAYS)
    invalidos = [d for d in dias if d not in ALL_DAYS]
    if invalidos:
        raise HTTPException(
            status_code=400,
            detail=f"Días inválidos: {', '.join(invalidos)} "
                   f"(usa {', '.join(ALL_DAYS)}).")
    # Orden canónico lun→dom, sin duplicados
    return [d for d in ALL_DAYS if d in dias]


def _macs_whitelist_actual(api) -> tuple:
    """(macs aplicadas ∪ archivo, whitelist del archivo)."""
    stored = load_whitelist()
    aplicadas = {r.get("src-mac-address", "").upper()
                 for r in get_allow_rules(api)}
    return sorted(aplicadas | set(stored)), stored


@router.get("/horario")
def horario(api=Depends(get_api)):
    drop = get_drop_rule(api)
    allows = get_allow_rules(api)
    stored = load_whitelist()
    devices = build_device_map(api, by="mac")

    # Lista blanca: unión de reglas aplicadas y archivo persistido
    applied = {r.get("src-mac-address", "").upper(): r for r in allows}
    todas_macs = sorted(set(applied) | set(stored))
    whitelist = []
    for mac in todas_macs:
        dev = devices.get(mac)
        en_red = dev is not None
        whitelist.append({
            "mac": mac,
            "nombre": ((dev.get("name") if en_red else None)
                       or stored.get(mac, {}).get("nombre") or ""),
            "ip": dev["ip"] if en_red else None,
            "en_red": en_red,
            "aplicada_en_router": mac in applied,
            "bytes": int(applied.get(mac, {}).get("bytes", 0)),
        })

    if not drop:
        return {"corte": None, "en_curso": False, "whitelist": whitelist}

    start, end, days = parse_drop_time(drop)

    # ¿Bloqueando ahora? — reloj del router; si no se puede leer, el local
    ahora = get_router_now(api)
    fuente_reloj = "router"
    if ahora is None:
        local = datetime.now()
        ahora = (local.hour * 60 + local.minute,
                 ALL_DAYS[local.weekday()],
                 f"{local.hour:02d}:{local.minute:02d}")
        fuente_reloj = "servidor"
    now_min, today, hhmm = ahora

    return {
        "corte": {
            "inicio": start[:5],
            "fin": end[:5],
            "dias": days,
            "dias_etiquetas": [DAYS_LABEL.get(d, d) for d in days],
            "interfaz_wan": drop.get("out-interface", ""),
            "paquetes_bloqueados": int(drop.get("packets", 0)),
            "bytes_bloqueados": int(drop.get("bytes", 0)),
        },
        "en_curso": corte_en_curso(start, end, days, now_min, today),
        "hora_actual": hhmm,
        "fuente_reloj": fuente_reloj,
        "whitelist": whitelist,
    }


# ---------------------------------------------------------------------------
# Escrituras ⚠️
# ---------------------------------------------------------------------------

class HorarioBody(BaseModel):
    inicio: str                      # "HH:MM"
    fin: str                         # "HH:MM"
    dias: list[str] = []             # vacío = todos los días
    confirmar: bool = False


class ConfirmarBody(BaseModel):
    confirmar: bool = False


class WhitelistBody(BaseModel):
    macs: list[str]
    confirmar: bool = False


@router.post("/horario")
def crear_horario(body: HorarioBody, api=Depends(get_api)):
    """⚠️ Crea (o reemplaza) el corte. La lista blanca vigente —reglas
    aplicadas ∪ config/whitelist.json— se conserva y se reaplica."""
    _exigir_confirmacion(body.confirmar)
    inicio = _validar_hora(body.inicio, "inicio")
    fin = _validar_hora(body.fin, "fin")
    if inicio == fin:
        raise HTTPException(status_code=400,
                            detail="El inicio y el fin no pueden ser iguales.")
    dias = _validar_dias(body.dias)

    wan = get_wan_interface(api)
    if not wan:
        raise HTTPException(
            status_code=400,
            detail="No se pudo detectar la interfaz WAN (ruta 0.0.0.0/0).")

    macs, stored = _macs_whitelist_actual(api)
    reemplazado = get_drop_rule(api) is not None
    remove_all_rules(api)
    apply_all_rules(api, wan, inicio, fin, dias, macs)
    if macs:
        save_whitelist(set(macs), build_device_map(api, by="mac"), stored)

    return {
        "mensaje": ("Corte reemplazado." if reemplazado else "Corte programado."),
        "inicio": inicio[:5],
        "fin": fin[:5],
        "dias": dias,
        "interfaz_wan": wan,
        "whitelist_aplicada": len(macs),
    }


@router.delete("/horario")
def eliminar_horario(body: ConfirmarBody, api=Depends(get_api)):
    """⚠️ Elimina el corte y las reglas ACCEPT. La lista blanca sigue
    guardada en config/whitelist.json y se reaplica al reprogramar."""
    _exigir_confirmacion(body.confirmar)
    eliminadas = remove_all_rules(api)
    return {
        "mensaje": ("Corte eliminado. Internet sin restricciones."
                    if eliminadas else "No había reglas de corte."),
        "reglas_eliminadas": eliminadas,
        "whitelist_guardada": len(load_whitelist()),
    }


@router.get("/horario/whitelist")
def ver_whitelist(api=Depends(get_api)):
    """Lista blanca: archivo ∪ reglas aplicadas, con EN RED."""
    stored = load_whitelist()
    aplicadas = {r.get("src-mac-address", "").upper()
                 for r in get_allow_rules(api)}
    devices = build_device_map(api, by="mac")
    macs = sorted(set(stored) | aplicadas)
    return {
        "dispositivos": [
            {
                "mac": mac,
                "nombre": ((devices.get(mac) or {}).get("name")
                           or stored.get(mac, {}).get("nombre") or ""),
                "ip": (devices.get(mac) or {}).get("ip"),
                "en_red": mac in devices,
                "aplicada_en_router": mac in aplicadas,
            }
            for mac in macs
        ]
    }


@router.put("/horario/whitelist")
def guardar_whitelist(body: WhitelistBody, api=Depends(get_api)):
    """⚠️ Reemplaza la lista blanca: persiste en config/whitelist.json y
    reconstruye las reglas (con el corte vigente si existe)."""
    _exigir_confirmacion(body.confirmar)
    macs = set()
    for mac in body.macs:
        if not RE_MAC.match(mac):
            raise HTTPException(status_code=400,
                                detail=f"'{mac}' no es una MAC válida.")
        macs.add(mac.upper())

    stored = load_whitelist()
    devices = build_device_map(api, by="mac")
    # Persistir primero: el archivo es la fuente de verdad
    save_whitelist(macs, devices, stored)

    drop = get_drop_rule(api)
    if drop:
        inicio, fin, dias = parse_drop_time(drop)
        wan = drop.get("out-interface", "") or get_wan_interface(api)
        remove_all_rules(api)
        apply_all_rules(api, wan, inicio, fin, dias, sorted(macs))
        estado = "aplicada con el corte vigente"
    else:
        aplicar_solo_whitelist(api, get_wan_interface(api), sorted(macs))
        estado = "guardada (sin corte programado aún)"

    return {"mensaje": f"Lista blanca {estado}.",
            "dispositivos": len(macs)}
