"""
core/horario.py — Corte de internet por horario con lista blanca
================================================================

Lógica extraída de horario_internet.py: detección de WAN, lectura y
creación de reglas etiquetadas (HORARIO-INTERNET / HORARIO-PERMITIDO /
HORARIO-INTENTOS), parsing de horarios de RouterOS v6/v7, lista blanca
persistente en config/whitelist.json y los dispositivos afectados por el
corte. Solo gestiona reglas propias.
"""

import re
from datetime import date

from lib import (load_json_config, save_json_config, get_router_datetime,
                 parse_router_date, get_lan_prefix, build_device_map)

# Tags para identificar nuestras reglas
DROP_TAG  = "HORARIO-INTERNET"       # la regla DROP global
ALLOW_TAG = "HORARIO-PERMITIDO"      # reglas ACCEPT por MAC (lista blanca)
TRY_TAG   = "HORARIO-INTENTOS"       # anota quién intenta salir (justo antes del DROP)

# Address-list donde la regla TRY_TAG anota la IP de cada dispositivo que
# intenta salir durante el corte; la entrada caduca sola.
TRY_LIST = "HORARIO-INTENTOS"
TRY_TIMEOUT_S = 600                  # 10 min

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
    RouterOS v7 ya no tiene gateway-status: la interfaz viene en
    immediate-gw ('172.10.7.1%ether1', o solo 'pppoe-out1').
    """
    iface = ruta.get("interface", "")
    if iface:
        return iface
    m = re.search(r"via\s+(\S+)", ruta.get("gateway-status", ""))
    if m:
        return m.group(1)
    return ruta.get("immediate-gw", "").rpartition("%")[2]


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
    """Elimina todas las reglas (DROP + ACCEPT + INTENTOS) de este gestor
    y las entradas de su address-list. Retorna cuántas reglas quitó.

    NO borra config/whitelist.json: la lista blanca persiste y se
    reaplica automáticamente al programar un nuevo corte.
    """
    to_remove = [
        r[".id"] for r in api.command("/ip/firewall/filter/print")
        if r.get("comment", "") in (DROP_TAG, TRY_TAG)
        or r.get("comment", "").startswith(ALLOW_TAG)
    ]
    for rid in to_remove:
        api.command("/ip/firewall/filter/remove", params=[f"=.id={rid}"])
    for e in api.command("/ip/firewall/address-list/print",
                         queries=[f"?list={TRY_LIST}"]):
        api.command("/ip/firewall/address-list/remove",
                    params=[f"=.id={e['.id']}"])
    return len(to_remove)


def apply_all_rules(api, wan: str, start: str, end: str,
                    days: list, allowed_macs: list):
    """
    Crea primero las ACCEPT (lista blanca), luego la de INTENTOS y al
    final la DROP global. El orden es crítico: RouterOS procesa top-down,
    primera coincidencia gana — la de INTENTOS no corta (anota la IP en
    TRY_LIST y deja seguir el paquete hasta el DROP), así que solo ve a
    los que no están en la lista blanca y durante el mismo horario.
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

    # 2. Registro de intentos (mismo horario, no corta)
    api.command("/ip/firewall/filter/add", params=[
        "=chain=forward",
        f"=out-interface={wan}",
        "=action=add-src-to-address-list",
        f"=address-list={TRY_LIST}",
        f"=address-list-timeout={TRY_TIMEOUT_S}s",
        f"=time={time_val}",
        f"=comment={TRY_TAG}",
    ])

    # 3. DROP global con horario (para todos los demás)
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
# Afectados por el corte: en la red, fuera de la lista blanca
# ---------------------------------------------------------------------------

# Estados ARP que indican que el equipo respondió hace poco
_ARP_VIVO = {"reachable", "stale", "delay", "probe", "permanent"}
_UNIDADES_S = {"w": 604800, "d": 86400, "h": 3600, "m": 60, "s": 1}


def duracion_a_segundos(valor: str) -> int | None:
    """Duración de RouterOS → segundos: '9m41s', '1h2m', '41s870ms'
    (v7 puede añadir milisegundos, se ignoran) o '00:09:41'.
    None si no se reconoce."""
    valor = (valor or "").strip()
    if not valor:
        return None
    if ":" in valor:
        try:
            partes = [int(x) for x in valor.split(":")]
        except ValueError:
            return None
        while len(partes) < 3:
            partes.insert(0, 0)
        h, m, s = partes[-3:]
        return h * 3600 + m * 60 + s
    tokens = re.findall(r"(\d+)(ms|us|ns|[wdhms])", valor)
    if not tokens or "".join(n + u for n, u in tokens) != valor:
        return None
    return sum(int(n) * _UNIDADES_S.get(u, 0) for n, u in tokens)


def get_try_rule(api) -> dict | None:
    """Regla de registro de intentos, o None (cortes creados antes de
    que existiera no la tienen hasta reprogramarlos)."""
    for r in api.command("/ip/firewall/filter/print"):
        if r.get("comment", "") == TRY_TAG:
            return r
    return None


def intentos_recientes(api) -> dict:
    """IP → segundos desde su último intento de salir (address-list)."""
    hace = {}
    for e in api.command("/ip/firewall/address-list/print",
                         queries=[f"?list={TRY_LIST}"]):
        restante = duracion_a_segundos(e.get("timeout", ""))
        if e.get("address") and restante is not None:
            hace[e["address"]] = max(0, TRY_TIMEOUT_S - restante)
    return hace


def dispositivos_afectados(api, whitelist_macs) -> list:
    """Dispositivos conectados ahora que NO están en la lista blanca.

    Durante el corte son los que tienen red pero no internet. "Conectado"
    = lease DHCP bound o entrada ARP viva. Cada uno lleva
    intento_hace_s (segundos desde su último intento de salir, o None si
    no intentó en los últimos 10 min / no hay regla de registro).
    Orden: los que intentan salir primero (más reciente arriba), luego
    por IP.
    """
    lan = get_lan_prefix(api)
    wl = {m.upper() for m in whitelist_macs}
    devices = build_device_map(api, by="ip")
    bound = {l.get("address") for l in api.command("/ip/dhcp-server/lease/print")
             if l.get("status") == "bound"}
    arp_vivo = {a.get("address") for a in api.command("/ip/arp/print")
                if a.get("status", "") in _ARP_VIVO
                and a.get("address", "").startswith(lan)}
    intentos = intentos_recientes(api)

    afectados = []
    for ip, d in devices.items():
        if not d["mac"] or d["mac"].upper() in wl:
            continue
        if ip not in bound and ip not in arp_vivo:
            continue
        afectados.append({
            "ip": ip,
            "mac": d["mac"].upper(),
            "nombre": d["name"],
            "nombre_detectado": d["detected_name"],
            "alias": d["alias"],
            "intento_hace_s": intentos.get(ip),
        })

    def orden(a):
        ip_num = [int(x) for x in a["ip"].split(".") if x.isdigit()]
        hace = a["intento_hace_s"]
        return (hace is None, hace if hace is not None else 0, ip_num)

    return sorted(afectados, key=orden)


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
        # El nombre detectado, no el alias: el alias vive en alias.json y
        # quitarlo no debe dejar su texto pegado aquí.
        dev = devices.get(mac, {})
        nombre = (dev.get("detected_name") or dev.get("name")
                  or prev.get("nombre", ""))
        items.append({
            "mac": mac,
            "nombre": nombre,
            "agregado": prev.get("agregado", date.today().isoformat()),
        })
    save_json_config(WHITELIST_CONFIG, {"dispositivos": items})
