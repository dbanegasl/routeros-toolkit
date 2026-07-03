"""
routers/respaldos.py — Snapshots locales y respaldo completo del router
=======================================================================

Espeja mant_respaldo.py sobre core/respaldo.py:
- GET  /api/respaldos           → snapshots locales + .backup del router
- POST /api/respaldos {full}    → snapshot local; con full:true además
                                  crea un .backup EN el router.

El snapshot es solo lectura sobre el router; --full escribe un archivo
en el router (igual que el CLI, sin confirmación adicional: no altera
la configuración). El directorio local es backups/ (MIKROTIK_BACKUP_DIR).
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from core.respaldo import (build_snapshot, save_snapshot,
                           create_router_backup, list_router_backups,
                           list_local_snapshots)
from ..auth import require_session
from ..deps import get_api

router = APIRouter(prefix="/api", tags=["respaldos"],
                   dependencies=[Depends(require_session)])


class RespaldoBody(BaseModel):
    full: bool = False


@router.get("/respaldos")
def respaldos(api=Depends(get_api)):
    """Snapshots locales (recientes primero) y .backup en el router."""
    return {
        "locales": list(reversed(list_local_snapshots())),
        "router": [
            {
                "nombre": f.get("name", ""),
                "bytes": int(f.get("size", 0)),
                "creado": f.get("creation-time", ""),
            }
            for f in list_router_backups(api)
        ],
    }


@router.post("/respaldos")
def crear_respaldo(body: RespaldoBody, api=Depends(get_api)):
    """Crea el snapshot local; con full:true además el .backup completo
    en el router (descargable desde Winbox → Files)."""
    snapshot = build_snapshot(api)
    ruta = save_snapshot(snapshot)
    respuesta = {
        "mensaje": "Snapshot local guardado.",
        "snapshot": ruta.name,
        "secciones": {nombre: len(items)
                      for nombre, items in snapshot["secciones"].items()},
        "backup_router": None,
    }
    if body.full:
        respuesta["backup_router"] = create_router_backup(api)
        respuesta["mensaje"] = ("Snapshot local guardado y respaldo "
                                "completo creado en el router.")
    return respuesta
