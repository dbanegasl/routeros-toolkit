#!/usr/bin/env python3
"""
Validar Router — Verificación previa de conectividad y configuración

Uso:
    python3 scripts/sys_validar.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from datetime import datetime

from lib import (MikroTikAPI, load_config, print_header, fmt_bytes,
                 load_json_config, get_router_datetime, run_script)


def main():
    print_header("🔍 VALIDAR ROUTER — RouterOS v6.49.19")
    
    config = load_config()
    print(f"Conectando a {config['host']}:{config['port']}...")
    
    with MikroTikAPI(**config) as api:
        print("✓ Conectado\n")
        
        # 1. IDENTIDAD DEL ROUTER
        print("[1] Identidad del Router")
        print("-" * 70)
        identity = api.command('/system/identity/print')
        if identity:
            print(f"  ✓ Name: {identity[0].get('name', 'N/A')}")
        
        resources = api.command('/system/resource/print')
        if resources:
            res = resources[0]
            print(f"  ✓ RouterOS: {res.get('version', 'N/A')}")
            print(f"  ✓ Platform: {res.get('platform', 'N/A')}")
            print(f"  ✓ CPU: {res.get('cpu-count', 'N/A')} cores @ {res.get('cpu-frequency', 'N/A')} MHz")
            print(f"  ✓ RAM: {fmt_bytes(int(res.get('total-memory', 0)))}")
        
        # 2. INTERFACES
        print("\n[2] Interfaces de Red")
        print("-" * 70)
        interfaces = api.command('/interface/print')
        for iface in interfaces:
            status = "🟢 UP" if iface.get('running') == 'true' else "🔴 DOWN"
            name = iface.get('name', 'N/A')
            mtu = iface.get('mtu', 'N/A')
            print(f"  {status} {name:15} (MTU: {mtu})")
        
        # 3. DIRECCIONES IP
        print("\n[3] Direcciones IP")
        print("-" * 70)
        addresses = api.command('/ip/address/print')
        for addr in addresses:
            address = addr.get('address', 'N/A')
            interface = addr.get('interface', 'N/A')
            print(f"  ✓ {address:20} → {interface}")
        
        # 4. DISPOSITIVO PRIORITARIO QoS (IP estática)
        qos = load_json_config("qos", default={})
        device = qos.get("dispositivo_prioritario", {})
        nombre = device.get("nombre", "?")
        mac = device.get("mac", "")
        print(f"\n[4] Dispositivo prioritario QoS: {nombre} ({device.get('ip', '?')})")
        print("-" * 70)
        if not mac:
            print("  ℹ️  Sin config/qos.json — se omite esta verificación")
        else:
            leases = api.command('/ip/dhcp-server/lease/print',
                                 queries=[f'?mac-address={mac}'])
            if leases:
                for lease in leases:
                    print(f"  ✓ IP: {lease.get('address', 'N/A')}")
                    print(f"  ✓ MAC: {lease.get('mac-address', 'N/A')}")
                    print(f"  ✓ Hostname: {lease.get('host-name', 'N/A')}")
                    print(f"  ✓ Comment: {lease.get('comment', 'N/A')}")
            else:
                print(f"  ⚠️  {nombre} NO encontrado por MAC {mac}")
        
        # 5. FASTTRACK
        print("\n[5] FastTrack (aceleración)")
        print("-" * 70)
        ft = api.command('/ip/firewall/filter/print',
                        queries=['?action=fasttrack-connection'])
        if ft:
            for rule in ft:
                disabled = rule.get('disabled') == 'true'
                status = "✓ DESHABILITADO" if disabled else "❌ ACTIVO"
                print(f"  {status} — {rule.get('comment', 'N/A')}")
        else:
            print(f"  ℹ️  Sin reglas FastTrack configuradas")
        
        # 6. QoS ACTUAL
        print("\n[6] Configuración QoS Actual")
        print("-" * 70)
        mangle = api.command('/ip/firewall/mangle/print')
        queues = api.command('/queue/tree/print')
        simple = api.command('/queue/simple/print')
        
        print(f"  • Mangle Rules: {len(mangle)}")
        print(f"  • Queue Tree: {len(queues)}")
        print(f"  • Queue Simple: {len(simple)}")
        
        if len(mangle) > 0:
            print(f"\n  Reglas Mangle activas:")
            for m in mangle[:5]:  # Mostrar solo las primeras 5
                comment = m.get('comment', 'N/A')
                print(f"    - {comment}")
            if len(mangle) > 5:
                print(f"    ... y {len(mangle) - 5} más")
        
        # 7. TRÁFICO (últimas 24h)
        print("\n[7] Tráfico de Interfaces")
        print("-" * 70)
        interfaces = api.command('/interface/print')
        for iface in interfaces:
            if iface.get('running') == 'true':
                name = iface.get('name')
                rx = int(iface.get('rx-byte', 0))
                tx = int(iface.get('tx-byte', 0))
                print(f"  {name:15} RX: {fmt_bytes(rx):>10}  TX: {fmt_bytes(tx):>10}")
        
        # 8. RELOJ Y NTP — el corte por horario (09) y las reglas time=
        # dependen de que la hora del router sea correcta
        print("\n[8] Reloj del router y NTP")
        print("-" * 70)
        reloj_router = get_router_datetime(api)
        if reloj_router is None:
            print("  ⚠️  No se pudo leer el reloj del router")
        else:
            deriva = abs((reloj_router - datetime.now()).total_seconds())
            print(f"  • Hora del router: {reloj_router:%Y-%m-%d %H:%M:%S}")
            print(f"  • Hora de este PC: {datetime.now():%Y-%m-%d %H:%M:%S}")
            if deriva <= 120:
                print(f"  ✓ Sincronizado (diferencia: {deriva:.0f}s)")
            else:
                print(f"  ❌ Deriva de {deriva/60:.1f} minutos — los cortes por "
                      f"horario NO ocurrirán a la hora esperada")
        try:
            ntp = api.command('/system/ntp/client/print')
            ntp_on = bool(ntp) and ntp[0].get('enabled') == 'true'
            if ntp_on:
                print(f"  ✓ Cliente NTP habilitado")
            else:
                print(f"  ⚠️  Cliente NTP deshabilitado — la hora se perderá "
                      f"al reiniciar el router")
                print(f"     Actívalo en Winbox: System → NTP Client")
        except RuntimeError:
            # Informativo, mejor esfuerzo: en algunas versiones el paquete
            # NTP no está instalado y el comando no existe
            print(f"  ℹ️  No se pudo consultar el cliente NTP")

        # 9. RESUMEN
        print("\n" + "=" * 70)
        print("  ✅ ROUTER VALIDADO")
        print("=" * 70)
        
        if len(mangle) == 0 and len(queues) == 0 and len(simple) == 0:
            print("\n  📋 Estado: SIN QoS (listo para desplegar)")
            print("  Próximo paso: python3 scripts/qos_desplegar.py")
        else:
            print("\n  📋 Estado: CON QoS ACTIVO")
            print("  Próximo paso: python3 scripts/qos_monitor.py")
        


if __name__ == "__main__":
    run_script(main)
