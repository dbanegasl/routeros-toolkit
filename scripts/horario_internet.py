#!/usr/bin/env python3
"""
horario_internet.py — Corte de internet por horario con lista blanca
=========================================================================

Estrategia (la más segura):
    1. Reglas ACCEPT por MAC  →  dispositivos aprobados (WiFi, cámaras, padres…)
                                  se crean SIN límite de tiempo → siempre con acceso
    2. Regla DROP global      →  bloquea TODOS los demás durante el horario

Resultado:
    - Dispositivos en lista blanca: internet 24h, sin corte.
    - Cualquier otro dispositivo (incluyendo MACs nuevas/desconocidas):
      sin internet en el horario definido, automáticamente.

Orden de procesamiento en RouterOS (top-down, primera coincidencia gana):
    [ACCEPT MAC=phone-papa]   → pasa siempre
    [ACCEPT MAC=camara-sala]  → pasa siempre
    [DROP   time=01:00-06:00] → bloquea a todos los demás en ese rango

¿Es seguro?
    ✅  No toca bridges, interfaces ni rutas.
    ✅  Completamente reversible con --remove.
    ✅  Nuevos dispositivos quedan bloqueados por defecto.

Persistencia:
    La lista blanca se guarda en config/whitelist.json y sobrevive a
    --remove: al programar un nuevo corte se reaplica automáticamente
    sin tener que agregar los dispositivos de nuevo.

Requisito: router con hora correcta (NTP activo).

Uso:
    python3 scripts/horario_internet.py              # configurar horario
    python3 scripts/horario_internet.py --list       # ver estado actual
    python3 scripts/horario_internet.py --allow      # gestionar lista blanca
    python3 scripts/horario_internet.py --remove     # eliminar todo
"""

import sys
import os
import argparse
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from lib import (MikroTikAPI, load_config, build_device_map,
                 get_mac_vendor_cache, C, run_script)
from core.horario import (DROP_TAG, ALLOW_TAG, DAYS_MAP, DAYS_LABEL, ALL_DAYS,
                          get_wan_interface, get_drop_rule, get_allow_rules,
                          normalize_ros_time, parse_drop_time, corte_en_curso,
                          get_router_now, remove_all_rules, apply_all_rules,
                          aplicar_solo_whitelist, load_whitelist, save_whitelist)


# ---------------------------------------------------------------------------
# Input helpers
# ---------------------------------------------------------------------------

def ask_time(prompt: str) -> str:
    while True:
        raw = input(f"  {prompt} (HH:MM): ")
        # Normaliza: elimina espacios, AM/PM, acepta punto o dos puntos
        val = "".join(c for c in raw if c.isprintable()).strip()
        val = val.upper().replace("AM", "").replace("PM", "").strip()
        val = val.replace(".", ":")  # acepta 1.10 → 1:10
        parts = [p.strip() for p in val.split(":")]
        if len(parts) >= 2:
            try:
                h, m = int(parts[0]), int(parts[1])
                if 0 <= h <= 23 and 0 <= m <= 59:
                    return f"{h:02d}:{m:02d}:00"
            except ValueError:
                pass
        print(f"  {C.WARN}Formato inválido. Usa HH:MM (ej: 01:00 o 1.10){C.RESET}")


def ask_days() -> list:
    print(f"\n  {C.BOLD}Días del corte:{C.RESET}")
    print(f"  1=Lun  2=Mar  3=Mié  4=Jue  5=Vie  6=Sáb  7=Dom")
    print(f"  {C.DIM}Enter sin nada = todos los días.{C.RESET}")
    raw = input("  Días [1-7 separados por coma, Enter=todos]: ").strip()
    if not raw:
        return ALL_DAYS
    selected = []
    for ch in raw.replace(" ", "").split(","):
        if ch in DAYS_MAP and DAYS_MAP[ch] not in selected:
            selected.append(DAYS_MAP[ch])
    return selected if selected else ALL_DAYS


# ---------------------------------------------------------------------------
# Ver estado actual
# ---------------------------------------------------------------------------

def _fmt_counter(val: str) -> str:
    """Formatea bytes/paquetes con sufijo K/M."""
    n = int(val)
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n/1_000:.1f}K"
    return str(n)


def list_rules(api):
    drop    = get_drop_rule(api)
    allows  = get_allow_rules(api)
    stored  = load_whitelist()
    devices = build_device_map(api, by="mac")

    print(f"\n  {C.BOLD}{'═'*65}{C.RESET}")
    print(f"  {C.HEADER}  ⏰  Estado del corte de internet por horario{C.RESET}")
    print(f"  {C.BOLD}{'═'*65}{C.RESET}")

    if not drop:
        print(f"\n  {C.GREEN}No hay ningún corte programado.{C.RESET}")
        if stored:
            print(f"\n  {C.DIM}💾 Lista blanca guardada "
                  f"({len(stored)} dispositivo(s)) — se aplicará "
                  f"automáticamente al programar un corte:{C.RESET}")
            for mac in sorted(stored):
                nombre = stored[mac].get("nombre") or "—"
                print(f"     {C.GREEN}✓{C.RESET} {mac:<20} {nombre}")
        print()
        return

    # Desincronización archivo ↔ router
    applied_macs = {r.get("src-mac-address", "").upper() for r in allows}
    solo_archivo = set(stored) - applied_macs
    solo_router  = applied_macs - set(stored)
    if solo_archivo:
        print(f"\n  {C.WARN}⚠️  {len(solo_archivo)} dispositivo(s) del archivo "
              f"NO están aplicados en el router:{C.RESET}")
        for mac in sorted(solo_archivo):
            print(f"     • {mac} {stored[mac].get('nombre', '')}")
        print(f"  {C.DIM}Ejecuta --allow y confirma para sincronizar.{C.RESET}")
    if solo_router:
        print(f"\n  {C.WARN}⚠️  {len(solo_router)} regla(s) del router no "
              f"están en config/whitelist.json (se agregarán al usar --allow).{C.RESET}")

    start, end, days = parse_drop_time(drop)
    days_labels = ", ".join(DAYS_LABEL.get(d, d) for d in days)

    # Contadores de la regla DROP
    pkts  = _fmt_counter(drop.get("packets", "0"))
    bytes_ = _fmt_counter(drop.get("bytes", "0"))
    if drop.get("packets", "0") != "0":
        hit_str = f"{C.ERR}🚫 {pkts} paquetes bloqueados ({bytes_} B){C.RESET}"
    else:
        hit_str = f"{C.DIM}Sin actividad aún (0 paquetes){C.RESET}"

    # ¿Está bloqueando AHORA? (reloj del router; si falla, reloj local)
    ahora = get_router_now(api)
    fuente_reloj = "hora del router"
    if ahora is None:
        local = datetime.now()
        ahora = (local.hour * 60 + local.minute,
                 ALL_DAYS[local.weekday()],
                 f"{local.hour:02d}:{local.minute:02d}")
        fuente_reloj = "hora de este PC"
    now_min, today, hhmm = ahora
    en_curso = corte_en_curso(start, end, days, now_min, today)

    print(f"\n  {C.BOLD}⏰ Corte programado:{C.RESET}")
    print(f"     Interfaz WAN    : {C.CYAN}{drop.get('out-interface','?')}{C.RESET}")
    print(f"     Sin internet    : {C.ERR}{start[:5]}{C.RESET} → {C.ERR}{end[:5]}{C.RESET}")
    print(f"     Días            : {days_labels}")
    print(f"     Afecta a        : {C.BOLD}TODOS{C.RESET} los no listados abajo")
    if en_curso:
        print(f"     Ahora mismo     : {C.ERR}⛔ EN CURSO — bloqueando internet "
              f"(hasta las {end[:5]}){C.RESET}")
    else:
        print(f"     Ahora mismo     : {C.GREEN}🟢 Fuera de horario — "
              f"internet normal{C.RESET}")
    print(f"                       {C.DIM}({fuente_reloj}: {hhmm}){C.RESET}")
    print(f"     Tráfico cortado : {hit_str}")

    if allows:
        allowed_macs = {r.get("src-mac-address", "").upper() for r in allows}
        # Construir mapa mac → regla para sacar contadores
        allow_map = {r.get("src-mac-address", "").upper(): r for r in allows}
        print(f"\n  {C.GREEN}✅ Lista blanca — siempre con internet "
              f"({len(allowed_macs)} dispositivo(s)):{C.RESET}")
        print(f"     {'MAC':<19} {'IP':<16} {'TRÁFICO':<9} {'EN RED':<7} NOMBRE")
        print(f"  {'─'*76}")
        for mac in sorted(allowed_macs):
            dev    = devices.get(mac)
            en_red = dev is not None
            ip     = dev["ip"] if en_red else "—"
            # Nombre: el de la red si está conectado; si no, el guardado
            # en config/whitelist.json (no se pierde por estar offline)
            name = ((dev.get("name") if en_red else None)
                    or stored.get(mac, {}).get("nombre")
                    or "—")
            rule = allow_map.get(mac, {})
            traf = (f"{_fmt_counter(rule['bytes'])}B"
                    if rule.get("bytes", "0") != "0" else "—")
            traf_c = C.GREEN if traf != "—" else C.DIM
            red    = "sí" if en_red else "no"
            red_c  = C.GREEN if en_red else C.DIM
            print(f"  {C.GREEN}✓{C.RESET}  {mac:<19} {ip:<16} "
                  f"{traf_c}{traf:<9}{C.RESET} {red_c}{red:<7}{C.RESET} {name}")
    else:
        print(f"\n  {C.WARN}⚠️  Lista blanca vacía — el corte aplica a "
              f"TODOS los dispositivos.{C.RESET}")
        print(f"  {C.DIM}Usa la opción 42 del menú para agregar excepciones.{C.RESET}")
    print()


# ---------------------------------------------------------------------------
# Gestionar lista blanca (excepciones)
# ---------------------------------------------------------------------------

def interactive_allow(api):
    """Agregar/quitar dispositivos de la lista blanca (siempre con internet).

    La lista se persiste en config/whitelist.json y sobrevive a --remove.
    """
    drop         = get_drop_rule(api)
    allows       = get_allow_rules(api)
    stored       = load_whitelist()
    # Unión de lo aplicado en el router y lo persistido en el archivo:
    # así nada se pierde aunque estén desincronizados.
    allowed_macs = ({r.get("src-mac-address", "").upper() for r in allows}
                    | set(stored))
    devices      = build_device_map(api, by="mac")

    print(f"\n  {C.BOLD}{'═'*65}{C.RESET}")
    print(f"  {C.HEADER}  🛡️   Lista blanca — excepciones al corte de internet{C.RESET}")
    print(f"  {C.BOLD}{'═'*65}{C.RESET}")

    if drop:
        start, end, days = parse_drop_time(drop)
        wan         = drop.get("out-interface", "")
        days_labels = ", ".join(DAYS_LABEL.get(d, d) for d in days)
        print(f"\n  {C.DIM}Corte programado: {start[:5]} → {end[:5]}  |  {days_labels}{C.RESET}")
    else:
        wan = get_wan_interface(api)
        start = end = ""
        days  = ALL_DAYS
        print(f"\n  {C.WARN}⚠️  Sin horario configurado aún.{C.RESET}")
        print(f"  {C.DIM}Puedes armar la lista blanca ahora y configurar el horario{C.RESET}")
        print(f"  {C.DIM}después con la opción 40. Los cambios se guardan en el router.{C.RESET}")

    print(f"\n  {C.DIM}Los dispositivos marcados con ✓ SIEMPRE tendrán internet.{C.RESET}")
    print(f"  {C.DIM}El resto queda sin internet en el horario del corte.{C.RESET}\n")

    all_devs = sorted(devices.items(), key=lambda x: x[1]["ip"])
    if not all_devs:
        print(f"  {C.WARN}No se detectaron dispositivos en la red.{C.RESET}\n")
        return

    vendor_cache = get_mac_vendor_cache()

    def get_vendor(mac: str) -> str:
        oui = mac[:8].upper()
        return vendor_cache.get(oui, "")[:14]  # truncar para que quepa

    print(f"  {'#':<4} {'✓':<3} {'IP':<16} {'FABRICANTE':<16} {'HOSTNAME':<20} NOMBRE")
    print(f"  {'─'*78}")

    indexed = []
    for mac_up, dev in all_devs:
        idx      = len(indexed) + 1
        allowed  = mac_up in allowed_macs
        marca    = f"{C.GREEN}✓{C.RESET}" if allowed else " "
        vendor   = get_vendor(dev['mac']) or f"{C.DIM}?{C.RESET}"
        hostname = (dev.get('hostname') or f"{C.DIM}—{C.RESET}")[:20]
        print(f"  {idx:<4} {marca}   {dev['ip']:<16} {vendor:<16} {hostname:<20} {dev['name']}")
        indexed.append(mac_up)

    # Dispositivos de la lista blanca que no están conectados ahora:
    # también se pueden quitar (toggle) aunque estén offline.
    for mac_up in sorted(m for m in stored if m not in devices):
        idx    = len(indexed) + 1
        nombre = stored[mac_up].get("nombre") or mac_up
        print(f"  {idx:<4} {C.GREEN}✓{C.RESET}   {'—':<16} {get_vendor(mac_up) or '?':<16} "
              f"{'—':<20} {nombre} {C.DIM}(no conectado){C.RESET}")
        indexed.append(mac_up)

    print(f"\n  {C.GREEN}✓{C.RESET} = siempre con internet  "
          f"│  sin marca = bloqueado en el horario")
    print(f"\n  Escribe los números para {C.GREEN}permitir{C.RESET}/{C.ERR}quitar{C.RESET} "
          f"de la lista blanca (toggle)")
    print(f"  {C.DIM}Enter sin nada = cancelar sin cambios{C.RESET}\n")

    raw = input("  Números [separados por coma]: ").strip()
    if not raw:
        print(f"\n  {C.DIM}Sin cambios.{C.RESET}\n")
        return

    new_allowed = set(allowed_macs)
    for token in raw.replace(" ", "").split(","):
        if not token.isdigit():
            continue
        idx = int(token) - 1
        if 0 <= idx < len(indexed):
            mac  = indexed[idx]
            name = devices.get(mac, {}).get("name", mac)
            if mac in new_allowed:
                new_allowed.discard(mac)
                print(f"  {C.ERR}−{C.RESET}  {name} → {C.ERR}quitado de lista blanca "
                      f"(quedará bloqueado en horario){C.RESET}")
            else:
                new_allowed.add(mac)
                print(f"  {C.GREEN}+{C.RESET}  {name} → {C.GREEN}agregado a lista blanca "
                      f"(siempre con internet){C.RESET}")

    if new_allowed == allowed_macs:
        print(f"\n  {C.DIM}Sin cambios.{C.RESET}\n")
        return

    confirm = input(f"\n  ¿Aplicar cambios en el router? (s/n): ").strip().lower()
    if confirm != "s":
        print(f"  {C.DIM}Cancelado.{C.RESET}\n")
        return

    # Persistir primero: el archivo es la fuente de verdad y sobrevive
    # a un --remove (no hay que rearmar la lista al reprogramar).
    save_whitelist(new_allowed, devices, stored)
    print(f"\n  {C.DIM}💾 Lista blanca guardada en config/whitelist.json{C.RESET}")

    if drop:
        # Reconstruir reglas DROP + ACCEPT
        remove_all_rules(api)
        apply_all_rules(api, wan, start, end, days, list(new_allowed))
        n = len(new_allowed)
        print(f"\n  {C.GREEN}✅ Lista blanca actualizada.{C.RESET} "
              f"{n} dispositivo(s) siempre con internet.")
        print(f"  {C.DIM}El resto quedará sin internet de "
              f"{start[:5]} a {end[:5]}.{C.RESET}\n")
    else:
        # Solo guardar ACCEPT — el DROP se añade cuando configuren el horario
        aplicar_solo_whitelist(api, wan, new_allowed)
        n = len(new_allowed)
        print(f"\n  {C.GREEN}✅ Lista blanca guardada ({n} dispositivo(s)).{C.RESET}")
        print(f"  {C.WARN}Configura el horario de corte con la opción 40{C.RESET}")
        print(f"  {C.DIM}para que la lista blanca entre en efecto.{C.RESET}\n")


# ---------------------------------------------------------------------------
# Configurar horario
# ---------------------------------------------------------------------------

def interactive_mode(api):
    wan = get_wan_interface(api)

    print(f"\n  {C.BOLD}{'═'*65}{C.RESET}")
    print(f"  {C.HEADER}  ⏰  Programar corte total de internet{C.RESET}")
    print(f"  {C.BOLD}{'═'*65}{C.RESET}")
    print(f"\n  {C.DIM}Bloquea TODOS los dispositivos en el horario elegido.{C.RESET}")
    print(f"  {C.DIM}Los que agregues a la lista blanca (opción 42) siempre{C.RESET}")
    print(f"  {C.DIM}tendrán internet. No toca bridges ni interfaces.{C.RESET}\n")

    if wan:
        print(f"  {C.DIM}Interfaz WAN detectada:{C.RESET} {C.CYAN}{wan}{C.RESET}")
    else:
        print(f"  {C.WARN}⚠️  No se detectó la interfaz WAN automáticamente.{C.RESET}")
        wan = input("  Ingresa el nombre de la interfaz WAN (ej: ether1): ").strip()
        if not wan:
            print(f"  {C.ERR}Cancelado.{C.RESET}\n")
            return

    drop   = get_drop_rule(api)
    allows = get_allow_rules(api)
    stored = load_whitelist()
    # Lista blanca = reglas ya aplicadas ∪ archivo persistido
    preserved_macs = sorted(
        {r.get("src-mac-address", "").upper() for r in allows} | set(stored))
    if stored and not allows:
        print(f"\n  {C.GREEN}💾 Lista blanca recuperada de config/whitelist.json "
              f"({len(stored)} dispositivo(s)){C.RESET}")

    if drop:
        print(f"\n  {C.WARN}⚠️  Ya hay un corte programado:{C.RESET}")
        list_rules(api)
        opt = input("  ¿Reemplazar el horario? (s/n): ").strip().lower()
        if opt != "s":
            print(f"  {C.DIM}Cancelado. Usa opción 42 para gestionar la lista blanca.{C.RESET}\n")
            return
        remove_all_rules(api)
        if preserved_macs:
            print(f"  {C.DIM}Se conservan {len(preserved_macs)} dispositivo(s) "
                  f"de la lista blanca.{C.RESET}")

    print(f"\n  Define cuándo {C.ERR}NO habrá internet{C.RESET} "
          f"(para todos los no permitidos):\n")
    start = ask_time("Hora de INICIO del corte")
    end   = ask_time("Hora de FIN   del corte")
    days  = ask_days()

    days_labels = ", ".join(DAYS_LABEL.get(d, d) for d in days)
    print(f"\n  {C.BOLD}── Resumen ──────────────────────────────────────────{C.RESET}")
    print(f"  Sin internet : {C.BOLD}{start[:5]}{C.RESET} → {C.BOLD}{end[:5]}{C.RESET}")
    print(f"  Días         : {days_labels}")
    print(f"  Afecta a     : {C.BOLD}TODOS{C.RESET} excepto lista blanca")
    if preserved_macs:
        print(f"  Lista blanca : {len(preserved_macs)} dispositivo(s) conservados")
    print(f"  {C.BOLD}─────────────────────────────────────────────────────{C.RESET}")

    confirm = input(f"\n  ¿Aplicar en el router? (s/n): ").strip().lower()
    if confirm != "s":
        print(f"\n  {C.DIM}Cancelado.{C.RESET}\n")
        return

    apply_all_rules(api, wan, start, end, days, preserved_macs)
    if preserved_macs:
        # Sincronizar el archivo con lo aplicado (nombres/fechas al día)
        save_whitelist(set(preserved_macs),
                       build_device_map(api, by="mac"), stored)

    print(f"\n  {C.ERR}🔴 Corte programado activo:{C.RESET}")
    print(f"     Sin internet : {C.BOLD}{start[:5]}{C.RESET} → {C.BOLD}{end[:5]}{C.RESET}  "
          f"│  {days_labels}")
    if not preserved_macs:
        print(f"\n  {C.WARN}⚠️  Lista blanca vacía — usa la opción 42 del menú{C.RESET}")
        print(f"  {C.WARN}   para agregar dispositivos que siempre tendrán internet.{C.RESET}")
    else:
        print(f"     Lista blanca  : {C.GREEN}{len(preserved_macs)} dispositivo(s) "
              f"siempre con internet{C.RESET}")
    print(f"\n  {C.DIM}La regla funciona aunque este PC esté apagado.{C.RESET}\n")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Corte de internet por horario con lista blanca de excepciones")
    parser.add_argument("--list",   action="store_true",
                        help="Ver estado actual (horario + lista blanca)")
    parser.add_argument("--allow",  action="store_true",
                        help="Gestionar lista blanca (dispositivos siempre con internet)")
    parser.add_argument("--remove", action="store_true",
                        help="Eliminar todo — sin cortes ni lista blanca")
    args = parser.parse_args()

    cfg = load_config()
    with MikroTikAPI(**cfg) as api:
        if args.list:
            list_rules(api)
        elif args.allow:
            interactive_allow(api)
        elif args.remove:
            n = remove_all_rules(api)
            if n:
                print(f"\n  {C.GREEN}✅ {n} regla(s) eliminada(s). "
                      f"Internet sin restricciones.{C.RESET}")
            else:
                print(f"\n  {C.GREEN}No había reglas de corte.{C.RESET}")
            stored = load_whitelist()
            if stored:
                print(f"  {C.DIM}💾 La lista blanca ({len(stored)} "
                      f"dispositivo(s)) sigue guardada en "
                      f"config/whitelist.json y se reaplicará al "
                      f"programar un nuevo corte.{C.RESET}\n")
            else:
                print()
        else:
            interactive_mode(api)


if __name__ == "__main__":
    run_script(main)
