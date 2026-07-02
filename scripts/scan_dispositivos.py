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
import re

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from lib import (MikroTikAPI, load_config, C,
                 get_mac_vendor_cache, is_random_mac, lookup_mac_vendor_online,
                 load_oui_cache, save_oui_cache,
                 run_script)

# Palabras clave en hostname que sugieren tipo de dispositivo
MOBILE_KEYWORDS  = ["iphone", "ipad", "android", "samsung", "xiaomi", "redmi",
                    "poco", "huawei", "oppo", "oneplus", "pixel", "motorola", "phone"]
APPLE_KEYWORDS   = ["iphone", "ipad", "macbook", "imac", "mac mini", "apple",
                    "airpods", "homepod", "apple tv", "apple watch"]
IOT_KEYWORDS     = ["esp", "shelly", "sonoff", "tuya", "tasmota", "ring",
                    "echo", "alexa", "nest", "chromecast", "fire", "blink"]

# OUI conocidos de Apple para refuerzo
APPLE_OUIS = {
    "00:1E:C2", "AC:BC:32", "F0:18:98", "8C:85:90", "60:F8:1D",
    "A8:86:DD", "98:10:E8", "C4:B3:01", "38:CA:DA", "00:23:12",
    "00:26:BB", "3C:07:54", "78:D7:5F", "F4:F1:5A", "DC:A4:CA",
    "B8:E8:56", "00:CD:FE", "F0:DB:F8", "70:56:81", "4C:57:CA",
}


def guess_device_type(mac: str, hostname: str, vendor: str) -> str:
    """Infiere el tipo de dispositivo basándose en MAC, hostname y vendor."""
    h = hostname.lower()
    v = vendor.lower()
    oui = mac[:8].upper() if mac else ""

    if oui in APPLE_OUIS or any(k in h for k in APPLE_KEYWORDS) or "apple" in v:
        return "🍎 Apple"
    if is_random_mac(mac):
        if any(k in h for k in MOBILE_KEYWORDS):
            return "📱 Móvil"
        return "📱 MAC privada (móvil?)"
    if any(k in h for k in MOBILE_KEYWORDS) or any(k in v for k in MOBILE_KEYWORDS):
        return "📱 Móvil"
    if any(k in h for k in IOT_KEYWORDS) or any(k in v for k in ["espressif", "amazon", "google", "blink", "ring"]):
        return "🏠 IoT/Smart"
    if any(k in v for k in ["printer", "epson", "hp", "brother", "canon", "lexmark"]):
        return "🖨️  Impresora"
    if any(k in v for k in ["tp-link", "netgear", "asus", "linksys", "ubiquiti", "mikrotik"]):
        return "📡 Red"
    if any(k in v for k in ["intel", "gigabyte", "asus", "foxconn", "realtek", "broadcom"]):
        return "💻 PC/Laptop"
    if vendor:
        return "🔌 Dispositivo"
    return "❓ Desconocido"


def fmt_lease_time(expires: str) -> str:
    """Convierte el tiempo de expiración del lease a formato legible."""
    if not expires or expires in ("never", ""):
        return "∞ fija"
    # RouterOS retorna formato "jan/01/2024 12:00:00" o segundos
    m = re.match(r"(\d+)d(\d+):(\d+):(\d+)", expires)
    if m:
        d, h, mi, _ = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))
        if d:   return f"{d}d {h}h"
        if h:   return f"{h}h {mi}m"
        return  f"{mi}m"
    return expires[:10]


def scan_network(api, do_lookup: bool, filter_type: str) -> list:
    """Recopila y enriquece la información de todos los dispositivos."""
    local_vendors = get_mac_vendor_cache()
    oui_cache     = load_oui_cache()
    leases        = api.command("/ip/dhcp-server/lease/print")
    arp           = api.command("/ip/arp/print")

    devices = {}

    # Poblar desde leases DHCP
    for l in leases:
        ip  = l.get("address", "")
        mac = l.get("mac-address", "").upper()
        if not ip:
            continue
        devices[ip] = {
            "mac":      mac,
            "hostname": l.get("host-name", ""),
            "lease_type": l.get("dynamic", "true") == "false" and "estática" or l.get("status", "DHCP"),
            "expires":  l.get("expires-after", ""),
            "comment":  l.get("comment", ""),
        }

    # Agregar dispositivos con IP estática (solo en ARP, no en DHCP)
    for e in arp:
        ip  = e.get("address", "")
        mac = e.get("mac-address", "").upper()
        if not ip or not mac or ip in devices:
            continue
        devices[ip] = {
            "mac":        mac,
            "hostname":   "",
            "lease_type": "STATIC",
            "expires":    "never",
            "comment":    "",
        }

    # Enriquecer con vendor y tipo
    results = []
    unknown_macs = []

    for ip, d in devices.items():
        mac = d["mac"]
        oui = mac[:8].upper()
        vendor = local_vendors.get(oui, oui_cache.get(oui, ""))

        if not vendor and not is_random_mac(mac):
            unknown_macs.append((ip, mac, oui))

        device_type = guess_device_type(mac, d["hostname"], vendor)
        results.append({
            "ip":       ip,
            "mac":      mac,
            "hostname": d["hostname"],
            "vendor":   vendor,
            "type":     device_type,
            "lease":    d["lease_type"],
            "expires":  fmt_lease_time(d["expires"]),
            "random":   is_random_mac(mac),
        })

    # Lookup online para MACs desconocidas (solo si --lookup)
    if do_lookup and unknown_macs:
        print(f"\n  {C.DIM}Consultando macvendors.com para {len(unknown_macs)} MACs desconocidas...{C.RESET}")
        for ip, mac, oui in unknown_macs:
            v = lookup_mac_vendor_online(mac, oui_cache)
            if v:
                # Actualizar en results
                for r in results:
                    if r["mac"] == mac:
                        r["vendor"] = v
                        r["type"]   = guess_device_type(mac, r["hostname"], v)
        save_oui_cache(oui_cache)

    # Aplicar filtro
    if filter_type:
        ft = filter_type.lower()
        if ft == "apple":
            results = [r for r in results if "Apple" in r["type"]]
        elif ft == "mobile":
            results = [r for r in results if "📱" in r["type"]]
        elif ft == "iot":
            results = [r for r in results if "IoT" in r["type"]]
        elif ft == "unknown":
            results = [r for r in results if "Desconocido" in r["type"] or not r["vendor"]]

    return sorted(results, key=lambda x: list(map(int, x["ip"].split("."))))


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
    from collections import Counter
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
        results = scan_network(api, args.lookup, args.filter)
        print_results(results)

        if not args.lookup:
            unknown = sum(1 for r in results if not r["vendor"] and not r["random"])
            if unknown:
                print(f"  {C.DIM}💡 {unknown} fabricantes desconocidos."
                      f" Usa --lookup para consultar online.{C.RESET}\n")


if __name__ == "__main__":
    run_script(main)
