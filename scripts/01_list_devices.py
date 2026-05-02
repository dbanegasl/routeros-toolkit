#!/usr/bin/env python3
"""
01_list_devices.py — Lista todos los dispositivos conectados a la red
======================================================================

Muestra:
  - Todos los leases DHCP activos (dispositivos con IP asignada)
  - Dispositivos con IP estática detectados en la tabla ARP
  - Puerto físico del switch al que está conectado cada dispositivo
  - Fabricante del hardware según el OUI de la MAC

Uso:
    cd mikrotik/
    python3 scripts/01_list_devices.py

    # Filtrar por nombre:
    python3 scripts/01_list_devices.py | grep -i samsung

Requiere:
    - config.env con las credenciales del router
    - Python 3.6+, sin dependencias externas
"""

import sys
import os

# Permite importar la lib desde cualquier directorio de trabajo
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lib import MikroTikAPI, load_config, resolve_device_name, C


def main():
    cfg = load_config()
    print(f"\n{C.DIM}Conectando a {cfg['host']}:{cfg['port']}...{C.RESET}")

    with MikroTikAPI(**cfg) as api:

        arp_entries = api.command("/ip/arp/print")
        arp_map = {e["address"]: e.get("mac-address", "") for e in arp_entries
                   if e.get("address", "").startswith("192.168.")}

        bridge_hosts = api.command("/interface/bridge/host/print")
        mac_to_port = {h["mac-address"]: h["interface"]
                       for h in bridge_hosts if h.get("local", "false") != "true"}

        leases = api.command("/ip/dhcp-server/lease/print")
        dhcp_ips = set()
        rows = []

        for lease in leases:
            ip     = lease.get("address", "")
            mac    = lease.get("mac-address", "")
            hostname = lease.get("host-name", "")
            status = lease.get("status", "?")
            dhcp_ips.add(ip)
            port   = mac_to_port.get(mac, "—")
            name   = resolve_device_name(ip, mac, hostname, is_static=False)
            rows.append((ip, mac, name, status, port, "DHCP"))

        for ip, mac in arp_map.items():
            if ip not in dhcp_ips:
                port = mac_to_port.get(mac, "—")
                name = resolve_device_name(ip, mac, "", is_static=True)
                rows.append((ip, mac, name, "estática", port, "STATIC"))

        rows.sort(key=lambda r: list(map(int, r[0].split("."))))

        sep = "─" * 100
        print(f"\n{C.BOLD}{sep}{C.RESET}")
        print(f"  {C.HEADER}{'IP':<16} {'MAC':<18} {'NOMBRE / DISPOSITIVO':<32} "
              f"{'ESTADO':<10} {'PUERTO':<8} TIPO{C.RESET}")
        print(f"{C.BOLD}{sep}{C.RESET}")

        dhcp_count = static_count = 0
        for ip, mac, name, status, port, tipo in rows:
            if status == "estática":
                status_col = C.YELLOW
                tipo_col   = C.YELLOW
                static_count += 1
            elif status == "bound":
                status_col = C.GREEN
                tipo_col   = C.DIM
                dhcp_count += 1
            else:
                status_col = C.WARN
                tipo_col   = C.DIM
                dhcp_count += 1

            print(f"  {C.CYAN}{ip:<16}{C.RESET} {C.DIM}{mac:<18}{C.RESET} "
                  f"{C.BOLD}{name:<32}{C.RESET} "
                  f"{status_col}{status:<10}{C.RESET} "
                  f"{port:<8} {tipo_col}{tipo}{C.RESET}")

        print(f"{C.BOLD}{sep}{C.RESET}")
        print(f"\n  Total: {C.BOLD}{len(rows)}{C.RESET} dispositivos  "
              f"({C.GREEN}{dhcp_count} DHCP{C.RESET}, "
              f"{C.YELLOW}{static_count} IP estática{C.RESET})\n")


if __name__ == "__main__":
    main()
