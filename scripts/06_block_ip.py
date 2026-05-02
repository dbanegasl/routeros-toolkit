#!/usr/bin/env python3
"""
06_block_ip.py — Bloquear / Desbloquear dispositivos por MAC en el firewall
============================================================================

Bloquea por dirección MAC (src-mac-address) en lugar de IP, lo que hace el
bloqueo robusto: si el dispositivo cambia de IP sigue bloqueado.

Regla que crea:
    chain=forward  src-mac-address=<MAC>  action=drop
    comment="BLOQUEADO-POR-MENU-<MAC>"

Uso:
    python3 scripts/06_block_ip.py --block AA:BB:CC:DD:EE:FF
    python3 scripts/06_block_ip.py --unblock AA:BB:CC:DD:EE:FF
    python3 scripts/06_block_ip.py --list          # ver MACs bloqueadas
    python3 scripts/06_block_ip.py                 # modo interactivo

Nota: bloquear por IP es evadible cambiando la IP del dispositivo.
      El bloqueo por MAC persiste aunque el dispositivo tome otra IP.
"""

import sys
import os
import argparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from lib import MikroTikAPI, load_config, resolve_device_name, C

COMMENT_TAG = "BLOQUEADO-POR-MENU"


def get_blocked(api) -> list:
    """Retorna lista de reglas de bloqueo creadas por este script."""
    rules = api.command("/ip/firewall/filter/print")
    return [r for r in rules
            if r.get("comment", "").startswith(COMMENT_TAG)]


def list_blocked(api):
    blocked = get_blocked(api)
    if not blocked:
        print(f"\n  {C.GREEN}No hay dispositivos bloqueados por este script.{C.RESET}\n")
        return
    print(f"\n{C.BOLD}  Dispositivos bloqueados:{C.RESET}")
    print(f"  {'ID':<8} {'MAC BLOQUEADA':<22} COMENTARIO")
    print(f"  {'─'*60}")
    for r in blocked:
        mac = r.get("src-mac-address", r.get("src-address", "?"))
        print(f"  {r.get('.id','?'):<8} {mac:<22} {r.get('comment','')}")
    print()


def block_mac(api, mac: str):
    mac = mac.upper()
    blocked = get_blocked(api)
    for r in blocked:
        if r.get("src-mac-address", "").upper() == mac:
            print(f"\n  {C.WARN}⚠️  {mac} ya está bloqueada "
                  f"(ID: {r.get('.id')}){C.RESET}\n")
            return

    api.command("/ip/firewall/filter/add", params=[
        "=chain=forward",
        f"=src-mac-address={mac}",
        "=action=drop",
        f"=comment={COMMENT_TAG}-{mac}",
    ])
    print(f"\n  {C.ERR}🔴 MAC bloqueada:{C.RESET} {C.BOLD}{mac}{C.RESET}")
    print(f"  {C.DIM}(el bloqueo persiste aunque el dispositivo cambie de IP){C.RESET}\n")


def unblock_mac(api, mac: str):
    mac = mac.upper()
    blocked = get_blocked(api)
    found = [r for r in blocked if r.get("src-mac-address", "").upper() == mac]
    if not found:
        print(f"\n  {C.WARN}No hay regla de bloqueo para {mac}{C.RESET}\n")
        return
    for r in found:
        api.command("/ip/firewall/filter/remove",
                    params=[f"=.id={r['.id']}"])
    print(f"\n  {C.GREEN}✅ Desbloqueo exitoso:{C.RESET} {C.BOLD}{mac}{C.RESET}\n")


def build_device_map(api) -> dict:
    """Construye mapa ip -> {name, mac, static} combinando DHCP y ARP."""
    leases = api.command("/ip/dhcp-server/lease/print")
    arp    = api.command("/ip/arp/print")

    devices = {}
    for l in leases:
        ip  = l.get("address", "")
        mac = l.get("mac-address", "")
        if ip:
            devices[ip] = {
                "mac":    mac,
                "name":   resolve_device_name(ip, mac, l.get("host-name",""), False),
                "static": False,
            }
    for e in arp:
        ip  = e.get("address", "")
        mac = e.get("mac-address", "")
        if ip.startswith("192.168.") and ip not in devices and mac:
            devices[ip] = {
                "mac":    mac,
                "name":   resolve_device_name(ip, mac, "", True),
                "static": True,
            }
    return devices


def print_device_table(devices: dict):
    """Imprime la lista de dispositivos con IP, MAC y nombre."""
    print(f"\n  {'IP':<18} {'MAC':<20} NOMBRE")
    print(f"  {'─'*65}")
    for ip in sorted(devices.keys(), key=lambda x: list(map(int, x.split(".")))):
        d = devices[ip]
        print(f"  {ip:<18} {d['mac']:<20} {d['name']}")
    print()


def interactive_mode(api):
    devices = build_device_map(api)

    print(f"\n{C.HEADER}  Gestión de bloqueo de dispositivos{C.RESET}\n")
    print(f"  {C.BOLD}[1]{C.RESET} Bloquear un dispositivo (por MAC)")
    print(f"  {C.BOLD}[2]{C.RESET} Desbloquear un dispositivo (por MAC)")
    print(f"  {C.BOLD}[3]{C.RESET} Ver dispositivos bloqueados")
    print(f"  {C.BOLD}[0]{C.RESET} Volver al menú\n")

    opcion = input(f"  {C.CYAN}Selecciona una opción: {C.RESET}").strip()

    if opcion == "1":
        print_device_table(devices)
        print(f"  {C.DIM}Puedes ingresar la IP (ej: 192.168.1.60) o la MAC directamente.{C.RESET}")
        entrada = input(f"\n  {C.CYAN}IP o MAC a bloquear: {C.RESET}").strip()
        if not entrada:
            return

        # Resolver MAC si ingresó una IP
        if "." in entrada:
            ip = entrada
            d  = devices.get(ip)
            if not d or not d["mac"]:
                print(f"\n  {C.WARN}No se encontró MAC para {ip}. Ingresa la MAC manualmente.{C.RESET}\n")
                return
            mac  = d["mac"]
            name = d["name"]
            print(f"\n  {C.DIM}Dispositivo: {name} — MAC: {mac}{C.RESET}")
        else:
            mac  = entrada
            name = mac

        confirm = input(f"  {C.WARN}¿Confirmar bloqueo de {name} ({mac})? [s/N]: {C.RESET}").strip().lower()
        if confirm == "s":
            block_mac(api, mac)
        else:
            print(f"  {C.DIM}Cancelado.{C.RESET}\n")

    elif opcion == "2":
        list_blocked(api)
        print_device_table(devices)
        entrada = input(f"  {C.CYAN}IP o MAC a desbloquear: {C.RESET}").strip()
        if not entrada:
            return
        if "." in entrada:
            d = devices.get(entrada)
            if not d or not d["mac"]:
                print(f"\n  {C.WARN}No se encontró MAC para {entrada}.{C.RESET}\n")
                return
            entrada = d["mac"]
        unblock_mac(api, entrada)

    elif opcion == "3":
        list_blocked(api)


def main():
    parser = argparse.ArgumentParser(
        description="Bloquear/desbloquear dispositivos por MAC en MikroTik")
    parser.add_argument("--block",   metavar="MAC", help="Bloquear esta MAC")
    parser.add_argument("--unblock", metavar="MAC", help="Desbloquear esta MAC")
    parser.add_argument("--list",    action="store_true",
                        help="Listar MACs bloqueadas")
    args = parser.parse_args()

    cfg = load_config()
    print(f"\n{C.DIM}Conectando a {cfg['host']}...{C.RESET}")

    with MikroTikAPI(**cfg) as api:
        if args.list:
            list_blocked(api)
        elif args.block:
            block_mac(api, args.block)
        elif args.unblock:
            unblock_mac(api, args.unblock)
        else:
            interactive_mode(api)


if __name__ == "__main__":
    main()
