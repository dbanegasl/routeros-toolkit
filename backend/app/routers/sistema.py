"""
routers/sistema.py — Estado del router, interfaces, validación y config
=======================================================================

Espeja core/monitoreo.py (sistema, interfaces) y sys_validar.py (la
validación completa como JSON estructurado). Solo lecturas.
"""

import os
from datetime import datetime

from fastapi import APIRouter, Depends

from core.monitoreo import resumen_sistema, get_iface_stats
from core.qos import load_qos_config, buscar_fasttrack, buscar_lease
from lib import get_router_datetime, get_lan_prefix, load_config
from ..auth import require_session
from ..deps import get_api

router = APIRouter(prefix="/api", tags=["sistema"],
                   dependencies=[Depends(require_session)])

# Sin candado ni router: healthcheck del compose (público, ver main.py)
salud_router = APIRouter(prefix="/api", tags=["sistema"])


@salud_router.get("/salud")
def salud():
    """Healthcheck del servicio (no toca el router)."""
    return {"estado": "ok"}


@router.get("/sistema")
def sistema(api=Depends(get_api)):
    """CPU, RAM, disco, uptime, interfaces activas y dispositivos DHCP."""
    info = resumen_sistema(api)
    if info is None:
        return {"error": "El router no reportó /system/resource"}
    return info


@router.get("/interfaces")
def interfaces(api=Depends(get_api)):
    """Estadísticas de tráfico acumulado por interfaz."""
    stats = get_iface_stats(api)
    return {
        "interfaces": [
            {
                "nombre": nombre,
                "tipo": s.get("type", "?"),
                "tx_bytes": int(s.get("tx-byte", 0)),
                "rx_bytes": int(s.get("rx-byte", 0)),
                "activa": s.get("running") == "true",
            }
            for nombre, s in sorted(stats.items())
        ]
    }


@router.get("/config")
def config_publica(api=Depends(get_api)):
    """Configuración visible de la app — sin secretos (ni password del
    router ni hashes)."""
    cfg = load_config()
    qos = load_qos_config()
    return {
        "router": {"host": cfg["host"], "port": cfg["port"],
                   "usuario": cfg["username"]},
        "lan_prefix": get_lan_prefix(api),
        "qos": {
            "dispositivo_prioritario": {
                "nombre": qos["dispositivo_prioritario"]["nombre"],
                "ip": qos["dispositivo_prioritario"]["ip"],
            },
            "descarga_total_mbps": qos["descarga_total_mbps"],
            "subida_total_mbps": qos["subida_total_mbps"],
        },
    }


@router.get("/validacion")
def validacion(api=Depends(get_api)):
    """sys_validar como JSON estructurado: identidad, interfaces, QoS,
    FastTrack, dispositivo prioritario y deriva del reloj."""
    identity = api.command("/system/identity/print")
    resources = api.command("/system/resource/print")
    interfaces = api.command("/interface/print")
    addresses = api.command("/ip/address/print")
    mangle = api.command("/ip/firewall/mangle/print")
    queues = api.command("/queue/tree/print")
    simple = api.command("/queue/simple/print")
    fasttrack = buscar_fasttrack(api)

    res = resources[0] if resources else {}

    # Dispositivo prioritario del QoS (si hay config)
    qos_cfg = load_qos_config()
    device = qos_cfg["dispositivo_prioritario"]
    lease = None
    if device.get("mac"):
        leases = buscar_lease(api, device["mac"])
        if leases:
            lease = {
                "ip": leases[0].get("address", ""),
                "mac": leases[0].get("mac-address", ""),
                "hostname": leases[0].get("host-name", ""),
            }

    # Reloj y deriva — los cortes por horario dependen de la hora del router
    reloj_router = get_router_datetime(api)
    ahora = datetime.now()
    deriva = (abs((reloj_router - ahora).total_seconds())
              if reloj_router else None)
    try:
        ntp = api.command("/system/ntp/client/print")
        ntp_habilitado = bool(ntp) and ntp[0].get("enabled") == "true"
    except RuntimeError:
        ntp_habilitado = None      # paquete NTP no instalado en esta versión

    qos_activo = bool(mangle or queues or simple)

    return {
        "identidad": {
            "nombre": identity[0].get("name", "?") if identity else "?",
            "version": res.get("version", "?"),
            "equipo": res.get("board-name", "?"),
            "cpu": res.get("cpu-count", "?"),
            "ram_total": int(res.get("total-memory", 0)),
        },
        "interfaces": [
            {"nombre": i.get("name", "?"),
             "activa": i.get("running") == "true",
             "mtu": i.get("mtu", "?")}
            for i in interfaces
        ],
        "direcciones": [
            {"direccion": a.get("address", "?"),
             "interfaz": a.get("interface", "?")}
            for a in addresses
        ],
        "dispositivo_prioritario": {
            "nombre": device.get("nombre", "?"),
            "mac": device.get("mac", ""),
            "lease": lease,
        },
        "fasttrack": [
            {"comentario": r.get("comment", ""),
             "deshabilitado": r.get("disabled") == "true"}
            for r in fasttrack
        ],
        "qos": {
            "mangle": len(mangle),
            "queue_tree": len(queues),
            "queue_simple": len(simple),
            "activo": qos_activo,
        },
        "reloj": {
            "hora_router": (reloj_router.isoformat(timespec="seconds")
                            if reloj_router else None),
            "hora_servidor": ahora.isoformat(timespec="seconds"),
            "deriva_segundos": round(deriva) if deriva is not None else None,
            "sincronizado": deriva is not None and deriva <= 120,
            "ntp_habilitado": ntp_habilitado,
        },
    }
