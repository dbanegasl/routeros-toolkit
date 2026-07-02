"""
core/respaldo.py — Snapshot local y respaldo completo del router
================================================================

Lógica extraída de mant_respaldo.py:
- build_snapshot / save_snapshot: JSON local (solo lectura sobre el router)
  con las secciones que este toolkit puede modificar.
- create_router_backup: /system/backup/save (el .backup queda EN el router).
"""

import json
import os
from datetime import datetime
from pathlib import Path

from lib import get_router_datetime

# Secciones que los scripts de este toolkit pueden modificar (bloqueos,
# horario, QoS, respaldos) más contexto útil para reconstruir a mano.
SNAPSHOT_SECTIONS = {
    "identidad":       "/system/identity/print",
    "direcciones_ip":  "/ip/address/print",
    "firewall_filter": "/ip/firewall/filter/print",
    "firewall_mangle": "/ip/firewall/mangle/print",
    "firewall_nat":    "/ip/firewall/nat/print",
    "queue_tree":      "/queue/tree/print",
    "queue_simple":    "/queue/simple/print",
    "dhcp_leases":     "/ip/dhcp-server/lease/print",
    "schedulers":      "/system/scheduler/print",
}


def get_backup_dir() -> Path:
    """backups/ en la raíz del proyecto, o MIKROTIK_BACKUP_DIR."""
    override = os.environ.get("MIKROTIK_BACKUP_DIR")
    if override:
        return Path(override)
    return Path(__file__).resolve().parent.parent / "backups"


def snapshot_filename(now: datetime) -> str:
    return f"snapshot_{now:%Y-%m-%d_%H%M%S}.json"


def build_snapshot(api) -> dict:
    """Arma el snapshot completo (dict listo para serializar). Solo lectura."""
    resources = api.command("/system/resource/print")
    reloj = get_router_datetime(api)
    snapshot = {
        "meta": {
            "creado": datetime.now().isoformat(timespec="seconds"),
            "hora_router": reloj.isoformat(timespec="seconds") if reloj else None,
            "routeros": resources[0].get("version", "?") if resources else "?",
            "equipo": resources[0].get("board-name", "?") if resources else "?",
        },
        "secciones": {},
    }
    for nombre, cmd in SNAPSHOT_SECTIONS.items():
        snapshot["secciones"][nombre] = api.command(cmd)
    return snapshot


def save_snapshot(snapshot: dict) -> Path:
    """Escribe el snapshot en backups/ y retorna la ruta."""
    backup_dir = get_backup_dir()
    backup_dir.mkdir(parents=True, exist_ok=True)
    ruta = backup_dir / snapshot_filename(datetime.now())
    with open(ruta, "w") as f:
        json.dump(snapshot, f, indent=2, ensure_ascii=False)
    return ruta


def create_router_backup(api) -> str:
    """Crea un .backup completo EN EL ROUTER y retorna su nombre."""
    nombre = f"respaldo-{datetime.now():%Y%m%d-%H%M%S}"
    api.command("/system/backup/save", params=[f"=name={nombre}"])
    return f"{nombre}.backup"


def list_router_backups(api) -> list:
    """Archivos .backup que hay en el router (solo lectura)."""
    return [f for f in api.command("/file/print")
            if f.get("name", "").endswith(".backup")]
