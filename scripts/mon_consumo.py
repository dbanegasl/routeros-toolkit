#!/usr/bin/env python3
"""
mon_consumo.py — Top consumidores de ancho de banda
=========================================================

Analiza TODAS las conexiones activas del firewall (connection tracking)
y agrupa por IP de origen (LAN) para identificar qué dispositivo está
usando más internet en este momento.

Métricas reportadas por dispositivo:
  ↓ Descarga actual  — suma de repl-rate  de todas sus conexiones (bytes/s)
  ↑ Subida actual    — suma de orig-rate  de todas sus conexiones (bytes/s)
  DL sesión          — bytes descargados desde que se creó cada conexión
  UL sesión          — bytes subidos desde que se creó cada conexión
  # Conexiones       — número de conexiones TCP/UDP activas

Cómo se resuelven los nombres de dispositivos:
  1. Hostname reportado por DHCP (si existe y no es genérico como "wlan0")
  2. Fabricante del MAC (OUI lookup local) + últimos 5 dígitos de la MAC
  3. MAC completa como último recurso
  Los dispositivos con IP estática se marcan con [estática].

Campos del connection tracking usados:
    orig-rate  → bytes/s que el cliente envía al exterior (upload)
    repl-rate  → bytes/s que el exterior envía al cliente (download)
    orig-bytes + orig-fasttrack-bytes  → total upload de la conexión
    repl-bytes + repl-fasttrack-bytes  → total download de la conexión

Colores:
    🔴 Rojo    → ≥ 10 Mbps
    🟡 Amarillo → 1–10 Mbps
    🟢 Verde   → < 1 Mbps

Uso:
    cd mikrotik/
    python3 scripts/mon_consumo.py
    python3 scripts/mon_consumo.py --top 10
    python3 scripts/mon_consumo.py --sort total    # por GB acumulados
    python3 scripts/mon_consumo.py --no-color      # sin colores ANSI
"""

import sys
import os
import argparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from lib import (MikroTikAPI, load_config, fmt_speed, fmt_bytes,
                 build_name_map, C, get_lan_prefix,
                 run_script)
from core.monitoreo import snapshot_consumo, ordenar_consumo


def main():
    parser = argparse.ArgumentParser(
        description="Muestra los dispositivos con mayor consumo de red")
    parser.add_argument("--top", type=int, default=15,
                        help="Número de dispositivos a mostrar (default: 15)")
    parser.add_argument("--sort", choices=["rate", "total"], default="rate",
                        help="Ordenar por velocidad actual (rate) o total de sesión (total)")
    parser.add_argument("--no-color", action="store_true",
                        help="Deshabilitar colores ANSI")
    args = parser.parse_args()

    if args.no_color:
        C.disable()

    cfg = load_config()
    print(f"\n{C.DIM}Conectando a {cfg['host']}...{C.RESET}")

    with MikroTikAPI(**cfg) as api:

        ip_name = build_name_map(api)
        lan = get_lan_prefix(api)

        data, total_conns = snapshot_consumo(api, lan)
        ranked = ordenar_consumo(data, por=args.sort)

        # ── Encabezado ────────────────────────────────────────────────────
        sep = "─" * 98
        print(f"\n{C.BOLD}{sep}{C.RESET}")
        print(f"  {C.HEADER}{'DISPOSITIVO':<30} {'IP':<16} "
              f"{'↓ AHORA':>13} {'↑ AHORA':>13} "
              f"{'DL SESIÓN':>11} {'UL SESIÓN':>11} {'CONN':>6}{C.RESET}")
        print(f"{C.BOLD}{sep}{C.RESET}")

        shown = 0
        winner = None

        for ip, d in ranked:
            if shown >= args.top:
                break
            if d["dl_total"] + d["ul_total"] == 0:
                continue

            dl_r = d["dl_rate"]
            ul_r = d["ul_rate"]
            name = ip_name.get(ip, ip)[:29]

            # Color según velocidad de descarga
            speed_col = C.speed_color(dl_r)

            rank_num = shown + 1
            prefix = f"{C.ERR}🔴{C.RESET}" if rank_num == 1 else f"  {rank_num:>2}"

            print(f"{prefix} {C.BOLD}{name:<30}{C.RESET} {C.CYAN}{ip:<16}{C.RESET}"
                  f" {speed_col}{fmt_speed(dl_r):>13}{C.RESET}"
                  f" {C.GREEN}{fmt_speed(ul_r):>13}{C.RESET}"
                  f" {fmt_bytes(d['dl_total']):>11}"
                  f" {fmt_bytes(d['ul_total']):>11}"
                  f" {C.DIM}{d['conns']:>6}{C.RESET}")

            if winner is None:
                winner = ip
            shown += 1

        print(f"{C.BOLD}{sep}{C.RESET}")
        print(f"\n  {C.DIM}Conexiones activas totales: {total_conns}{C.RESET}")

        # ── Resumen del ganador ───────────────────────────────────────────
        if winner:
            w = data[winner]
            w_name = ip_name.get(winner, winner)
            print(f"\n  {C.ERR}🔴 Mayor consumidor:{C.RESET} "
                  f"{C.BOLD}{w_name}{C.RESET} "
                  f"{C.DIM}({winner}){C.RESET}")
            print(f"     {C.BOLD}↓ {fmt_speed(w['dl_rate'])}{C.RESET}  "
                  f"↑ {fmt_speed(w['ul_rate'])}  "
                  f"{C.DIM}|{C.RESET}  "
                  f"Sesión: DL {C.BOLD}{fmt_bytes(w['dl_total'])}{C.RESET}  "
                  f"UL {fmt_bytes(w['ul_total'])}\n")


if __name__ == "__main__":
    run_script(main)
