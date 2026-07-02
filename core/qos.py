"""
core/qos.py — Plan QoS: configuración, builders y operaciones en el router
==========================================================================

Lógica extraída de qos_desplegar.py, qos_reset.py y qos_diagnostico.py:

- Configuración (config/qos.json con defaults del plan original de Kevin).
- build_mangle_rules / build_queue_tree: funciones puras que generan el
  plan completo; con los defaults producen EXACTAMENTE el plan original
  (100 Mbps) — están cubiertas por tests que lo pinean.
- Operaciones sobre el router (aplicar/eliminar reglas y colas, FastTrack).
  El reset es SELECTIVO: solo toca elementos etiquetados del QoS
  (comentarios 'QoS *', colas 'QoS_*/DL-*/UL-*').
"""

from lib import load_json_config


# ---------------------------------------------------------------------------
# Configuración (config/qos.json)
# ---------------------------------------------------------------------------

QOS_DEFAULTS = {
    "dispositivo_prioritario": {
        "nombre": "Kevin KUTOGG",
        "mac": "F0:2F:74:CB:97:3F",
        "ip": "192.168.5.22",
    },
    "interfaz_wan": "ether1",
    "bridge_lan": "bridge1",
    "descarga_total_mbps": 100,
    "subida_total_mbps": 100,
    "umbral_bulk_mb": 30,
}

# Prefijos que identifican los elementos creados por el despliegue QoS
QOS_COMMENT_PREFIX = "QoS"
QOS_QUEUE_PREFIXES = ("QoS_", "DL-", "UL-")


def load_qos_config() -> dict:
    """Lee config/qos.json completando faltantes con los defaults."""
    qos = load_json_config("qos", default=QOS_DEFAULTS)
    # Merge profundo del sub-dict del dispositivo (claves parciales)
    device = dict(QOS_DEFAULTS["dispositivo_prioritario"])
    device.update(qos.get("dispositivo_prioritario", {}))
    qos["dispositivo_prioritario"] = device
    return qos


def _scale_limit(value: str, factor: float) -> str:
    """Escala un límite RouterOS ('85M', '512k') por un factor.

    Con factor 1.0 retorna el valor intacto, así el plan por defecto
    (100 Mbps) genera exactamente las mismas reglas de siempre.
    """
    if factor == 1.0:
        return value
    unit = value[-1]
    n = max(1, int(int(value[:-1]) * factor))
    return f"{n}{unit}"


# ---------------------------------------------------------------------------
# Builders del plan (funciones puras, cubiertas por tests)
# ---------------------------------------------------------------------------

def build_mangle_rules(qos: dict) -> list:
    """Construye la lista de reglas Mangle según la configuración.

    Función pura (sin API): con los defaults genera exactamente el plan
    original de Kevin. Testeable sin router.
    """
    device = qos["dispositivo_prioritario"]
    ip = device["ip"]
    alias = device["nombre"].split()[0]          # "Kevin KUTOGG" → "Kevin"
    umbral_mb = int(qos.get("umbral_bulk_mb", 30))
    umbral_bytes = umbral_mb * 1_000_000

    return [
        # ============================================================
        # BLOQUE 1: CRÍTICO — DNS e ICMP
        # ============================================================
        {
            'chain': 'prerouting',
            'action': 'mark-connection',
            'protocol': 'udp',
            'dst-port': '53',
            'new-connection-mark': 'conn_critico',
            'passthrough': 'yes',
            'comment': 'QoS P1 - DNS UDP'
        },
        {
            'chain': 'prerouting',
            'action': 'mark-connection',
            'protocol': 'tcp',
            'dst-port': '53',
            'new-connection-mark': 'conn_critico',
            'passthrough': 'yes',
            'comment': 'QoS P1 - DNS TCP (DNSSEC)'
        },
        {
            'chain': 'prerouting',
            'action': 'mark-connection',
            'protocol': 'icmp',
            'new-connection-mark': 'conn_critico',
            'passthrough': 'yes',
            'comment': 'QoS P1 - ICMP Ping'
        },
        {
            'chain': 'prerouting',
            'action': 'mark-packet',
            'connection-mark': 'conn_critico',
            'new-packet-mark': 'pkt_critico',
            'passthrough': 'no',
            'comment': 'QoS P1 - Marcar paquetes criticos'
        },

        # ============================================================
        # BLOQUE 2: DISPOSITIVO PRIORITARIO — TODO su tráfico
        # ============================================================
        {
            'chain': 'prerouting',
            'action': 'mark-connection',
            'src-address': ip,
            'new-connection-mark': 'conn_kevin',
            'passthrough': 'yes',
            'comment': f'QoS P2 - {alias} origen (upload + gaming)'
        },
        {
            'chain': 'prerouting',
            'action': 'mark-connection',
            'dst-address': ip,
            'new-connection-mark': 'conn_kevin',
            'passthrough': 'yes',
            'comment': f'QoS P2 - {alias} destino (download + respuestas juegos)'
        },
        {
            'chain': 'prerouting',
            'action': 'mark-packet',
            'connection-mark': 'conn_kevin',
            'new-packet-mark': 'pkt_kevin',
            'passthrough': 'no',
            'comment': f'QoS P2 - Marcar paquetes {alias} (gaming + OBS + todo)'
        },

        # ============================================================
        # BLOQUE 3: DESCARGAS PESADAS (BULK)
        # ============================================================
        {
            'chain': 'forward',
            'action': 'mark-connection',
            'protocol': 'tcp',
            'connection-bytes': f'{umbral_bytes}-0',
            'connection-mark': '!conn_kevin',
            'new-connection-mark': 'conn_bulk',
            'passthrough': 'yes',
            'comment': f'QoS P8 - Cualquier TCP >{umbral_mb}MB excluye {alias}'
        },
        {
            'chain': 'forward',
            'action': 'mark-packet',
            'connection-mark': 'conn_bulk',
            'new-packet-mark': 'pkt_bulk',
            'passthrough': 'no',
            'comment': 'QoS P8 - Marcar paquetes bulk/descarga pesada'
        },

        # ============================================================
        # BLOQUE 4: TRABAJO — SSH, RDP, VPN, puertos dev
        # ============================================================
        {
            'chain': 'prerouting',
            'action': 'mark-connection',
            'protocol': 'tcp',
            'dst-port': '22,2222',
            'new-connection-mark': 'conn_trabajo',
            'passthrough': 'yes',
            'comment': 'QoS P3 - SSH'
        },
        {
            'chain': 'prerouting',
            'action': 'mark-connection',
            'protocol': 'tcp',
            'dst-port': '3389',
            'new-connection-mark': 'conn_trabajo',
            'passthrough': 'yes',
            'comment': 'QoS P3 - RDP'
        },
        {
            'chain': 'prerouting',
            'action': 'mark-connection',
            'protocol': 'tcp',
            'dst-port': '5900',
            'new-connection-mark': 'conn_trabajo',
            'passthrough': 'yes',
            'comment': 'QoS P3 - VNC'
        },
        {
            'chain': 'prerouting',
            'action': 'mark-connection',
            'protocol': 'udp',
            'dst-port': '51820',
            'new-connection-mark': 'conn_trabajo',
            'passthrough': 'yes',
            'comment': 'QoS P3 - WireGuard VPN'
        },
        {
            'chain': 'prerouting',
            'action': 'mark-connection',
            'protocol': 'udp',
            'dst-port': '1194,1195',
            'new-connection-mark': 'conn_trabajo',
            'passthrough': 'yes',
            'comment': 'QoS P3 - OpenVPN'
        },
        {
            'chain': 'prerouting',
            'action': 'mark-connection',
            'protocol': 'tcp',
            'dst-port': '3000,4000,5000,8000,8080,8443,9000',
            'new-connection-mark': 'conn_trabajo',
            'passthrough': 'yes',
            'comment': 'QoS P3 - Puertos dev (Docker, APIs locales, etc)'
        },
        {
            'chain': 'prerouting',
            'action': 'mark-connection',
            'protocol': 'tcp',
            'dst-port': '25,587,993,995',
            'new-connection-mark': 'conn_trabajo',
            'passthrough': 'yes',
            'comment': 'QoS P3 - Correo electronico'
        },
        {
            'chain': 'prerouting',
            'action': 'mark-packet',
            'connection-mark': 'conn_trabajo',
            'new-packet-mark': 'pkt_trabajo',
            'passthrough': 'no',
            'comment': 'QoS P3 - Marcar paquetes trabajo/dev'
        },

        # ============================================================
        # BLOQUE 5: STREAMING ADULTOS — HTTPS (port 443)
        # ============================================================
        {
            'chain': 'prerouting',
            'action': 'mark-connection',
            'protocol': 'tcp',
            'dst-port': '443',
            'connection-mark': '!conn_kevin',
            'new-connection-mark': 'conn_streaming',
            'passthrough': 'yes',
            'comment': 'QoS P5 - HTTPS streaming adultos (Netflix/HBO)'
        },
        {
            'chain': 'prerouting',
            'action': 'mark-packet',
            'connection-mark': 'conn_streaming',
            'new-packet-mark': 'pkt_streaming',
            'passthrough': 'no',
            'comment': 'QoS P5 - Marcar paquetes streaming adultos'
        },

        # ============================================================
        # BLOQUE 6: WEB GENERAL — HTTP (port 80)
        # ============================================================
        {
            'chain': 'prerouting',
            'action': 'mark-connection',
            'protocol': 'tcp',
            'dst-port': '80',
            'connection-mark': '!conn_kevin',
            'new-connection-mark': 'conn_web',
            'passthrough': 'yes',
            'comment': 'QoS P6 - HTTP general'
        },
        {
            'chain': 'prerouting',
            'action': 'mark-packet',
            'connection-mark': 'conn_web',
            'new-packet-mark': 'pkt_web',
            'passthrough': 'no',
            'comment': 'QoS P6 - Marcar paquetes web general'
        },

        # ============================================================
        # BLOQUE 7: FALLBACK — Todo lo que no encajó
        # ============================================================
        {
            'chain': 'prerouting',
            'action': 'mark-connection',
            'connection-mark': 'no-mark',
            'new-connection-mark': 'conn_resto',
            'passthrough': 'yes',
            'comment': 'QoS P7 - Fallback todo lo demas'
        },
        {
            'chain': 'prerouting',
            'action': 'mark-packet',
            'connection-mark': 'conn_resto',
            'new-packet-mark': 'pkt_resto',
            'passthrough': 'no',
            'comment': 'QoS P7 - Marcar paquetes sin clasificar'
        },
    ]


def build_queue_tree(qos: dict) -> list:
    """Construye la lista de colas Queue Tree según la configuración.

    Función pura (sin API). Los límites del plan asumen 100 Mbps; si la
    config define otro total, todos los límites se escalan en proporción.
    """
    device = qos["dispositivo_prioritario"]
    nombre = device["nombre"]
    alias = nombre.split()[0]
    umbral_mb = int(qos.get("umbral_bulk_mb", 30))

    queues = [
        # ── COLAS RAÍZ ──
        {
            'name': 'QoS_Download',
            'parent': qos["bridge_lan"],
            'max-limit': '85M',
            'comment': 'Cola raiz download - trafico hacia LAN'
        },
        {
            'name': 'QoS_Upload',
            'parent': qos["interfaz_wan"],
            'max-limit': '85M',
            'comment': 'Cola raiz upload - trafico saliente hacia internet'
        },

        # ── SUB-COLAS DOWNLOAD ──
        {
            'name': 'DL-1-Critico',
            'parent': 'QoS_Download',
            'packet-mark': 'pkt_critico',
            'priority': '1',
            'limit-at': '3M',
            'max-limit': '85M',
            'queue': 'default',
            'comment': 'DNS + ICMP - pasan siempre'
        },
        {
            'name': 'DL-2-Kevin',
            'parent': 'QoS_Download',
            'packet-mark': 'pkt_kevin',
            'priority': '2',
            'limit-at': '30M',
            'max-limit': '85M',
            'queue': 'default',
            'comment': f'{nombre} - gaming y stream garantizados'
        },
        {
            'name': 'DL-3-Trabajo',
            'parent': 'QoS_Download',
            'packet-mark': 'pkt_trabajo',
            'priority': '3',
            'limit-at': '10M',
            'max-limit': '70M',
            'queue': 'default',
            'comment': 'Daniel - SSH VPN dev trabajo'
        },
        {
            'name': 'DL-5-Streaming',
            'parent': 'QoS_Download',
            'packet-mark': 'pkt_streaming',
            'priority': '5',
            'limit-at': '8M',
            'max-limit': '55M',
            'queue': 'default',
            'comment': 'Netflix HBO YouTube adultos'
        },
        {
            'name': 'DL-6-Web',
            'parent': 'QoS_Download',
            'packet-mark': 'pkt_web',
            'priority': '6',
            'limit-at': '5M',
            'max-limit': '60M',
            'queue': 'default',
            'comment': 'HTTP navegacion general'
        },
        {
            'name': 'DL-7-Resto',
            'parent': 'QoS_Download',
            'packet-mark': 'pkt_resto',
            'priority': '7',
            'limit-at': '3M',
            'max-limit': '45M',
            'queue': 'default',
            'comment': 'Trafico sin clasificar'
        },
        {
            'name': 'DL-8-Bulk',
            'parent': 'QoS_Download',
            'packet-mark': 'pkt_bulk',
            'priority': '8',
            'limit-at': '2M',
            'max-limit': '25M',
            'queue': 'default',
            'comment': f'Descargas pesadas >{umbral_mb}MB - cede ante {alias} automaticamente'
        },

        # ── SUB-COLAS UPLOAD ──
        {
            'name': 'UL-1-Critico',
            'parent': 'QoS_Upload',
            'packet-mark': 'pkt_critico',
            'priority': '1',
            'limit-at': '2M',
            'max-limit': '85M',
            'queue': 'default',
            'comment': 'DNS + ICMP upload'
        },
        {
            'name': 'UL-2-Kevin',
            'parent': 'QoS_Upload',
            'packet-mark': 'pkt_kevin',
            'priority': '2',
            'limit-at': '30M',
            'max-limit': '85M',
            'queue': 'default',
            'comment': f'{alias} OBS upload - NUNCA se toca aunque la red este saturada'
        },
        {
            'name': 'UL-3-Trabajo',
            'parent': 'QoS_Upload',
            'packet-mark': 'pkt_trabajo',
            'priority': '3',
            'limit-at': '5M',
            'max-limit': '40M',
            'queue': 'default',
            'comment': 'SSH git push VPN upload trabajo'
        },
        {
            'name': 'UL-5-Streaming',
            'parent': 'QoS_Upload',
            'packet-mark': 'pkt_streaming',
            'priority': '5',
            'limit-at': '2M',
            'max-limit': '20M',
            'queue': 'default',
            'comment': 'ACKs video adultos'
        },
        {
            'name': 'UL-6-Web',
            'parent': 'QoS_Upload',
            'packet-mark': 'pkt_web',
            'priority': '6',
            'limit-at': '2M',
            'max-limit': '20M',
            'queue': 'default',
            'comment': 'HTTP upload general'
        },
        {
            'name': 'UL-7-Resto',
            'parent': 'QoS_Upload',
            'packet-mark': 'pkt_resto',
            'priority': '7',
            'limit-at': '1M',
            'max-limit': '10M',
            'queue': 'default',
            'comment': 'Upload trafico sin clasificar'
        },
        {
            'name': 'UL-8-Bulk',
            'parent': 'QoS_Upload',
            'packet-mark': 'pkt_bulk',
            'priority': '8',
            'limit-at': '512k',
            'max-limit': '3M',
            'queue': 'default',
            'comment': 'Upload bulk (backups, workshop uploads, etc)'
        },
    ]

    # Escalar límites si el ancho de banda configurado no es 100 Mbps
    factor_dl = float(qos.get("descarga_total_mbps", 100)) / 100
    factor_ul = float(qos.get("subida_total_mbps", 100)) / 100
    for q in queues:
        factor = factor_dl if q["name"].startswith(("QoS_Download", "DL-")) \
                 else factor_ul
        for key in ("limit-at", "max-limit"):
            if key in q:
                q[key] = _scale_limit(q[key], factor)

    return queues


def mangle_params(rule: dict) -> list:
    """Convierte un dict de regla Mangle a params '=clave=valor' para el API."""
    params = [f'=chain={rule["chain"]}', f'=action={rule["action"]}']
    for key, value in rule.items():
        if key not in ('chain', 'action'):
            params.append(f'={key}={value}')
    return params


# ---------------------------------------------------------------------------
# Operaciones de despliegue (mutaciones sobre el router)
# ---------------------------------------------------------------------------

def buscar_lease(api, mac: str) -> list:
    """Leases DHCP del dispositivo (por MAC)."""
    return api.command('/ip/dhcp-server/lease/print',
                       queries=[f'?mac-address={mac}'])


def fijar_ip_estatica(api, device: dict, lease_id: str = None):
    """Fija la IP del dispositivo prioritario: actualiza el lease si existe
    (lease_id) o crea uno nuevo por MAC."""
    comment = f"{device['nombre']} - IP fija garantizada"
    if lease_id:
        api.command('/ip/dhcp-server/lease/set',
                    params=[f'=.id={lease_id}',
                            f"=address={device['ip']}",
                            f'=comment={comment}'])
    else:
        api.command('/ip/dhcp-server/lease/add',
                    params=[f"=mac-address={device['mac']}",
                            f"=address={device['ip']}",
                            f'=comment={comment}'])


def buscar_fasttrack(api) -> list:
    """Reglas fasttrack-connection del firewall filter."""
    return api.command('/ip/firewall/filter/print',
                       queries=['?action=fasttrack-connection'])


def deshabilitar_fasttrack(api, rules: list = None) -> list:
    """Deshabilita las reglas FastTrack (necesario para que Mangle/colas
    vean el tráfico). Retorna las reglas que deshabilitó."""
    if rules is None:
        rules = buscar_fasttrack(api)
    disabled = []
    for rule in rules:
        rule_id = rule.get('.id', '')
        if not rule_id:
            continue
        api.command('/ip/firewall/filter/set',
                    params=[f'=.id={rule_id}', '=disabled=yes'])
        disabled.append(rule)
    return disabled


def rehabilitar_fasttrack(api, solo_deshabilitadas: bool = True) -> tuple:
    """Vuelve a habilitar FastTrack. Retorna (n_habilitadas, n_reglas).

    Con solo_deshabilitadas=True (reset selectivo) solo toca las que
    estaban en disabled=true; con False (rollback) fuerza disabled=no
    en todas.
    """
    ft = buscar_fasttrack(api)
    habilitadas = 0
    for rule in ft:
        rule_id = rule.get('.id', '')
        if not rule_id:
            continue
        if solo_deshabilitadas and rule.get('disabled') != 'true':
            continue
        api.command('/ip/firewall/filter/set',
                    params=[f'=.id={rule_id}', '=disabled=no'])
        habilitadas += 1
    return habilitadas, len(ft)


def eliminar_reglas_mangle(api, rules: list) -> int:
    """Elimina las reglas Mangle dadas (dicts con .id). Retorna cuántas."""
    n = 0
    for rule in rules:
        rule_id = rule.get('.id', '')
        if rule_id:
            api.command('/ip/firewall/mangle/remove',
                        params=[f'=.id={rule_id}'])
            n += 1
    return n


def eliminar_colas(api, queues: list) -> int:
    """Elimina las colas Queue Tree dadas, en orden inverso (primero las
    subcolas, luego las colas padre). Retorna cuántas."""
    n = 0
    for queue in reversed(queues):
        queue_id = queue.get('.id', '')
        if queue_id:
            api.command('/queue/tree/remove',
                        params=[f'=.id={queue_id}'])
            n += 1
    return n


def aplicar_reglas_mangle(api, rules: list) -> list:
    """Aplica las reglas Mangle. Retorna [(regla, error|None)] por regla."""
    resultados = []
    for rule in rules:
        try:
            api.command('/ip/firewall/mangle/add', params=mangle_params(rule))
            resultados.append((rule, None))
        except Exception as e:
            resultados.append((rule, e))
    return resultados


def crear_colas(api, queues: list) -> list:
    """Crea las colas Queue Tree. Retorna [(cola, error|None)] por cola."""
    resultados = []
    for queue in queues:
        params = [f'={key}={value}' for key, value in queue.items()]
        try:
            api.command('/queue/tree/add', params=params)
            resultados.append((queue, None))
        except Exception as e:
            resultados.append((queue, e))
    return resultados


# ---------------------------------------------------------------------------
# Reset selectivo (qos_reset) — solo elementos etiquetados del QoS
# ---------------------------------------------------------------------------

def filtrar_mangle_qos(rules: list) -> list:
    """Solo las reglas Mangle creadas por el QoS (comentario 'QoS *')."""
    return [m for m in rules
            if m.get('comment', '').startswith(QOS_COMMENT_PREFIX)]


def filtrar_colas_qos(queues: list) -> list:
    """Solo las colas creadas por el QoS ('QoS_*', 'DL-*', 'UL-*')."""
    return [t for t in queues
            if t.get('name', '').startswith(QOS_QUEUE_PREFIXES)]


# ---------------------------------------------------------------------------
# Diagnóstico (qos_diagnostico)
# ---------------------------------------------------------------------------

def agrupar_por_prioridad(mangle: list) -> dict:
    """Agrupa reglas Mangle por prioridad (P1..P8) sumando contadores.

    Retorna: prioridad → {bytes, packets, rules: [{comment, bytes, packets}]}
    """
    marks = {}
    for rule in mangle:
        comment = rule.get('comment', 'unknown')
        bytes_val = int(rule.get('bytes', 0))
        packets_val = int(rule.get('packets', 0))

        # Extraer marca de prioridad (P1, P2, etc)
        priority = "unknown"
        if "P1" in comment:
            priority = "P1_Critico"
        elif "P2" in comment:
            priority = "P2_Kevin"
        elif "P3" in comment:
            priority = "P3_Trabajo"
        elif "P5" in comment:
            priority = "P5_Streaming"
        elif "P6" in comment:
            priority = "P6_Web"
        elif "P7" in comment:
            priority = "P7_Resto"
        elif "P8" in comment:
            priority = "P8_Bulk"

        if priority not in marks:
            marks[priority] = {'bytes': 0, 'packets': 0, 'rules': []}
        marks[priority]['bytes'] += bytes_val
        marks[priority]['packets'] += packets_val
        marks[priority]['rules'].append({
            'comment': comment,
            'bytes': bytes_val,
            'packets': packets_val
        })
    return marks
