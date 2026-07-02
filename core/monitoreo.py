"""
core/monitoreo.py — Consumo por dispositivo, interfaces, sistema y log
======================================================================

Lógica extraída de mon_consumo.py, mon_vivo.py, info_interfaces.py,
info_sistema.py y mant_log.py. Las funciones retornan datos; no imprimen.
"""

from collections import defaultdict


# ---------------------------------------------------------------------------
# Consumo por dispositivo (connection tracking) — mon_consumo / mon_vivo
# ---------------------------------------------------------------------------

def snapshot_consumo(api, lan: str) -> tuple:
    """Lee el connection tracking y acumula métricas por IP LAN de origen.

    Retorna (data, total_conns) donde data es:
        ip → {dl_rate, ul_rate, dl_total, ul_total, conns}
    Los totales suman los bytes FastTrack (orig/repl-fasttrack-bytes),
    imprescindible porque FastTrack se salta los contadores normales.
    """
    conns = api.command("/ip/firewall/connection/print")
    data = defaultdict(lambda: dict(dl_rate=0, ul_rate=0,
                                    dl_total=0, ul_total=0, conns=0))
    for c in conns:
        src = c.get("src-address", "").split(":")[0]
        if not src.startswith(lan):
            continue
        d = data[src]
        d["dl_rate"]  += int(c.get("repl-rate", 0))
        d["ul_rate"]  += int(c.get("orig-rate", 0))
        d["dl_total"] += (int(c.get("repl-bytes", 0)) +
                          int(c.get("repl-fasttrack-bytes", 0)))
        d["ul_total"] += (int(c.get("orig-bytes", 0)) +
                          int(c.get("orig-fasttrack-bytes", 0)))
        d["conns"]    += 1
    return dict(data), len(conns)


def ordenar_consumo(data: dict, por: str = "rate") -> list:
    """Ordena el snapshot de consumo de mayor a menor.

    por="rate"  → velocidad actual (dl_rate + ul_rate)
    por="total" → acumulado de sesión (dl_total + ul_total)
    Retorna lista de tuplas (ip, métricas).
    """
    if por == "total":
        clave = lambda kv: kv[1]["dl_total"] + kv[1]["ul_total"]
    else:
        clave = lambda kv: kv[1]["dl_rate"] + kv[1]["ul_rate"]
    return sorted(data.items(), key=clave, reverse=True)


# ---------------------------------------------------------------------------
# Interfaces — info_interfaces
# ---------------------------------------------------------------------------

def get_iface_stats(api) -> dict:
    """Retorna dict nombre → stats del comando /interface/print stats."""
    ifaces = api.command("/interface/print", params=["=stats="])
    return {i["name"]: i for i in ifaces}


def calcular_delta(sample1: dict, sample2: dict) -> dict:
    """Delta de bytes TX/RX entre dos muestras de get_iface_stats."""
    delta = {}
    for name, s2 in sample2.items():
        if name in sample1:
            s1 = sample1[name]
            delta[name] = {
                "tx-byte": max(0, int(s2.get("tx-byte", 0)) -
                                  int(s1.get("tx-byte", 0))),
                "rx-byte": max(0, int(s2.get("rx-byte", 0)) -
                                  int(s1.get("rx-byte", 0))),
            }
    return delta


def interfaz_mas_activa(delta: dict):
    """(nombre, delta) de la interfaz con más tráfico, o None si delta vacío."""
    if not delta:
        return None
    return max(delta.items(),
               key=lambda kv: kv[1]["tx-byte"] + kv[1]["rx-byte"])


# ---------------------------------------------------------------------------
# Sistema — info_sistema
# ---------------------------------------------------------------------------

def resumen_sistema(api) -> dict:
    """Estado del router (hardware, recursos, interfaces, dispositivos).

    Retorna un dict con los campos ya casteados, o None si el router
    no reportó /system/resource.
    """
    res = api.command("/system/resource/print")
    identity = api.command("/system/identity/print")
    interfaces = api.command("/interface/print")
    leases = api.command("/ip/dhcp-server/lease/print")

    if not res:
        return None

    r = res[0]
    total_mem = int(r.get("total-memory", 1))
    free_mem  = int(r.get("free-memory", 0))
    total_hdd = int(r.get("total-hdd-space", 1))
    free_hdd  = int(r.get("free-hdd-space", 0))

    return {
        "name":         identity[0].get("name", "MikroTik") if identity else "MikroTik",
        "uptime":       r.get("uptime", "?"),
        "version":      r.get("version", "?"),
        "board":        r.get("board-name", "?"),
        "arch":         r.get("architecture-name", "?"),
        "cpu_count":    r.get("cpu-count", "1"),
        "cpu_load":     int(r.get("cpu-load", 0)),
        "free_mem":     free_mem,
        "total_mem":    total_mem,
        "used_mem":     total_mem - free_mem,
        "free_hdd":     free_hdd,
        "total_hdd":    total_hdd,
        "used_hdd":     total_hdd - free_hdd,
        "bad_blocks":   r.get("bad-blocks", "0"),
        "ifaces_up":    sum(1 for i in interfaces if i.get("running") == "true"),
        "ifaces_total": len(interfaces),
        "devices_conn": sum(1 for l in leases if l.get("status") == "bound"),
    }


# ---------------------------------------------------------------------------
# Log — mant_log
# ---------------------------------------------------------------------------

def obtener_log(api, lineas: int = 50) -> list:
    """Últimas N entradas del syslog de RouterOS."""
    entries = api.command("/log/print")
    return entries[-lineas:]


def nivel_log(topics: str) -> str:
    """Nivel de severidad ('critical'…'debug') según los topics de la entrada."""
    for lvl in ("critical", "error", "warning", "debug"):
        if lvl in topics:
            return lvl
    return "info"
