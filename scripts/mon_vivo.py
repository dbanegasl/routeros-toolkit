#!/usr/bin/env python3
"""
mon_vivo.py — Monitor en vivo de consumo por dispositivo
===============================================================

Muestra un dashboard que se refresca automáticamente cada N segundos,
con los dispositivos ordenados por velocidad de descarga actual.

Usa el campo `repl-rate` / `orig-rate` del connection tracking, que el
router actualiza en tiempo real (sin necesidad de hacer muestras manuales).

Controles:
    Ctrl+C  — Salir del monitor

Uso:
    cd mikrotik/
    python3 scripts/mon_vivo.py              # refresca cada 3 s
    python3 scripts/mon_vivo.py --interval 5  # refresca cada 5 s
    python3 scripts/mon_vivo.py --top 10      # mostrar top 10
"""

import sys
import os
import time
import argparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from lib import (MikroTikAPI, load_config, fmt_speed, fmt_bytes,
                 build_name_map, C, get_lan_prefix,
                 run_script)
from core.monitoreo import snapshot_consumo, ordenar_consumo


def clear_screen():
    print("\033[H\033[J", end="", flush=True)


def render(snapshot: dict, ip_name: dict, top: int, host: str,
           iteration: int, elapsed: float, total_conns: int):
    """Dibuja el dashboard completo."""
    clear_screen()

    now = time.strftime("%H:%M:%S")
    print(f"  {C.HEADER}MikroTik Live Monitor{C.RESET}  ─  "
          f"{C.CYAN}{host}{C.RESET}  ─  {C.BOLD}{now}{C.RESET}  "
          f"{C.DIM}(refresh #{iteration}, {elapsed:.1f}s)   Ctrl+C para salir{C.RESET}")
    print()

    ranked = ordenar_consumo(snapshot, por="rate")

    # Filtrar IPs sin actividad reciente
    active = [(ip, d) for ip, d in ranked
              if d["dl_total"] + d["ul_total"] > 0]

    print(f"  {C.HEADER}{'#':<4} {'DISPOSITIVO':<32} {'IP':<16} "
          f"{'↓ DESCARGA':>13} {'↑ SUBIDA':>12} "
          f"{'DL SESIÓN':>11} {'UL SESIÓN':>11} {'CONN':>5}{C.RESET}")
    print(f"  {'─'*104}")

    for rank, (ip, d) in enumerate(active[:top], 1):
        name = ip_name.get(ip, ip)[:31]
        dl_r = d["dl_rate"]
        ul_r = d["ul_rate"]
        speed_col = C.speed_color(dl_r)
        prefix = f"{C.ERR}🔴{C.RESET}" if rank == 1 and (dl_r + ul_r) > 0 else f"  {rank:>2}"
        print(f"{prefix}  {C.BOLD}{name:<32}{C.RESET} {C.CYAN}{ip:<16}{C.RESET}"
              f" {speed_col}{fmt_speed(dl_r):>13}{C.RESET}"
              f" {C.GREEN}{fmt_speed(ul_r):>12}{C.RESET}"
              f" {fmt_bytes(d['dl_total']):>11}"
              f" {fmt_bytes(d['ul_total']):>11}"
              f" {C.DIM}{d['conns']:>5}{C.RESET}")

    print(f"  {'─'*104}")
    print(f"\n  Dispositivos activos: {C.BOLD}{len(active)}{C.RESET}  |  "
          f"Conexiones totales: {C.DIM}{total_conns}{C.RESET}")


def main():
    parser = argparse.ArgumentParser(
        description="Monitor en vivo de consumo de red por dispositivo")
    parser.add_argument("--interval", type=float, default=3.0,
                        help="Segundos entre refrescos (default: 3)")
    parser.add_argument("--top", type=int, default=20,
                        help="Máximo de dispositivos a mostrar (default: 20)")
    args = parser.parse_args()

    cfg = load_config()
    print(f"Conectando a {cfg['host']}...")

    with MikroTikAPI(**cfg) as api:
        print("Cargando dispositivos...")
        ip_name = build_name_map(api)
        lan = get_lan_prefix(api)

        iteration = 0
        print("Iniciando monitor... (Ctrl+C para salir)")
        time.sleep(1)

        try:
            while True:
                t0 = time.time()
                snapshot, total_conns = snapshot_consumo(api, lan)
                elapsed = time.time() - t0
                iteration += 1
                render(snapshot, ip_name, args.top, cfg["host"],
                       iteration, elapsed, total_conns)
                time.sleep(args.interval)

        except KeyboardInterrupt:
            print("\n\n  Monitor detenido.\n")


if __name__ == "__main__":
    run_script(main)
