#!/usr/bin/env python3
"""
scan_dispositivos.py — Identificación avanzada de dispositivos en la red
======================================================================

Combina datos de DHCP, ARP y opcionalmente la API de macvendors.com para
identificar cada dispositivo con el máximo detalle posible.

Detecta:
  - MACs aleatorias/privadas (iOS 14+, Android 10+, Windows 10+)
  - Fabricante real vía base de datos OUI local
  - Fabricante online vía macvendors.com (con --lookup)
  - Dispositivos Apple, móviles, IoT, etc.
  - Hostname DHCP, tiempo restante de lease, tipo de asignación

Uso:
    python3 scripts/scan_dispositivos.py             # solo base local
    python3 scripts/scan_dispositivos.py --lookup    # consulta macvendors.com
    python3 scripts/scan_dispositivos.py --filter apple
    python3 scripts/scan_dispositivos.py --filter mobile
    python3 scripts/scan_dispositivos.py --filter unknown
"""

import sys
import os
import argparse
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from lib import MikroTikAPI, load_config, C, run_script
from core.dispositivos import (escanear_red, completar_vendors_online,
                               filtrar_dispositivos)


def print_results(results: list):
    if not results:
        print(f"\n  {C.WARN}Sin resultados.{C.RESET}\n")
        return

    col_ip     = 16
    col_mac    = 20
    col_vendor = 22
    col_host   = 22
    col_type   = 24

    header = (f"  {'IP':<{col_ip}} {'MAC':<{col_mac}} {'FABRICANTE':<{col_vendor}}"
              f" {'HOSTNAME':<{col_host}} TIPO DE DISPOSITIVO")
    sep    = f"  {'─' * (col_ip + col_mac + col_vendor + col_host + col_type + 6)}"

    print(f"\n{header}")
    print(sep)

    for r in results:
        vendor_str = r["vendor"] or f"{C.DIM}—{C.RESET}"
        host_str   = r["hostname"] or f"{C.DIM}—{C.RESET}"
        random_tag = f" {C.DIM}[priv]{C.RESET}" if r["random"] else ""

        # Color por tipo
        if "Apple" in r["type"]:
            type_color = C.CYAN
        elif "📱" in r["type"]:
            type_color = C.YELLOW
        elif "Desconocido" in r["type"]:
            type_color = C.DIM
        else:
            type_color = C.GREEN

        print(f"  {r['ip']:<{col_ip}} {r['mac']:<{col_mac}}{random_tag}"
              f" {vendor_str:<{col_vendor}} {host_str:<{col_host}}"
              f" {type_color}{r['type']}{C.RESET}")

    print(f"\n  Total: {C.BOLD}{len(results)}{C.RESET} dispositivos\n")

    # Resumen por tipo
    tipos = Counter(r["type"] for r in results)
    print(f"  {C.BOLD}Resumen:{C.RESET}")
    for tipo, count in tipos.most_common():
        print(f"    {tipo:<30} {count}")
    print()


def main():
    parser = argparse.ArgumentParser(
        description="Identificación avanzada de dispositivos en la red")
    parser.add_argument("--lookup",  action="store_true",
                        help="Consultar macvendors.com para MACs desconocidas")
    parser.add_argument("--filter",  metavar="TIPO",
                        help="Filtrar por tipo: apple, mobile, iot, unknown")
    args = parser.parse_args()

    cfg = load_config()
    print(f"\n{C.DIM}Conectando a {cfg['host']}...{C.RESET}")

    with MikroTikAPI(**cfg) as api:
        print(f"{C.HEADER}  🔍 Escaneando dispositivos en la red...{C.RESET}")
        results, unknown_macs, oui_cache = escanear_red(api)

        if args.lookup and unknown_macs:
            print(f"\n  {C.DIM}Consultando macvendors.com para "
                  f"{len(unknown_macs)} MACs desconocidas...{C.RESET}")
            completar_vendors_online(results, unknown_macs, oui_cache)

        results = filtrar_dispositivos(results, args.filter)
        print_results(results)

        if not args.lookup:
            unknown = sum(1 for r in results if not r["vendor"] and not r["random"])
            if unknown:
                print(f"  {C.DIM}💡 {unknown} fabricantes desconocidos."
                      f" Usa --lookup para consultar online.{C.RESET}\n")


if __name__ == "__main__":
    run_script(main)
