"""
core/dispositivos.py — Inventario, escaneo y clasificación de dispositivos
==========================================================================

Lógica extraída de info_dispositivos.py y scan_dispositivos.py.
Las funciones retornan datos (listas de dicts); no imprimen nada.
"""

import re

from lib import (resolve_device_name, get_lan_prefix, get_mac_vendor_cache,
                 is_random_mac, lookup_mac_vendor_online,
                 load_oui_cache, save_oui_cache)

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


# ---------------------------------------------------------------------------
# Inventario (info_dispositivos)
# ---------------------------------------------------------------------------

def inventario_dispositivos(api) -> list:
    """Inventario completo: leases DHCP + IPs estáticas detectadas en ARP.

    Retorna una lista de dicts ordenada por IP:
        {ip, mac, nombre, estado, puerto, tipo}
    donde tipo es "DHCP" o "STATIC" y estado es el status del lease
    ("bound", "waiting", …) o "estática" para entradas solo-ARP.
    """
    lan = get_lan_prefix(api)
    arp_entries = api.command("/ip/arp/print")
    arp_map = {e["address"]: e.get("mac-address", "") for e in arp_entries
               if e.get("address", "").startswith(lan)}

    bridge_hosts = api.command("/interface/bridge/host/print")
    mac_to_port = {h["mac-address"]: h["interface"]
                   for h in bridge_hosts if h.get("local", "false") != "true"}

    leases = api.command("/ip/dhcp-server/lease/print")
    dhcp_ips = set()
    rows = []

    for lease in leases:
        ip       = lease.get("address", "")
        mac      = lease.get("mac-address", "")
        hostname = lease.get("host-name", "")
        dhcp_ips.add(ip)
        rows.append({
            "ip":     ip,
            "mac":    mac,
            "nombre": resolve_device_name(ip, mac, hostname, is_static=False),
            "estado": lease.get("status", "?"),
            "puerto": mac_to_port.get(mac, "—"),
            "tipo":   "DHCP",
        })

    for ip, mac in arp_map.items():
        if ip not in dhcp_ips:
            rows.append({
                "ip":     ip,
                "mac":    mac,
                "nombre": resolve_device_name(ip, mac, "", is_static=True),
                "estado": "estática",
                "puerto": mac_to_port.get(mac, "—"),
                "tipo":   "STATIC",
            })

    rows.sort(key=lambda r: list(map(int, r["ip"].split("."))))
    return rows


# ---------------------------------------------------------------------------
# Clasificación (scan_dispositivos)
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Escaneo avanzado (scan_dispositivos)
# ---------------------------------------------------------------------------

def escanear_red(api) -> tuple:
    """Recopila y enriquece la información de todos los dispositivos.

    Retorna (results, unknown_macs, oui_cache):
        results      — lista de dicts ordenada por IP con
                       {ip, mac, hostname, vendor, type, lease, expires, random}
        unknown_macs — [(ip, mac, oui)] sin fabricante conocido (candidatas
                       a lookup online con completar_vendors_online)
        oui_cache    — cache OUI→vendor cargado (se pasa al lookup online)
    """
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

        results.append({
            "ip":       ip,
            "mac":      mac,
            "hostname": d["hostname"],
            "vendor":   vendor,
            "type":     guess_device_type(mac, d["hostname"], vendor),
            "lease":    d["lease_type"],
            "expires":  fmt_lease_time(d["expires"]),
            "random":   is_random_mac(mac),
        })

    results.sort(key=lambda x: list(map(int, x["ip"].split("."))))
    return results, unknown_macs, oui_cache


def completar_vendors_online(results: list, unknown_macs: list, oui_cache: dict):
    """Consulta macvendors.com para las MACs desconocidas y actualiza results.

    Modifica results en el lugar (vendor + type) y persiste el cache OUI.
    """
    for ip, mac, oui in unknown_macs:
        v = lookup_mac_vendor_online(mac, oui_cache)
        if v:
            for r in results:
                if r["mac"] == mac:
                    r["vendor"] = v
                    r["type"]   = guess_device_type(mac, r["hostname"], v)
    save_oui_cache(oui_cache)


def filtrar_dispositivos(results: list, filter_type: str) -> list:
    """Filtra el escaneo por tipo: apple, mobile, iot o unknown."""
    if not filter_type:
        return results
    ft = filter_type.lower()
    if ft == "apple":
        return [r for r in results if "Apple" in r["type"]]
    if ft == "mobile":
        return [r for r in results if "📱" in r["type"]]
    if ft == "iot":
        return [r for r in results if "IoT" in r["type"]]
    if ft == "unknown":
        return [r for r in results if "Desconocido" in r["type"] or not r["vendor"]]
    return results
