"""
routers/qos.py — Plan QoS: visor (dry-run), despliegue ⚠️, diagnóstico y reset ⚠️
=================================================================================

Espeja qos_desplegar.py / qos_diagnostico.py / qos_reset.py sobre los
mismos builders de core/qos.py — el plan que muestra GET /api/qos/plan
es EXACTAMENTE el que aplica el CLI.

Diferencia deliberada con el CLI: la limpieza previa del despliegue es
SELECTIVA (solo elementos etiquetados 'QoS *' / 'QoS_*, DL-*, UL-*');
las reglas Mangle y colas ajenas se preservan, igual que en el reset.
Las escrituras exigen {"confirmar": true}.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.qos import (load_qos_config, build_mangle_rules, build_queue_tree,
                      buscar_lease, fijar_ip_estatica, buscar_fasttrack,
                      deshabilitar_fasttrack, rehabilitar_fasttrack,
                      eliminar_reglas_mangle, eliminar_colas,
                      aplicar_reglas_mangle, crear_colas,
                      filtrar_mangle_qos, filtrar_colas_qos,
                      agrupar_por_prioridad)
from ..auth import require_session
from ..deps import get_api

router = APIRouter(prefix="/api", tags=["qos"],
                   dependencies=[Depends(require_session)])


class ConfirmarBody(BaseModel):
    confirmar: bool = False


def _exigir_confirmacion(confirmar: bool):
    if not confirmar:
        raise HTTPException(
            status_code=400,
            detail="Esta acción modifica el firewall y las colas del router: "
                   "envía \"confirmar\": true para ejecutarla.")


def _estado(api) -> dict:
    """Estado actual del QoS en el router (solo elementos etiquetados)."""
    mangle = api.command("/ip/firewall/mangle/print")
    colas = api.command("/queue/tree/print")
    ft = buscar_fasttrack(api)
    qos_mangle = filtrar_mangle_qos(mangle)
    qos_colas = filtrar_colas_qos(colas)
    return {
        "activo": bool(qos_mangle or qos_colas),
        "mangle_qos": len(qos_mangle),
        "mangle_ajenas": len(mangle) - len(qos_mangle),
        "colas_qos": len(qos_colas),
        "colas_ajenas": len(colas) - len(qos_colas),
        "fasttrack_activo": any(r.get("disabled") != "true" for r in ft),
        "fasttrack_reglas": len(ft),
    }


@router.get("/qos/plan")
def plan(api=Depends(get_api)):
    """Dry-run: el plan completo (mismos builders que el CLI) sin tocar
    el router, más el estado actual y el lease del dispositivo."""
    qos = load_qos_config()
    device = qos["dispositivo_prioritario"]
    leases = buscar_lease(api, device["mac"])
    return {
        "config": {
            "dispositivo": device,
            "interfaz_wan": qos["interfaz_wan"],
            "bridge_lan": qos["bridge_lan"],
            "descarga_total_mbps": qos["descarga_total_mbps"],
            "subida_total_mbps": qos["subida_total_mbps"],
            "umbral_bulk_mb": qos["umbral_bulk_mb"],
        },
        "lease": {
            "existe": bool(leases),
            "ip_actual": leases[0].get("address", "") if leases else None,
        },
        "estado": _estado(api),
        "mangle": build_mangle_rules(qos),
        "colas": build_queue_tree(qos),
    }


@router.get("/qos/diagnostico")
def diagnostico(api=Depends(get_api)):
    """Contadores reales: reglas Mangle agrupadas por prioridad y colas
    Queue Tree con bytes/paquetes/descartes (espejo de qos_diagnostico)."""
    mangle = filtrar_mangle_qos(api.command("/ip/firewall/mangle/print"))
    colas = filtrar_colas_qos(api.command("/queue/tree/print"))
    marcas = agrupar_por_prioridad(mangle)
    return {
        "estado": _estado(api),
        "marcas": [
            {
                "prioridad": prioridad,
                "bytes": datos["bytes"],
                "paquetes": datos["packets"],
                "reglas": [
                    {"comentario": r["comment"], "bytes": r["bytes"],
                     "paquetes": r["packets"]}
                    for r in datos["rules"]
                ],
            }
            for prioridad, datos in sorted(marcas.items())
        ],
        "colas": [
            {
                "nombre": q.get("name", ""),
                "padre": q.get("parent", ""),
                "mark": q.get("packet-mark", ""),
                "bytes": int(q.get("bytes", 0)),
                "paquetes": int(q.get("packets", 0)),
                "descartados": int(q.get("dropped", 0)),
                "limite": q.get("limit-at", ""),
                "maximo": q.get("max-limit", ""),
            }
            for q in colas
        ],
    }


# ---------------------------------------------------------------------------
# Escrituras ⚠️
# ---------------------------------------------------------------------------

@router.post("/qos/desplegar")
def desplegar(body: ConfirmarBody, api=Depends(get_api)):
    """⚠️ Despliega el plan QoS completo: fija la IP del dispositivo
    prioritario, deshabilita FastTrack, limpia el QoS previo (solo lo
    etiquetado) y aplica reglas Mangle + Queue Tree."""
    _exigir_confirmacion(body.confirmar)
    qos = load_qos_config()
    device = qos["dispositivo_prioritario"]

    # 1. IP fija por MAC (actualiza el lease si existe, si no lo crea)
    leases = buscar_lease(api, device["mac"])
    lease_id = (leases[0].get(".id") or None) if leases else None
    fijar_ip_estatica(api, device, lease_id=lease_id)

    # 2. Sin FastTrack el Mangle y las colas sí ven el tráfico
    ft_deshabilitadas = len(deshabilitar_fasttrack(api))

    # 3. Limpiar despliegue previo (solo elementos etiquetados del QoS)
    mangle_previas = eliminar_reglas_mangle(
        api, filtrar_mangle_qos(api.command("/ip/firewall/mangle/print")))
    colas_previas = eliminar_colas(
        api, filtrar_colas_qos(api.command("/queue/tree/print")))

    # 4-5. Aplicar el plan (los mismos builders del dry-run)
    res_mangle = aplicar_reglas_mangle(api, build_mangle_rules(qos))
    res_colas = crear_colas(api, build_queue_tree(qos))
    errores = (
        [f"Mangle '{r['comment']}': {e}" for r, e in res_mangle if e] +
        [f"Cola '{q['name']}': {e}" for q, e in res_colas if e]
    )

    return {
        "mensaje": ("Plan QoS desplegado." if not errores else
                    f"Plan QoS desplegado con {len(errores)} error(es)."),
        "dispositivo": device["nombre"],
        "fasttrack_deshabilitadas": ft_deshabilitadas,
        "mangle_previas_eliminadas": mangle_previas,
        "colas_previas_eliminadas": colas_previas,
        "mangle_aplicadas": sum(1 for _, e in res_mangle if e is None),
        "colas_creadas": sum(1 for _, e in res_colas if e is None),
        "errores": errores,
    }


@router.delete("/qos")
def reset(body: ConfirmarBody, api=Depends(get_api)):
    """⚠️ Reset selectivo (espejo de qos_reset.py): elimina SOLO los
    elementos etiquetados del QoS y rehabilita FastTrack. Las reglas de
    otros gestores (bloqueos, horario, manuales) quedan intactas."""
    _exigir_confirmacion(body.confirmar)
    mangle_eliminadas = eliminar_reglas_mangle(
        api, filtrar_mangle_qos(api.command("/ip/firewall/mangle/print")))
    colas_eliminadas = eliminar_colas(
        api, filtrar_colas_qos(api.command("/queue/tree/print")))
    ft_habilitadas, ft_total = rehabilitar_fasttrack(
        api, solo_deshabilitadas=True)

    if mangle_eliminadas or colas_eliminadas:
        mensaje = "QoS eliminado. Red en estado limpio."
    else:
        mensaje = "No había QoS desplegado."
    return {
        "mensaje": mensaje,
        "mangle_eliminadas": mangle_eliminadas,
        "colas_eliminadas": colas_eliminadas,
        "fasttrack_rehabilitadas": ft_habilitadas,
        "fasttrack_reglas": ft_total,
    }
