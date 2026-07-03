"""
core/horario.py — Corte de internet por horario con lista blanca
================================================================

Lógica extraída de horario_internet.py: detección de WAN, lectura y
creación de reglas etiquetadas (HORARIO-INTERNET / HORARIO-PERMITIDO),
parsing de horarios de RouterOS v6 y lista blanca persistente en
config/whitelist.json. Solo gestiona reglas propias.
"""

import re
from datetime import date

from lib import (load_json_config, save_json_config, get_router_datetime,
                 parse_router_date)

# Tags para identificar nuestras reglas
DROP_TAG  = "HORARIO-INTERNET"       # la regla DROP global
ALLOW_TAG = "HORARIO-PERMITIDO"      # reglas ACCEPT por MAC (lista blanca)

# Archivo de persistencia: la lista blanca sobrevive a --remove,
# así no hay que rearmarla a mano al reprogramar un corte.
WHITELIST_CONFIG = "whitelist"       # → config/whitelist.json

DAYS_MAP = {
    "1": "mon", "2": "tue", "3": "wed",
    "4": "thu", "5": "fri", "6": "sat", "7": "sun",
}
DAYS_LABEL = {
    "mon": "Lunes", "tue": "Martes", "wed": "Miércoles",
    "thu": "Jueves", "fri": "Viernes", "sat": "Sábado", "sun": "Domingo",
}
ALL_DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


# ---------------------------------------------------------------------------
# Detección de WAN
# ---------------------------------------------------------------------------

def _iface_de_ruta(ruta: dict) -> str:
    """Interfaz de salida de una ruta.

    RouterOS v6 no siempre expone 'interface' en /ip/route/print: cuando
    el gateway es una IP, la interfaz real viene dentro de
    gateway-status ('172.10.7.1 reachable via  ether1').
    """
    iface = ruta.get("interface", "")
    if iface:
        return iface
    m = re.search(r"via\s+(\S+)", ruta.get("gateway-status", ""))
    return m.group(1) if m else ""


def get_wan_interface(api) -> str:
    routes = api.command("/ip/route/print")
    default = [r for r in routes if r.get("dst-address") == "0.0.0.0/0"]
    for r in default:
        if r.get("active") == "true":
            iface = _iface_de_ruta(r)
            if iface:
                return iface
    for r in default:
        iface = _iface_de_ruta(r)
        if iface:
            return iface
    return ""


# ---------------------------------------------------------------------------
# Lectura de reglas existentes
# ---------------------------------------------------------------------------

def get_drop_rule(api) -> dict | None:
    """Retorna la regla DROP global o None."""
    for r in api.command("/ip/firewall/filter/print"):
        if r.get("comment", "") == DROP_TAG:
            return r
    return None


def get_allow_rules(api) -> list:
    """Retorna las reglas ACCEPT de la lista blanca."""
    return [r for r in api.command("/ip/firewall/filter/print")
            if r.get("comment", "").startswith(ALLOW_TAG)]


def normalize_ros_time(token: str) -> str:
    """Normaliza un tiempo de RouterOS a 'HH:MM:SS'.

    RouterOS v6 devuelve el campo time en formato de duración
    ('1h1m', '6h', '45m30s'); también puede venir como '01:01:00'.
    Si el valor no se reconoce, se retorna tal cual.
    """
    token = token.strip()
    if ":" in token:
        parts = token.split(":")
        try:
            h, m = int(parts[0]), int(parts[1])
            s = int(parts[2]) if len(parts) > 2 else 0
            return f"{h:02d}:{m:02d}:{s:02d}"
        except ValueError:
            return token
    unidades = re.findall(r"(\d+)([hms])", token)
    if not unidades:
        return token
    valores = {"h": 0, "m": 0, "s": 0}
    for num, unidad in unidades:
        valores[unidad] = int(num)
    return f"{valores['h']:02d}:{valores['m']:02d}:{valores['s']:02d}"


def parse_drop_time(rule: dict) -> tuple[str, str, list]:
    """Extrae (start, end, days) del campo time de la regla DROP.

    start/end quedan normalizados a 'HH:MM:SS' aunque RouterOS los
    devuelva en formato de duración ('1h1m-6h1m,mon,tue,...').
    """
    time_val = rule.get("time", "")
    start, end, days = "", "", list(ALL_DAYS)
    if time_val:
        parts = time_val.split(",")
        if parts and "-" in parts[0]:
            start, _, end = parts[0].partition("-")
            start, end = normalize_ros_time(start), normalize_ros_time(end)
        days = [p for p in parts[1:] if p in DAYS_LABEL] or ALL_DAYS
    return start, end, days


# ---------------------------------------------------------------------------
# ¿El corte está aplicándose AHORA? (según el reloj del router)
# ---------------------------------------------------------------------------

def _a_minutos(hhmm: str) -> int:
    h, m = hhmm.split(":")[:2]
    return int(h) * 60 + int(m)


def corte_en_curso(start: str, end: str, days: list,
                   now_min: int, today: str) -> bool:
    """True si el corte está bloqueando internet en este momento.

    Args:
        start/end — 'HH:MM' o 'HH:MM:SS'
        days      — días del corte ('mon'..'sun')
        now_min   — minuto actual del día (0–1439)
        today     — día actual ('mon'..'sun')

    Maneja rangos que cruzan medianoche (ej: 22:00 → 06:00): la madrugada
    cuenta como continuación del día en que empezó el corte.
    """
    if not start or not end:
        return False
    ini, fin = _a_minutos(start), _a_minutos(end)
    if ini == fin:
        return False
    if ini < fin:
        return today in days and ini <= now_min < fin
    # Cruza medianoche: [ini → 24:00) del día listado ∪ [00:00 → fin) del siguiente
    ayer = ALL_DAYS[(ALL_DAYS.index(today) - 1) % 7]
    return ((today in days and now_min >= ini)
            or (ayer in days and now_min < fin))


def get_router_now(api) -> tuple[int, str, str] | None:
    """Lee el reloj del router: (minuto del día, día 'mon'..'sun', 'HH:MM').

    Retorna None si no se puede interpretar (se puede caer al reloj local).
    """
    ahora = get_router_datetime(api)
    if ahora is None:
        return None
    return (ahora.hour * 60 + ahora.minute,
            ALL_DAYS[ahora.weekday()],
            f"{ahora.hour:02d}:{ahora.minute:02d}")


# ---------------------------------------------------------------------------
# Crear / eliminar reglas en el router
# ---------------------------------------------------------------------------

def remove_all_rules(api) -> int:
    """Elimina todas las reglas (DROP + ACCEPT) de este gestor.

    NO borra config/whitelist.json: la lista blanca persiste y se
    reaplica automáticamente al programar un nuevo corte.
    """
    to_remove = [
        r[".id"] for r in api.command("/ip/firewall/filter/print")
        if r.get("comment", "") == DROP_TAG
        or r.get("comment", "").startswith(ALLOW_TAG)
    ]
    for rid in to_remove:
        api.command("/ip/firewall/filter/remove", params=[f"=.id={rid}"])
    return len(to_remove)


def apply_all_rules(api, wan: str, start: str, end: str,
                    days: list, allowed_macs: list):
    """
    Crea primero las ACCEPT (lista blanca) y luego la DROP global.
    El orden es crítico: RouterOS procesa top-down, primera coincidencia gana.
    """
    days_str = ",".join(days)
    time_val = f"{start}-{end},{days_str}"

    # 1. ACCEPT por MAC (sin restricción de tiempo → siempre pasan)
    for mac in allowed_macs:
        api.command("/ip/firewall/filter/add", params=[
            "=chain=forward",
            f"=out-interface={wan}",
            f"=src-mac-address={mac.upper()}",
            "=action=accept",
            f"=comment={ALLOW_TAG}-{mac.upper()}",
        ])

    # 2. DROP global con horario (para todos los demás)
    api.command("/ip/firewall/filter/add", params=[
        "=chain=forward",
        f"=out-interface={wan}",
        "=action=drop",
        f"=time={time_val}",
        f"=comment={DROP_TAG}",
    ])


def aplicar_solo_whitelist(api, wan: str, macs) -> None:
    """Reemplaza las reglas ACCEPT sin crear la DROP (aún sin horario).

    Se usa cuando se arma la lista blanca antes de programar el corte:
    las ACCEPT quedan en el router y el DROP se añadirá al configurar
    el horario.
    """
    for r in get_allow_rules(api):
        api.command("/ip/firewall/filter/remove", params=[f"=.id={r['.id']}"])
    for mac in macs:
        params = [
            "=chain=forward",
            f"=src-mac-address={mac.upper()}",
            "=action=accept",
            f"=comment={ALLOW_TAG}-{mac.upper()}",
        ]
        if wan:
            params.insert(1, f"=out-interface={wan}")
        api.command("/ip/firewall/filter/add", params=params)


# ---------------------------------------------------------------------------
# Lista blanca persistente (config/whitelist.json)
# ---------------------------------------------------------------------------

def load_whitelist() -> dict:
    """MAC_upper → {mac, nombre, agregado} desde config/whitelist.json."""
    data = load_json_config(WHITELIST_CONFIG, default={"dispositivos": []})
    return {d["mac"].upper(): d
            for d in data.get("dispositivos", []) if d.get("mac")}


def save_whitelist(macs: set, devices: dict, previous: dict):
    """Persiste la lista blanca conservando nombre/fecha de entradas previas.

    Args:
        macs     — set de MACs (upper) que forman la nueva lista blanca
        devices  — mapa de dispositivos de la red (para resolver nombres)
        previous — whitelist anterior (para no perder nombre/fecha si el
                   dispositivo no está conectado ahora)
    """
    items = []
    for mac in sorted(macs):
        prev = previous.get(mac, {})
        nombre = (devices.get(mac, {}).get("name")
                  or prev.get("nombre", ""))
        items.append({
            "mac": mac,
            "nombre": nombre,
            "agregado": prev.get("agregado", date.today().isoformat()),
        })
    save_json_config(WHITELIST_CONFIG, {"dispositivos": items})
