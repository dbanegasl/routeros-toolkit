#!/usr/bin/env python3
"""
menu.py — Menú principal de herramientas MikroTik
==================================================

Punto de entrada unificado. Navega con números y Enter.
Ctrl+C en cualquier momento vuelve al menú principal.

Uso:
    cd /home/daniel/dev/support/mikrotik/
    python3 menu.py

    # O directamente (si tiene permisos de ejecución):
    ./menu.py
"""

import sys
import os
import subprocess
import time

# Directorio base del proyecto (donde vive este archivo)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPTS  = os.path.join(BASE_DIR, "scripts")
sys.path.insert(0, BASE_DIR)

from lib import MikroTikAPI, load_config, C


# ──────────────────────────────────────────────────────────────────────────────
# Definición del menú
# Estructura: (key, label, script, args_hint, description)
# ──────────────────────────────────────────────────────────────────────────────

MENU = {
    "info": {
        "title": "📊  INFORMACIÓN",
        "items": [
            ("1", "Inventario de dispositivos",
             "01_list_devices.py", "",
             "Lista todos los dispositivos con IP, MAC, fabricante y puerto"),
            ("2", "Estadísticas por interfaz",
             "04_interface_stats.py", "",
             "Tráfico total y velocidad actual por interfaz física"),
            ("3", "Estadísticas por interfaz (medir velocidad real)",
             "04_interface_stats.py", "--watch",
             "Toma 2 muestras con 5s de intervalo y calcula velocidad"),
            ("7", "Información del sistema",
             "07_system_info.py", "",
             "CPU, RAM, disco, uptime, versión de RouterOS"),
        ],
    },
    "monitor": {
        "title": "📈  MONITOREO DE RED",
        "items": [
            ("4", "Top consumidores (snapshot)",
             "02_top_consumers.py", "",
             "¿Quién usa más internet ahora mismo?"),
            ("5", "Top consumidores por datos totales",
             "02_top_consumers.py", "--sort total",
             "Ordenado por GB acumulados en esta sesión"),
            ("6", "Monitor en vivo (auto-refresh)",
             "03_live_monitor.py", "",
             "Dashboard que se actualiza cada 3s  ─  Ctrl+C para volver"),
        ],
    },
    "maint": {
        "title": "🔧  MANTENIMIENTO",
        "items": [
            ("8",  "Ver log del router",
             "05_router_log.py", "",
             "Últimas 50 entradas del syslog con colores por nivel"),
            ("9",  "Ver log en vivo (follow)",
             "05_router_log.py", "--follow",
             "Log que se actualiza cada 3s  ─  Ctrl+C para volver"),
            ("10", "Bloquear / Desbloquear IP",
             "06_block_ip.py", "",
             "Agrega o quita reglas de bloqueo en el firewall"),
            ("11", "Ver IPs bloqueadas",
             "06_block_ip.py", "--list",
             "Lista todas las IPs bloqueadas por este gestor"),
        ],
    },
    "system": {
        "title": "⚙️   SISTEMA",
        "items": [
            ("12", "Probar conexión al router",
             None, "",
             "Verifica que el router esté accesible y el login sea correcto"),
            ("13", "Ver configuración actual",
             None, "",
             "Muestra el contenido de config.env (sin la contraseña)"),
        ],
    },
}


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def clear():
    print("\033[H\033[J", end="", flush=True)


def pause():
    input(f"\n  {C.DIM}Presiona Enter para volver al menú...{C.RESET}")


def run_script(script: str, args: str = ""):
    """Ejecuta un script como subproceso con terminal completo."""
    script_path = os.path.join(SCRIPTS, script)
    cmd = [sys.executable, script_path] + (args.split() if args else [])
    print()
    try:
        subprocess.run(cmd, cwd=BASE_DIR)
    except KeyboardInterrupt:
        print(f"\n  {C.DIM}Interrumpido — volviendo al menú...{C.RESET}")
        time.sleep(0.8)


def test_connection():
    """Prueba la conexión al router y muestra información básica."""
    cfg = load_config()
    print(f"\n  Probando conexión a {C.CYAN}{cfg['host']}:{cfg['port']}{C.RESET}...\n")
    try:
        with MikroTikAPI(**cfg) as api:
            res = api.command("/system/resource/print")
            identity = api.command("/system/identity/print")
            if res:
                r = res[0]
                name = identity[0].get("name", "?") if identity else "?"
                print(f"  {C.GREEN}✅ Conexión exitosa{C.RESET}\n")
                print(f"  {C.BOLD}Nombre:    {C.RESET}{name}")
                print(f"  {C.BOLD}Hardware:  {C.RESET}{r.get('board-name','?')}")
                print(f"  {C.BOLD}RouterOS:  {C.RESET}{r.get('version','?')}")
                print(f"  {C.BOLD}Uptime:    {C.RESET}{r.get('uptime','?')}")
                print(f"  {C.BOLD}CPU:       {C.RESET}{r.get('cpu-load','?')}%")
    except Exception as e:
        print(f"  {C.ERR}❌ Error: {e}{C.RESET}")


def show_config():
    """Muestra la configuración actual (sin la contraseña)."""
    cfg = load_config()
    env_file = os.path.join(BASE_DIR, "config.env")
    print(f"\n  {C.BOLD}Configuración activa:{C.RESET}\n")
    print(f"  {C.BOLD}Host:     {C.RESET}{C.CYAN}{cfg['host']}{C.RESET}")
    print(f"  {C.BOLD}Puerto:   {C.RESET}{cfg['port']}")
    print(f"  {C.BOLD}Usuario:  {C.RESET}{cfg['username']}")
    print(f"  {C.BOLD}Contraseña:{C.RESET} {'*' * len(cfg['password'])}")
    print(f"\n  {C.DIM}Archivo: {env_file}{C.RESET}")


# ──────────────────────────────────────────────────────────────────────────────
# Renderizado del menú
# ──────────────────────────────────────────────────────────────────────────────

def build_lookup() -> dict:
    """Construye un dict key → (script, args) para lookup rápido."""
    lookup = {}
    for section in MENU.values():
        for key, _label, script, args, _desc in section["items"]:
            lookup[key] = (script, args)
    return lookup


def render_menu(cfg: dict):
    clear()
    w = 70
    print(f"\n  {C.BOLD}{'═'*w}{C.RESET}")
    print(f"  {C.HEADER}{'  🌐  MikroTik Management Tool':^{w}}{C.RESET}")
    print(f"  {C.DIM}  Router: {cfg['host']}  ·  Usuario: {cfg['username']}{C.RESET}")
    print(f"  {C.BOLD}{'═'*w}{C.RESET}\n")

    for section in MENU.values():
        print(f"  {C.BOLD}{section['title']}{C.RESET}")
        print(f"  {C.DIM}{'─'*w}{C.RESET}")
        for key, label, _script, _args, desc in section["items"]:
            print(f"    {C.CYAN}[{key:>2}]{C.RESET}  {C.BOLD}{label:<40}{C.RESET}"
                  f"  {C.DIM}{desc}{C.RESET}")
        print()

    print(f"  {C.DIM}{'─'*w}{C.RESET}")
    print(f"    {C.CYAN}[ 0]{C.RESET}  {C.BOLD}Salir{C.RESET}\n")
    print(f"  {C.BOLD}{'═'*w}{C.RESET}\n")


# ──────────────────────────────────────────────────────────────────────────────
# Loop principal
# ──────────────────────────────────────────────────────────────────────────────

def main():
    cfg     = load_config()
    lookup  = build_lookup()

    while True:
        render_menu(cfg)
        try:
            opcion = input(f"  {C.CYAN}Selecciona una opción: {C.RESET}").strip()
        except (KeyboardInterrupt, EOFError):
            print(f"\n\n  {C.DIM}¡Hasta luego!{C.RESET}\n")
            break

        if opcion == "0":
            print(f"\n  {C.DIM}¡Hasta luego!{C.RESET}\n")
            break

        elif opcion == "12":
            test_connection()
            pause()

        elif opcion == "13":
            show_config()
            pause()

        elif opcion in lookup:
            script, args = lookup[opcion]
            run_script(script, args)
            pause()

        else:
            print(f"  {C.WARN}Opción no válida. Intenta de nuevo.{C.RESET}")
            time.sleep(1)


if __name__ == "__main__":
    main()
