#!/usr/bin/env python3
"""
mant_log.py — Ver el log del router MikroTik
==================================================

Muestra las entradas del syslog de RouterOS con colores por nivel:
    🔴 error / critical — rojo
    🟡 warning          — amarillo
    🟢 info             — normal
    ⚪ debug            — gris

Uso:
    python3 scripts/mant_log.py              # últimas 50 líneas
    python3 scripts/mant_log.py --lines 100  # últimas 100 líneas
    python3 scripts/mant_log.py --follow      # modo follow (Ctrl+C para salir)
    python3 scripts/mant_log.py --filter dhcp # filtrar por texto
"""

import sys
import os
import argparse
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from lib import MikroTikAPI, load_config, C, run_script


LEVEL_COLOR = {
    "critical": C.ERR,
    "error":    C.ERR,
    "warning":  C.WARN,
    "info":     C.RESET,
    "debug":    C.GRAY,
}

LEVEL_ICON = {
    "critical": "💀",
    "error":    "🔴",
    "warning":  "🟡",
    "info":     "  ",
    "debug":    "  ",
}


def print_log_entries(entries: list, filter_text: str = ""):
    for e in entries:
        time_str  = e.get("time", "")
        topics    = e.get("topics", "")
        message   = e.get("message", "")
        level     = "info"
        for lvl in ("critical", "error", "warning", "debug"):
            if lvl in topics:
                level = lvl
                break

        line = f"{time_str}  [{topics:<20}]  {message}"
        if filter_text and filter_text.lower() not in line.lower():
            continue

        col  = LEVEL_COLOR.get(level, C.RESET)
        icon = LEVEL_ICON.get(level, "  ")
        print(f"{icon} {col}{line}{C.RESET}")


def main():
    parser = argparse.ArgumentParser(description="Ver log del router MikroTik")
    parser.add_argument("--lines",  type=int, default=50,
                        help="Número de líneas a mostrar (default: 50)")
    parser.add_argument("--follow", action="store_true",
                        help="Actualizar cada 3 segundos (modo follow)")
    parser.add_argument("--filter", dest="filter_text", default="",
                        help="Filtrar por texto en el mensaje o topics")
    args = parser.parse_args()

    cfg = load_config()
    print(f"\n{C.DIM}Conectando a {cfg['host']}...{C.RESET}\n")

    with MikroTikAPI(**cfg) as api:
        try:
            while True:
                entries = api.command("/log/print")
                # Tomar las últimas N entradas
                entries = entries[-args.lines:]

                if args.follow:
                    print("\033[H\033[J", end="")
                    print(f"{C.HEADER}MikroTik Log  ─  {cfg['host']}  "
                          f"─  {time.strftime('%H:%M:%S')}  "
                          f"(Ctrl+C para salir){C.RESET}\n")

                print_log_entries(entries, args.filter_text)

                if not args.follow:
                    print(f"\n{C.DIM}  {len(entries)} entradas mostradas{C.RESET}\n")
                    break

                time.sleep(3)

        except KeyboardInterrupt:
            print(f"\n{C.DIM}  Log detenido.{C.RESET}\n")


if __name__ == "__main__":
    run_script(main)
