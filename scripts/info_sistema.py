#!/usr/bin/env python3
"""
info_sistema.py — Información del sistema del router
=======================================================

Muestra un resumen del estado del hardware y software del router:
    - Modelo, versión de RouterOS, uptime
    - Uso de CPU y memoria RAM
    - Temperatura (si el hardware la reporta)
    - Espacio en disco (flash)
    - Número de interfaces activas

Uso:
    python3 scripts/info_sistema.py
    python3 scripts/info_sistema.py --watch   # refresca cada 3s (Ctrl+C para salir)
"""

import sys
import os
import argparse
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from lib import MikroTikAPI, load_config, fmt_bytes, C, run_script


def render_bar(value: int, total: int, width: int = 20) -> str:
    """Barra de progreso ASCII. value y total deben ser enteros."""
    if total == 0:
        return "[" + "?" * width + "]"
    filled = int(width * value / total)
    bar = "█" * filled + "░" * (width - filled)
    pct = value / total * 100
    color = C.ERR if pct > 85 else (C.WARN if pct > 60 else C.GREEN)
    return f"{color}[{bar}]{C.RESET} {pct:.1f}%"


def show_info(api):
    # Información del sistema
    res = api.command("/system/resource/print")
    identity = api.command("/system/identity/print")
    interfaces = api.command("/interface/print")
    leases = api.command("/ip/dhcp-server/lease/print")

    if not res:
        print(f"{C.ERR}No se pudo obtener información del sistema.{C.RESET}")
        return

    r = res[0]
    name = identity[0].get("name", "MikroTik") if identity else "MikroTik"

    uptime        = r.get("uptime", "?")
    version       = r.get("version", "?")
    board         = r.get("board-name", "?")
    arch          = r.get("architecture-name", "?")
    cpu_count     = r.get("cpu-count", "1")
    cpu_load      = int(r.get("cpu-load", 0))
    free_mem      = int(r.get("free-memory", 0))
    total_mem     = int(r.get("total-memory", 1))
    used_mem      = total_mem - free_mem
    free_hdd      = int(r.get("free-hdd-space", 0))
    total_hdd     = int(r.get("total-hdd-space", 1))
    used_hdd      = total_hdd - free_hdd
    bad_blocks    = r.get("bad-blocks", "0")

    ifaces_up   = sum(1 for i in interfaces if i.get("running") == "true")
    ifaces_total = len(interfaces)
    devices_conn = sum(1 for l in leases if l.get("status") == "bound")

    sep = "─" * 60
    print(f"\n{C.BOLD}{sep}{C.RESET}")
    print(f"  {C.HEADER}🌐  {name}  ─  {board}  ─  RouterOS {version}{C.RESET}")
    print(f"{C.BOLD}{sep}{C.RESET}\n")

    print(f"  {C.BOLD}Arquitectura:{C.RESET}  {arch}  ({cpu_count} CPU)")
    print(f"  {C.BOLD}Uptime:      {C.RESET}  {uptime}")
    print(f"  {C.BOLD}Versión:     {C.RESET}  RouterOS {version}\n")

    print(f"  {C.BOLD}CPU:         {C.RESET}  {render_bar(cpu_load, 100)}  ({cpu_load}%)")
    print(f"  {C.BOLD}RAM:         {C.RESET}  {render_bar(used_mem, total_mem)}"
          f"  {fmt_bytes(used_mem)} / {fmt_bytes(total_mem)}")
    print(f"  {C.BOLD}Disco:       {C.RESET}  {render_bar(used_hdd, total_hdd)}"
          f"  {fmt_bytes(used_hdd)} / {fmt_bytes(total_hdd)}")

    print(f"\n  {C.BOLD}Interfaces:  {C.RESET}  {C.GREEN}{ifaces_up} activas{C.RESET}"
          f" de {ifaces_total} totales")
    print(f"  {C.BOLD}Dispositivos:{C.RESET}  {C.CYAN}{devices_conn} conectados{C.RESET}"
          f" (DHCP)\n")

    print(f"{C.DIM}{sep}{C.RESET}\n")


def main():
    parser = argparse.ArgumentParser(
        description="Información del sistema del router MikroTik")
    parser.add_argument("--watch", action="store_true",
                        help="Refresca cada 3 segundos (Ctrl+C para salir)")
    args = parser.parse_args()

    cfg = load_config()
    print(f"\n{C.DIM}Conectando a {cfg['host']}...{C.RESET}")

    with MikroTikAPI(**cfg) as api:
        try:
            while True:
                if args.watch:
                    print("\033[H\033[J", end="")
                show_info(api)
                if not args.watch:
                    break
                time.sleep(3)
        except KeyboardInterrupt:
            print(f"\n{C.DIM}  Detenido.{C.RESET}\n")


if __name__ == "__main__":
    run_script(main)
