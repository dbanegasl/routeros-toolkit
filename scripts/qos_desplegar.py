#!/usr/bin/env python3
"""
Implementar Plan QoS MikroTik — hEX lite — RouterOS v6.49.19
=============================================================

Despliega automáticamente todas las reglas de Mangle y Queue Tree del plan
QoS completo para garantizar ping y stream del dispositivo prioritario sin
que las descargas pesadas de otros dispositivos lo afecten.

La configuración (dispositivo prioritario, interfaces, ancho de banda) se
lee de config/qos.json — ver config/qos.json.example. Sin ese archivo se
usan los valores por defecto del plan original (Kevin, 100 Mbps).

Uso:
    python3 scripts/qos_desplegar.py               # desplegar
    python3 scripts/qos_desplegar.py --dry-run     # mostrar sin aplicar
    python3 scripts/qos_desplegar.py --rollback    # revertir todo

Pasos ejecutados:
    0. Verificación previa (interfaces, FastTrack, IPs)
    1. Fijar IP estática del dispositivo prioritario por MAC
    2. Deshabilitar FastTrack
    3. Limpiar configuración QoS previa
    4. Aplicar reglas Mangle (marcado de tráfico)
    5. Crear árbol de colas Queue Tree
    6. Verificación final
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from lib import MikroTikAPI, load_config, print_header, load_json_config, run_script


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


def print_step(step_num: int, description: str):
    """Imprime el número y descripción de un paso."""
    print(f"\n→ PASO {step_num}: {description}")
    print("-" * 70)


def step_0_verify(api: MikroTikAPI, qos: dict):
    """Verificación previa: interfaces, FastTrack, IPs."""
    print_step(0, "Verificación previa")
    device = qos["dispositivo_prioritario"]

    print("\n📋 Interfaces disponibles:")
    interfaces = api.command('/interface/print')
    for iface in interfaces:
        print(f"  • {iface.get('name', 'N/A')} (running: {iface.get('running', 'N/A')})")

    print("\n🚀 Estado de FastTrack:")
    fasttrack = api.command('/ip/firewall/filter/print',
                            queries=['?action=fasttrack-connection'])
    if fasttrack:
        for rule in fasttrack:
            status = "❌ ACTIVO" if rule.get('disabled') == 'false' else "✓ Deshabilitado"
            print(f"  {status} — {rule.get('comment', 'Sin comentario')}")
    else:
        print("  ℹ️  No hay reglas FastTrack configuradas")

    print(f"\n👤 Buscando IP de {device['nombre']} (MAC: {device['mac']}):")
    leases = api.command('/ip/dhcp-server/lease/print',
                         queries=[f"?mac-address={device['mac']}"])
    if leases:
        for lease in leases:
            print(f"  ✓ {lease.get('address', 'N/A')} — {lease.get('host-name', 'N/A')}")
    else:
        print(f"  ⚠️  {device['nombre']} no está conectado o no tiene lease DHCP")

    return True


def step_1_static_ip(api: MikroTikAPI, qos: dict, dry_run: bool = False):
    """Asignar IP estática al dispositivo prioritario por MAC."""
    device = qos["dispositivo_prioritario"]
    print_step(1, f"Fijar IP estática de {device['nombre']} ({device['ip']})")

    comment = f"{device['nombre']} - IP fija garantizada"
    existing = api.command('/ip/dhcp-server/lease/print',
                           queries=[f"?mac-address={device['mac']}"])

    if dry_run:
        accion = "actualizaría" if existing else "crearía"
        print(f"  🔍 [dry-run] Se {accion} el lease: "
              f"MAC {device['mac']} → {device['ip']} ({comment})")
        return

    if existing:
        print(f"  ℹ️  Lease existente para {device['nombre']}. Actualizando...")
        lease_id = existing[0].get('.id', '')
        if lease_id:
            api.command('/ip/dhcp-server/lease/set',
                        params=[f'=.id={lease_id}',
                                f"=address={device['ip']}",
                                f'=comment={comment}'])
            print(f"  ✓ IP estática confirmada")
    else:
        print(f"  ℹ️  Creando nuevo lease para {device['nombre']}...")
        api.command('/ip/dhcp-server/lease/add',
                    params=[f"=mac-address={device['mac']}",
                            f"=address={device['ip']}",
                            f'=comment={comment}'])
        print(f"  ✓ IP estática creada")


def step_2_disable_fasttrack(api: MikroTikAPI, dry_run: bool = False):
    """Deshabilitar FastTrack."""
    print_step(2, "Deshabilitar FastTrack")

    fasttrack = api.command('/ip/firewall/filter/print',
                            queries=['?action=fasttrack-connection'])
    if fasttrack:
        for rule in fasttrack:
            rule_id = rule.get('.id', '')
            if not rule_id:
                continue
            if dry_run:
                print(f"  🔍 [dry-run] Se deshabilitaría FastTrack: "
                      f"{rule.get('comment', 'sin comentario')}")
                continue
            api.command('/ip/firewall/filter/set',
                        params=[f'=.id={rule_id}', '=disabled=yes'])
            print(f"  ✓ Regla FastTrack deshabilitada: {rule.get('comment', 'sin comentario')}")
    else:
        print(f"  ℹ️  No hay reglas FastTrack para deshabilitar")


def step_3_cleanup_qos(api: MikroTikAPI, dry_run: bool = False):
    """Limpiar configuración QoS previa."""
    print_step(3, "Limpiar configuración QoS previa")

    # Borrar todas las reglas Mangle
    mangle_rules = api.command('/ip/firewall/mangle/print')
    if mangle_rules:
        if dry_run:
            print(f"  🔍 [dry-run] Se eliminarían {len(mangle_rules)} reglas Mangle")
        else:
            print(f"  🗑️  Eliminando {len(mangle_rules)} reglas Mangle...")
            for rule in mangle_rules:
                rule_id = rule.get('.id', '')
                if rule_id:
                    api.command('/ip/firewall/mangle/remove',
                                params=[f'=.id={rule_id}'])
            print(f"  ✓ {len(mangle_rules)} reglas Mangle eliminadas")
    else:
        print(f"  ℹ️  No hay reglas Mangle previas")

    # Borrar todas las colas Queue Tree. Se eliminan en orden inverso para
    # quitar primero las subcolas y luego las colas padre.
    queues = api.command('/queue/tree/print')
    if queues:
        if dry_run:
            print(f"  🔍 [dry-run] Se eliminarían {len(queues)} colas Queue Tree")
        else:
            print(f"  🗑️  Eliminando {len(queues)} colas Queue Tree...")
            for queue in reversed(queues):
                queue_id = queue.get('.id', '')
                if queue_id:
                    api.command('/queue/tree/remove',
                                params=[f'=.id={queue_id}'])
            print(f"  ✓ {len(queues)} colas Queue Tree eliminadas")
    else:
        print(f"  ℹ️  No hay colas Queue Tree previas")


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


def _mangle_params(rule: dict) -> list:
    """Convierte un dict de regla Mangle a params '=clave=valor' para el API."""
    params = [f'=chain={rule["chain"]}', f'=action={rule["action"]}']
    for key, value in rule.items():
        if key not in ('chain', 'action'):
            params.append(f'={key}={value}')
    return params


def step_4_apply_mangle(api: MikroTikAPI, qos: dict, dry_run: bool = False):
    """Aplicar (o mostrar) las reglas Mangle."""
    print_step(4, "Aplicar reglas Mangle (marcado de tráfico)")
    mangle_rules = build_mangle_rules(qos)

    if dry_run:
        print(f"\n  🔍 [dry-run] Se aplicarían {len(mangle_rules)} reglas Mangle:")
        for i, rule in enumerate(mangle_rules, 1):
            detalle = " ".join(p.lstrip("=") for p in _mangle_params(rule)
                               if not p.startswith("=comment"))
            print(f"    [{i:2d}/{len(mangle_rules)}] {rule['comment']}")
            print(f"            {detalle}")
        return

    print(f"\n  📝 Aplicando {len(mangle_rules)} reglas Mangle...")
    for i, rule in enumerate(mangle_rules, 1):
        try:
            api.command('/ip/firewall/mangle/add', params=_mangle_params(rule))
            print(f"    ✓ [{i:2d}/{len(mangle_rules)}] {rule['comment']}")
        except Exception as e:
            print(f"    ❌ [{i:2d}/{len(mangle_rules)}] {rule['comment']} — ERROR: {e}")

    print(f"\n  ✓ {len(mangle_rules)} reglas Mangle aplicadas")


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


def step_5_apply_queue_tree(api: MikroTikAPI, qos: dict, dry_run: bool = False):
    """Crear (o mostrar) el árbol de colas Queue Tree."""
    print_step(5, "Crear árbol de colas Queue Tree")
    queues = build_queue_tree(qos)

    if dry_run:
        print(f"\n  🔍 [dry-run] Se crearían {len(queues)} colas Queue Tree:")
        for i, queue in enumerate(queues, 1):
            limits = (f"limit-at={queue.get('limit-at', '—')} "
                      f"max-limit={queue.get('max-limit', '—')} "
                      f"priority={queue.get('priority', '—')}")
            print(f"    [{i:2d}/{len(queues)}] {queue['name']:<15} "
                  f"parent={queue['parent']:<13} {limits}")
        return

    print(f"\n  📝 Creando {len(queues)} colas Queue Tree...")
    for i, queue in enumerate(queues, 1):
        params = [f'={key}={value}' for key, value in queue.items()]
        try:
            api.command('/queue/tree/add', params=params)
            print(f"    ✓ [{i:2d}/{len(queues)}] {queue['name']} — {queue['comment']}")
        except Exception as e:
            print(f"    ❌ [{i:2d}/{len(queues)}] {queue['name']} — ERROR: {e}")

    print(f"\n  ✓ {len(queues)} colas Queue Tree creadas")


def step_6_verify(api: MikroTikAPI, qos: dict):
    """Verificación final."""
    print_step(6, "Verificación final")
    device = qos["dispositivo_prioritario"]

    print("\n📊 Resumen de configuración QoS:")

    # Contar reglas Mangle
    mangle = api.command('/ip/firewall/mangle/print')
    print(f"  ✓ {len(mangle)} reglas Mangle activas")

    # Contar colas Queue Tree
    queues = api.command('/queue/tree/print')
    print(f"  ✓ {len(queues)} colas Queue Tree activas")

    # Mostrar estado de FastTrack
    fasttrack = api.command('/ip/firewall/filter/print',
                            queries=['?action=fasttrack-connection'])
    if fasttrack:
        for rule in fasttrack:
            disabled = rule.get('disabled') == 'true'
            status = "✓ Deshabilitado" if disabled else "❌ ACTIVO (debe deshabilitarse)"
            print(f"  {status} — FastTrack")
    else:
        print(f"  ℹ️  No hay reglas FastTrack")

    # Mostrar IP del dispositivo prioritario
    leases = api.command('/ip/dhcp-server/lease/print',
                         queries=[f"?mac-address={device['mac']}"])
    if leases:
        for lease in leases:
            print(f"  ✓ IP fija de {device['nombre']}: {lease.get('address', 'N/A')}")

    # CPU y recursos (informativo, mejor esfuerzo: el despliegue ya terminó)
    try:
        resources = api.command('/system/resource/print')
        if resources:
            res = resources[0]
            cpu_load = res.get('cpu-load', 'N/A')
            free_mem = res.get('free-memory', 'N/A')
            print(f"  📈 CPU Load: {cpu_load}% | Free Memory: {free_mem} bytes")
    except Exception:
        pass

    print("\n" + "=" * 70)
    print("  ✅ Plan QoS desplegado exitosamente")
    print("=" * 70)
    print("\nPróximos pasos:")
    print("  1. Probar descarga pesada desde otro dispositivo (>30 MB)")
    print("  2. Activar OBS en Kevin y verificar estabilidad del stream")
    print("  3. Hacer ping desde Kevin a servidor de juegos")
    print("  4. Monitorear en Winbox → Queues → Queue Tree")
    print("  5. Si algo falla, ejecutar: scripts/qos_desplegar.py --rollback")


def rollback(api: MikroTikAPI):
    """Reverter toda la configuración QoS."""
    print_header("ROLLBACK - Revertiendo configuración QoS")

    print("\n🗑️  Eliminando todas las reglas Mangle...")
    mangle = api.command('/ip/firewall/mangle/print')
    for rule in mangle:
        rule_id = rule.get('.id', '')
        if rule_id:
            api.command('/ip/firewall/mangle/remove', params=[f'=.id={rule_id}'])
    print(f"  ✓ {len(mangle)} reglas Mangle eliminadas")

    print("\n🗑️  Eliminando todas las colas Queue Tree...")
    queues = api.command('/queue/tree/print')
    for queue in reversed(queues):
        queue_id = queue.get('.id', '')
        if queue_id:
            api.command('/queue/tree/remove', params=[f'=.id={queue_id}'])
    print(f"  ✓ {len(queues)} colas Queue Tree eliminadas")

    print("\n🚀 Rehabilitando FastTrack...")
    fasttrack = api.command('/ip/firewall/filter/print',
                            queries=['?action=fasttrack-connection'])
    for rule in fasttrack:
        rule_id = rule.get('.id', '')
        if rule_id:
            api.command('/ip/firewall/filter/set',
                        params=[f'=.id={rule_id}', '=disabled=no'])
    print(f"  ✓ FastTrack rehabilitado")

    print("\n" + "=" * 70)
    print("  ✅ Rollback completado — Red en estado limpio")
    print("=" * 70)


def main():
    """Punto de entrada principal."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Desplegar Plan QoS MikroTik — hEX lite — RouterOS v6.49.19"
    )
    parser.add_argument(
        '--rollback',
        action='store_true',
        help='Revertir toda la configuración QoS'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Mostrar todo lo que se haría SIN modificar el router'
    )
    args = parser.parse_args()

    qos = load_qos_config()
    device = qos["dispositivo_prioritario"]
    titulo = f"🌐 Despliegue Plan QoS MikroTik — {device['nombre']}"
    if args.dry_run:
        titulo += "  [DRY-RUN: sin cambios]"
    print_header(titulo)

    config = load_config()
    print(f"Conectando a {config['host']}:{config['port']}...")

    with MikroTikAPI(**config) as api:
        print("✓ Conectado\n")

        if args.rollback:
            rollback(api)
        else:
            # Ejecutar todos los pasos en orden
            step_0_verify(api, qos)
            step_1_static_ip(api, qos, dry_run=args.dry_run)
            step_2_disable_fasttrack(api, dry_run=args.dry_run)
            step_3_cleanup_qos(api, dry_run=args.dry_run)
            step_4_apply_mangle(api, qos, dry_run=args.dry_run)
            step_5_apply_queue_tree(api, qos, dry_run=args.dry_run)
            if args.dry_run:
                print("\n" + "=" * 70)
                print("  🔍 DRY-RUN completado — el router NO fue modificado")
                print("=" * 70)
            else:
                step_6_verify(api, qos)



if __name__ == "__main__":
    run_script(main)
