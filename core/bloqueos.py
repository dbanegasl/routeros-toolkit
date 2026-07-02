"""
core/bloqueos.py — Bloqueo/desbloqueo de IPs en el firewall
===========================================================

Lógica extraída de mant_bloqueo.py. Solo gestiona reglas propias
(comentario BLOQUEADO-POR-MENU-*); nunca toca reglas ajenas.
"""

COMMENT_TAG = "BLOQUEADO-POR-MENU"


def reglas_bloqueo(api) -> list:
    """Reglas de bloqueo creadas por este toolkit (comentario propio)."""
    rules = api.command("/ip/firewall/filter/print")
    return [r for r in rules
            if r.get("comment", "").startswith(COMMENT_TAG)]


def buscar_bloqueo(api, ip: str) -> list:
    """Reglas de bloqueo existentes para una IP concreta."""
    return [r for r in reglas_bloqueo(api) if r.get("src-address") == ip]


def bloquear_ip(api, ip: str):
    """Agrega la regla DROP al inicio de la cadena forward para esta IP.

    No verifica duplicados: la capa de presentación decide (buscar_bloqueo).
    """
    api.command("/ip/firewall/filter/add", params=[
        "=chain=forward",
        f"=src-address={ip}",
        "=action=drop",
        f"=comment={COMMENT_TAG}-{ip}",
        "=place-before=0",       # insertar al inicio
    ])


def desbloquear_ip(api, ip: str) -> int:
    """Elimina las reglas de bloqueo de esta IP. Retorna cuántas quitó."""
    found = buscar_bloqueo(api, ip)
    for r in found:
        api.command("/ip/firewall/filter/remove",
                    params=[f"=.id={r['.id']}"])
    return len(found)
