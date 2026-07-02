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
#
# Numeración por décadas — el primer dígito indica la sección:
#   1–9 Información · 10–19 Monitoreo · 20–29 Mantenimiento
#   30–39 Identificación · 40–49 Horario · 50–59 QoS · 90–99 Sistema
# Al agregar una opción, usar el siguiente número libre de su década.
# ──────────────────────────────────────────────────────────────────────────────

MENU = {
    "info": {
        "title": "📊  INFORMACIÓN  [1–9]",
        "items": [
            ("1", "Inventario de dispositivos",
             "info_dispositivos.py", "",
             "Lista todos los dispositivos con IP, MAC, fabricante y puerto"),
            ("2", "Estadísticas por interfaz",
             "info_interfaces.py", "",
             "Tráfico total y velocidad actual por interfaz física"),
            ("3", "Medir velocidad real por interfaz",
             "info_interfaces.py", "--watch",
             "Toma 2 muestras con 5s de intervalo y calcula velocidad"),
            ("4", "Información del sistema",
             "info_sistema.py", "",
             "CPU, RAM, disco, uptime, versión de RouterOS"),
        ],
    },
    "monitor": {
        "title": "📈  MONITOREO DE RED  [10–19]",
        "items": [
            ("10", "Top consumidores (snapshot)",
             "mon_consumo.py", "",
             "¿Quién usa más internet ahora mismo?"),
            ("11", "Top consumidores por datos totales",
             "mon_consumo.py", "--sort total",
             "Ordenado por GB acumulados en esta sesión"),
            ("12", "Monitor en vivo (auto-refresh)",
             "mon_vivo.py", "",
             "Dashboard que se actualiza cada 3s  ─  Ctrl+C para volver"),
        ],
    },
    "maint": {
        "title": "🔧  MANTENIMIENTO  [20–29]",
        "items": [
            ("20", "Ver log del router",
             "mant_log.py", "",
             "Últimas 50 entradas del syslog con colores por nivel"),
            ("21", "Ver log en vivo (follow)",
             "mant_log.py", "--follow",
             "Log que se actualiza cada 3s  ─  Ctrl+C para volver"),
            ("22", "Bloquear / Desbloquear dispositivo",
             "mant_bloqueo.py", "",
             "Agrega o quita reglas de bloqueo en el firewall por MAC"),
            ("23", "Ver dispositivos bloqueados",
             "mant_bloqueo.py", "--list",
             "Lista todos los dispositivos bloqueados por este gestor"),
            ("24", "Respaldar configuración",
             "mant_respaldo.py", "",
             "Snapshot local de firewall/colas/leases — solo lectura"),
            ("25", "Ver respaldos existentes",
             "mant_respaldo.py", "--list",
             "Lista snapshots locales y archivos .backup del router"),
        ],
    },
    "scan": {
        "title": "🔍  IDENTIFICACIÓN  [30–39]",
        "items": [
            ("30", "Escanear y clasificar dispositivos",
             "scan_dispositivos.py", "",
             "Identifica fabricante y tipo de cada dispositivo en la red"),
            ("31", "Escanear con lookup online",
             "scan_dispositivos.py", "--lookup",
             "Consulta macvendors.com para MACs desconocidas (más lento)"),
            ("32", "Buscar dispositivos Apple",
             "scan_dispositivos.py", "--filter apple",
             "Muestra solo iPhones, iPads, Macs y otros Apple"),
            ("33", "Buscar dispositivos móviles",
             "scan_dispositivos.py", "--filter mobile",
             "Muestra solo teléfonos y tablets (incluyendo MAC privada)"),
        ],
    },
    "schedule": {
        "title": "⏰  HORARIO DE INTERNET  [40–49]",
        "items": [
            ("40", "Programar corte de internet",
             "horario_internet.py", "",
             "Bloquea TODOS en un horario — configura inicio, fin y días"),
            ("41", "Ver estado del corte",
             "horario_internet.py", "--list",
             "Horario, si está en curso ahora, y lista blanca"),
            ("42", "Gestionar lista blanca (excepciones)",
             "horario_internet.py", "--allow",
             "Elige qué dispositivos siempre tienen internet (WiFi, cámaras…)"),
            ("43", "Eliminar corte programado",
             "horario_internet.py", "--remove",
             "Borra las reglas del router — pide confirmación"),
        ],
    },
    "qos": {
        "title": "🚦  CALIDAD DE SERVICIO (QoS)  [50–59]",
        "items": [
            ("50", "Ver plan QoS (dry-run)",
             "qos_desplegar.py", "--dry-run",
             "Muestra cada regla y cola que se crearía — NO toca el router"),
            ("51", "Desplegar QoS",
             "qos_desplegar.py", "",
             "Aplica 23 reglas Mangle + 16 colas — pide confirmación"),
            ("52", "Diagnosticar QoS",
             "qos_diagnostico.py", "",
             "Verifica si las reglas están marcando tráfico (solo lectura)"),
            ("53", "Monitor QoS en tiempo real",
             "qos_monitor.py", "",
             "Ancho de banda por categoría  ─  Ctrl+C para volver"),
            ("54", "Eliminar QoS (reset)",
             "qos_reset.py", "",
             "Borra solo los elementos QoS del router — pide confirmación"),
        ],
    },
    "system": {
        "title": "⚙️   SISTEMA  [90–99]",
        "items": [
            ("90", "Probar conexión al router",
             None, "",
             "Verifica que el router esté accesible y el login sea correcto"),
            ("91", "Ver configuración actual",
             None, "",
             "Muestra el contenido de config.env (sin la contraseña)"),
            ("92", "Validación completa del router",
             "sys_validar.py", "",
             "Chequeo previo: interfaces, IPs, FastTrack, reloj y QoS"),
        ],
    },
}

# Opciones que modifican el router de forma inmediata al lanzarse (el script
# no vuelve a preguntar): el menú exige confirmación explícita antes.
CONFIRMAR = {
    "43": ("Esto eliminará el corte programado y sus reglas del router "
           "(la lista blanca queda guardada en config/whitelist.json)."),
    "51": "Esto desplegará el plan QoS completo (Mangle + Queue Tree) y deshabilitará FastTrack.",
    "54": "Esto eliminará todas las reglas y colas QoS del router y rehabilitará FastTrack.",
}


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def clear():
    print("\033[H\033[J", end="", flush=True)


def pause():
    input(f"\n  {C.DIM}Presiona Enter para volver al menú...{C.RESET}")


def confirmar(mensaje: str) -> bool:
    """Pide confirmación explícita antes de una acción que modifica el router."""
    print(f"\n  {C.WARN}⚠️  {mensaje}{C.RESET}")
    try:
        resp = input(f"  ¿Continuar? (s/N): ").strip().lower()
    except (KeyboardInterrupt, EOFError):
        print()
        return False
    return resp in ("s", "si", "sí")


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

        elif opcion == "90":
            test_connection()
            pause()

        elif opcion == "91":
            show_config()
            pause()

        elif opcion in lookup:
            if opcion in CONFIRMAR and not confirmar(CONFIRMAR[opcion]):
                print(f"  {C.DIM}Cancelado — no se hizo ningún cambio.{C.RESET}")
                time.sleep(1)
                continue
            script, args = lookup[opcion]
            run_script(script, args)
            pause()

        else:
            print(f"  {C.WARN}Opción no válida. Intenta de nuevo.{C.RESET}")
            time.sleep(1)


if __name__ == "__main__":
    main()
