#!/usr/bin/env python3
"""
info_dispositivos.py — Lista todos los dispositivos conectados a la red
======================================================================

Muestra:
  - Todos los leases DHCP activos (dispositivos con IP asignada)
  - Dispositivos con IP estática detectados en la tabla ARP
  - Puerto físico del switch al que está conectado cada dispositivo
  - Fabricante del hardware según el OUI de la MAC

Uso:
    cd mikrotik/
    python3 scripts/info_dispositivos.py

    # Filtrar por nombre:
    python3 scripts/info_dispositivos.py | grep -i samsung

Requiere:
    - config.env con las credenciales del router
    - Python 3.6+, sin dependencias externas
"""

import sys
import os

# Permite importar la lib desde cualquier directorio de trabajo
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lib import MikroTikAPI, load_config, C, run_script
from core.dispositivos import inventario_dispositivos


def main():
    cfg = load_config()
    print(f"\n{C.DIM}Conectando a {cfg['host']}:{cfg['port']}...{C.RESET}")

    with MikroTikAPI(**cfg) as api:
        rows = inventario_dispositivos(api)

        sep = "─" * 100
        print(f"\n{C.BOLD}{sep}{C.RESET}")
        print(f"  {C.HEADER}{'IP':<16} {'MAC':<18} {'NOMBRE / DISPOSITIVO':<32} "
              f"{'ESTADO':<10} {'PUERTO':<8} TIPO{C.RESET}")
        print(f"{C.BOLD}{sep}{C.RESET}")

        dhcp_count = static_count = 0
        for d in rows:
            status = d["estado"]
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

            print(f"  {C.CYAN}{d['ip']:<16}{C.RESET} {C.DIM}{d['mac']:<18}{C.RESET} "
                  f"{C.BOLD}{d['nombre']:<32}{C.RESET} "
                  f"{status_col}{status:<10}{C.RESET} "
                  f"{d['puerto']:<8} {tipo_col}{d['tipo']}{C.RESET}")

        print(f"{C.BOLD}{sep}{C.RESET}")
        print(f"\n  Total: {C.BOLD}{len(rows)}{C.RESET} dispositivos  "
              f"({C.GREEN}{dhcp_count} DHCP{C.RESET}, "
              f"{C.YELLOW}{static_count} IP estática{C.RESET})\n")


if __name__ == "__main__":
    run_script(main)
