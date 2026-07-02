#!/usr/bin/env python3
"""
mant_bloqueo.py — Bloquear / Desbloquear una IP en el firewall
=============================================================

Agrega o elimina una regla de bloqueo en /ip/firewall/filter.
La regla se agrega al inicio de la cadena FORWARD con action=drop
y un comentario identificador para poder quitarla fácilmente.

Regla que crea:
    chain=forward  src-address=<IP>  action=drop
    comment="BLOQUEADO-POR-MENU-<IP>"

Uso:
    python3 scripts/mant_bloqueo.py --block 192.168.5.22
    python3 scripts/mant_bloqueo.py --unblock 192.168.5.22
    python3 scripts/mant_bloqueo.py --list          # ver IPs bloqueadas
    python3 scripts/mant_bloqueo.py                 # modo interactivo
"""

import sys
import os
import argparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from lib import MikroTikAPI, load_config, build_name_map, C, run_script
from core.bloqueos import reglas_bloqueo, bloquear_ip, desbloquear_ip


def list_blocked(api):
    blocked = reglas_bloqueo(api)
    if not blocked:
        print(f"\n  {C.GREEN}No hay IPs bloqueadas por este script.{C.RESET}\n")
        return
    print(f"\n{C.BOLD}  IPs bloqueadas:{C.RESET}")
    print(f"  {'ID':<8} {'IP BLOQUEADA':<20} COMENTARIO")
    print(f"  {'─'*55}")
    for r in blocked:
        print(f"  {r.get('.id','?'):<8} {r.get('src-address','?'):<20} {r.get('comment','')}")
    print()


def block_ip(api, ip: str):
    # Verificar si ya está bloqueada
    for r in reglas_bloqueo(api):
        if r.get("src-address") == ip:
            print(f"\n  {C.WARN}⚠️  {ip} ya está bloqueada "
                  f"(ID: {r.get('.id')}){C.RESET}\n")
            return

    bloquear_ip(api, ip)
    print(f"\n  {C.ERR}🔴 IP bloqueada:{C.RESET} {C.BOLD}{ip}{C.RESET}\n")


def unblock_ip(api, ip: str):
    removed = desbloquear_ip(api, ip)
    if not removed:
        print(f"\n  {C.WARN}No hay regla de bloqueo para {ip}{C.RESET}\n")
        return
    print(f"\n  {C.GREEN}✅ Desbloqueo exitoso:{C.RESET} {C.BOLD}{ip}{C.RESET}\n")


def interactive_mode(api):
    """Modo interactivo cuando se ejecuta sin argumentos."""
    # Mostrar dispositivos conocidos para facilitar selección
    ip_name = build_name_map(api)

    print(f"\n{C.HEADER}  Gestión de bloqueo de IPs{C.RESET}\n")
    print(f"  {C.BOLD}[1]{C.RESET} Bloquear una IP")
    print(f"  {C.BOLD}[2]{C.RESET} Desbloquear una IP")
    print(f"  {C.BOLD}[3]{C.RESET} Ver IPs bloqueadas")
    print(f"  {C.BOLD}[0]{C.RESET} Volver al menú\n")

    opcion = input(f"  {C.CYAN}Selecciona una opción: {C.RESET}").strip()

    if opcion == "1":
        print(f"\n  Dispositivos en la red:\n")
        sorted_ips = sorted(ip_name.keys(),
                           key=lambda x: list(map(int, x.split("."))))
        for ip in sorted_ips:
            print(f"    {ip:<16}  {ip_name[ip]}")
        ip = input(f"\n  {C.CYAN}IP a bloquear: {C.RESET}").strip()
        if ip:
            confirm = input(f"  {C.WARN}¿Confirmar bloqueo de {ip}? [s/N]: {C.RESET}").strip().lower()
            if confirm == "s":
                block_ip(api, ip)
            else:
                print(f"  {C.DIM}Cancelado.{C.RESET}\n")

    elif opcion == "2":
        list_blocked(api)
        ip = input(f"  {C.CYAN}IP a desbloquear: {C.RESET}").strip()
        if ip:
            unblock_ip(api, ip)

    elif opcion == "3":
        list_blocked(api)


def main():
    parser = argparse.ArgumentParser(
        description="Bloquear/desbloquear IPs en el firewall MikroTik")
    parser.add_argument("--block",   metavar="IP", help="Bloquear esta IP")
    parser.add_argument("--unblock", metavar="IP", help="Desbloquear esta IP")
    parser.add_argument("--list",    action="store_true",
                        help="Listar IPs bloqueadas")
    args = parser.parse_args()

    cfg = load_config()
    print(f"\n{C.DIM}Conectando a {cfg['host']}...{C.RESET}")

    with MikroTikAPI(**cfg) as api:
        if args.list:
            list_blocked(api)
        elif args.block:
            block_ip(api, args.block)
        elif args.unblock:
            unblock_ip(api, args.unblock)
        else:
            interactive_mode(api)


if __name__ == "__main__":
    run_script(main)
