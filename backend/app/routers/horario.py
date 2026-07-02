"""
routers/horario.py — Estado del corte de internet por horario
=============================================================

Espeja horario_internet.py --list como JSON: corte programado, si está
en curso AHORA (reloj del router) y lista blanca con columna EN RED.
Solo lecturas en esta fase; crear/eliminar llegan en la Fase 4.
"""

from datetime import datetime

from fastapi import APIRouter, Depends

from core.horario import (get_drop_rule, get_allow_rules, parse_drop_time,
                          corte_en_curso, get_router_now, load_whitelist,
                          DAYS_LABEL, ALL_DAYS)
from lib import build_device_map
from ..auth import require_session
from ..deps import get_api

router = APIRouter(prefix="/api", tags=["horario"],
                   dependencies=[Depends(require_session)])


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
