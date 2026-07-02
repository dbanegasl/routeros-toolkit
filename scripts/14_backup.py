#!/usr/bin/env python3
"""
14_backup.py — Respaldo de la configuración del router
========================================================

Dos niveles de respaldo:

1. Snapshot local (por defecto, SOLO LECTURA sobre el router):
   guarda en backups/ un JSON con todas las secciones que este toolkit
   puede modificar (firewall, mangle, colas, leases, schedulers…) más
   metadatos del router. Sirve como referencia y para comparar antes y
   después de un cambio (ej: desplegar QoS).

2. Respaldo completo en el router (--full):
   además del snapshot, ejecuta /system/backup/save en el router. El
   archivo .backup queda EN EL ROUTER (Files en Winbox) y permite
   restaurar TODO el equipo. Descárgalo con Winbox (arrastrar desde
   Files) o por FTP.

El directorio local es backups/ en la raíz del proyecto (gitignored),
overrideable con la variable de entorno MIKROTIK_BACKUP_DIR.

Uso:
    python3 scripts/14_backup.py             # snapshot local (solo lectura)
    python3 scripts/14_backup.py --full      # snapshot + .backup en el router
    python3 scripts/14_backup.py --list      # ver respaldos existentes
"""

import sys
import os
import json
import argparse
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from lib import (MikroTikAPI, load_config, print_header, fmt_bytes,
                 get_router_datetime, C, run_script)

# Secciones que los scripts de este toolkit pueden modificar (06, 09, 10, 13)
# más contexto útil para reconstruir a mano si hiciera falta.
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


def do_list(api):
    """Muestra respaldos locales y del router."""
    backup_dir = get_backup_dir()
    locales = sorted(backup_dir.glob("snapshot_*.json")) if backup_dir.exists() else []

    print(f"  {C.BOLD}Snapshots locales{C.RESET} ({backup_dir}):")
    if not locales:
        print(f"  {C.DIM}(ninguno — crea uno con: python3 scripts/14_backup.py){C.RESET}")
    for ruta in locales:
        tam = fmt_bytes(ruta.stat().st_size)
        try:
            with open(ruta) as f:
                meta = json.load(f).get("meta", {})
            detalle = f"RouterOS {meta.get('routeros', '?')}"
        except (OSError, ValueError):
            detalle = f"{C.WARN}(no se pudo leer){C.RESET}"
        print(f"  {C.GREEN}✓{C.RESET} {ruta.name:<34} {tam:>9}   {detalle}")

    print(f"\n  {C.BOLD}Respaldos .backup en el router{C.RESET} (Files en Winbox):")
    router_files = list_router_backups(api)
    if not router_files:
        print(f"  {C.DIM}(ninguno — crea uno con: python3 scripts/14_backup.py --full){C.RESET}")
    for f in router_files:
        tam = fmt_bytes(int(f.get("size", 0)))
        fecha = f.get("creation-time", "?")
        print(f"  {C.GREEN}✓{C.RESET} {f.get('name', '?'):<34} {tam:>9}   {fecha}")
    print()


def do_backup(api, full: bool):
    """Crea el snapshot local y, con --full, también el .backup en el router."""
    print("Leyendo configuración del router...")
    snapshot = build_snapshot(api)
    resumen = ", ".join(f"{nombre}: {len(items)}"
                        for nombre, items in snapshot["secciones"].items())
    ruta = save_snapshot(snapshot)
    print(f"\n  {C.GREEN}✅ Snapshot local guardado:{C.RESET} {ruta}")
    print(f"  {C.DIM}Entradas — {resumen}{C.RESET}")

    if full:
        print(f"\nCreando respaldo completo en el router...")
        nombre = create_router_backup(api)
        print(f"  {C.GREEN}✅ Respaldo completo creado EN EL ROUTER:{C.RESET} {nombre}")
        print(f"  {C.DIM}Restaurable desde Winbox (Files → Restore). "
              f"Descárgalo a tu PC para conservarlo fuera del equipo.{C.RESET}")
    print()


def main():
    parser = argparse.ArgumentParser(
        description="Respaldo de la configuración del router")
    parser.add_argument("--full", action="store_true",
                        help="Además del snapshot local, crear un .backup "
                             "completo en el router (/system/backup/save)")
    parser.add_argument("--list", action="store_true",
                        help="Ver respaldos existentes (locales y del router)")
    args = parser.parse_args()

    print_header("💾 Respaldo de configuración del router")
    config = load_config()
    print(f"Conectando a {config['host']}:{config['port']}...\n")
    with MikroTikAPI(**config) as api:
        if args.list:
            do_list(api)
        else:
            do_backup(api, full=args.full)


if __name__ == "__main__":
    run_script(main)
