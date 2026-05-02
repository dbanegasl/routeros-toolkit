#!/usr/bin/env python3
"""
02_top_consumers.py — Top consumidores de ancho de banda
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
    python3 scripts/02_top_consumers.py
    python3 scripts/02_top_consumers.py --top 10
    python3 scripts/02_top_consumers.py --sort total    # por GB acumulados
    python3 scripts/02_top_consumers.py --no-color      # sin colores ANSI
"""

import sys
import os
import argparse
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from lib import MikroTikAPI, load_config, fmt_speed, fmt_bytes, resolve_device_name, C


def build_name_map(api) -> dict:
    """
    Construye un mapa IP → (nombre_display, es_estática) combinando DHCP y ARP.
    Las IPs que aparecen en ARP pero no en DHCP se marcan como estáticas.
    """
    leases = api.command("/ip/dhcp-server/lease/print")
    dhcp_ips = set()
    ip_info: dict = {}  # ip → (mac, hostname)

    for l in leases:
        ip  = l.get("address", "")
        mac = l.get("mac-address", "")
        name = l.get("host-name", "")
        dhcp_ips.add(ip)
        ip_info[ip] = (mac, name, False)

    arp = api.command("/ip/arp/print")
    for e in arp:
        ip  = e.get("address", "")
        mac = e.get("mac-address", "")
        if ip.startswith("192.168.") and ip not in ip_info:
            ip_info[ip] = (mac, "", True)   # IP estática

    return {
        ip: resolve_device_name(ip, mac, hostname, is_static)
        for ip, (mac, hostname, is_static) in ip_info.items()
    }


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

        # Leer todas las conexiones activas
        conns = api.command("/ip/firewall/connection/print")

        # Acumular métricas por IP LAN de origen
        dl_rate   = defaultdict(int)
        ul_rate   = defaultdict(int)
        dl_total  = defaultdict(int)
        ul_total  = defaultdict(int)
        num_conns = defaultdict(int)

        for c in conns:
            src = c.get("src-address", "").split(":")[0]
            if not src.startswith("192.168."):
                continue
            dl_rate[src]   += int(c.get("repl-rate", 0))
            ul_rate[src]   += int(c.get("orig-rate", 0))
            dl_total[src]  += (int(c.get("repl-bytes", 0)) +
                               int(c.get("repl-fasttrack-bytes", 0)))
            ul_total[src]  += (int(c.get("orig-bytes", 0)) +
                               int(c.get("orig-fasttrack-bytes", 0)))
            num_conns[src] += 1

        # Ordenar
        all_ips = set(list(dl_rate) + list(dl_total))
        if args.sort == "rate":
            ranked = sorted(all_ips,
                            key=lambda ip: dl_rate[ip] + ul_rate[ip],
                            reverse=True)
        else:
            ranked = sorted(all_ips,
                            key=lambda ip: dl_total[ip] + ul_total[ip],
                            reverse=True)

        # ── Encabezado ────────────────────────────────────────────────────
        sep = "─" * 98
        print(f"\n{C.BOLD}{sep}{C.RESET}")
        print(f"  {C.HEADER}{'DISPOSITIVO':<30} {'IP':<16} "
              f"{'↓ AHORA':>13} {'↑ AHORA':>13} "
              f"{'DL SESIÓN':>11} {'UL SESIÓN':>11} {'CONN':>6}{C.RESET}")
        print(f"{C.BOLD}{sep}{C.RESET}")

        shown = 0
        winner = None

        for ip in ranked:
            if shown >= args.top:
                break
            if dl_total[ip] + ul_total[ip] == 0:
                continue

            dl_r = dl_rate[ip]
            ul_r = ul_rate[ip]
            name = ip_name.get(ip, ip)[:29]

            # Color según velocidad de descarga
            speed_col = C.speed_color(dl_r)

            rank_num = shown + 1
            prefix = f"{C.ERR}🔴{C.RESET}" if rank_num == 1 else f"  {rank_num:>2}"

            print(f"{prefix} {C.BOLD}{name:<30}{C.RESET} {C.CYAN}{ip:<16}{C.RESET}"
                  f" {speed_col}{fmt_speed(dl_r):>13}{C.RESET}"
                  f" {C.GREEN}{fmt_speed(ul_r):>13}{C.RESET}"
                  f" {fmt_bytes(dl_total[ip]):>11}"
                  f" {fmt_bytes(ul_total[ip]):>11}"
                  f" {C.DIM}{num_conns[ip]:>6}{C.RESET}")

            if winner is None:
                winner = ip
            shown += 1

        print(f"{C.BOLD}{sep}{C.RESET}")
        print(f"\n  {C.DIM}Conexiones activas totales: {len(conns)}{C.RESET}")

        # ── Resumen del ganador ───────────────────────────────────────────
        if winner:
            w_name = ip_name.get(winner, winner)
            print(f"\n  {C.ERR}🔴 Mayor consumidor:{C.RESET} "
                  f"{C.BOLD}{w_name}{C.RESET} "
                  f"{C.DIM}({winner}){C.RESET}")
            print(f"     {C.BOLD}↓ {fmt_speed(dl_rate[winner])}{C.RESET}  "
                  f"↑ {fmt_speed(ul_rate[winner])}  "
                  f"{C.DIM}|{C.RESET}  "
                  f"Sesión: DL {C.BOLD}{fmt_bytes(dl_total[winner])}{C.RESET}  "
                  f"UL {fmt_bytes(ul_total[winner])}\n")


if __name__ == "__main__":
    main()

