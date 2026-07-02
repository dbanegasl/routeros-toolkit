#!/usr/bin/env python3
"""
Script de Diagnóstico — Verificar si las reglas Mangle están funcionando
correctamente y cómo se está marcando el tráfico de descargas pesadas.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from lib import MikroTikAPI, load_config, print_header, run_script
from core.qos import agrupar_por_prioridad


def main():
    print_header("🔍 Diagnóstico QoS — Verificar marcado de tráfico")

    config = load_config()
    print(f"Conectando a {config['host']}...")

    with MikroTikAPI(**config) as api:
        print("✓ Conectado\n")

        # ============================================================
        # 1. VER CONTADORES DE REGLAS MANGLE
        # ============================================================
        print_header("1️⃣  CONTADORES DE REGLAS MANGLE")

        mangle = api.command('/ip/firewall/mangle/print')
        print(f"Total de reglas: {len(mangle)}\n")

        marks = agrupar_por_prioridad(mangle)

        # Mostrar por prioridad
        for priority in sorted(marks.keys()):
            data = marks[priority]
            print(f"🏷️  {priority}")
            print(f"   Total: {data['bytes']:,} bytes | {data['packets']} packets")
            
            # Mostrar reglas individuales
            for rule in data['rules']:
                bytes_mb = rule['bytes'] / (1024*1024)
                marker = "↑↑ ALTO TRÁFICO" if rule['bytes'] > 100_000_000 else ""
                print(f"     • {rule['comment']}: {bytes_mb:.1f} MB | {rule['packets']} pkt {marker}")
            print()
        
        # ============================================================
        # 2. VERIFICAR REGLAS ESPECÍFICAS DE BULK (>30MB)
        # ============================================================
        print_header("2️⃣  REGLAS DE DESCARGAS PESADAS (BULK)")
        
        bulk_rules = [r for r in mangle if 'P8' in r.get('comment', '')]
        print(f"Reglas bulk encontradas: {len(bulk_rules)}\n")
        
        for rule in bulk_rules:
            chain = rule.get('chain', 'N/A')
            action = rule.get('action', 'N/A')
            protocol = rule.get('protocol', 'N/A')
            conn_bytes = rule.get('connection-bytes', 'N/A')
            conn_mark = rule.get('connection-mark', 'N/A')
            new_mark = rule.get('new-connection-mark', '')
            bytes_val = int(rule.get('bytes', 0))
            packets_val = int(rule.get('packets', 0))
            
            print(f"Chain: {chain}")
            print(f"Action: {action}")
            print(f"Protocol: {protocol}")
            print(f"Connection-bytes: {conn_bytes}")
            print(f"Connection-mark: {conn_mark}")
            print(f"New-connection-mark: {new_mark}")
            print(f"Bytes: {bytes_val:,} | Packets: {packets_val}")
            print()
        
        if not bulk_rules:
            print("❌ NO HAY REGLAS BULK - PROBLEMA ENCONTRADO!")
        
        # ============================================================
        # 3. VERIFICAR COLAS QUEUE TREE
        # ============================================================
        print_header("3️⃣  ESTADÍSTICAS DE COLAS QUEUE TREE")
        
        queues = api.command('/queue/tree/print')
        print(f"Total de colas: {len(queues)}\n")
        
        # Mostrar las colas principales
        for queue in queues:
            name = queue.get('name', 'unknown')
            parent = queue.get('parent', 'N/A')
            bytes_val = int(queue.get('bytes', 0))
            packets_val = int(queue.get('packets', 0))
            dropped = int(queue.get('dropped', 0))
            limit_at = queue.get('limit-at', 'N/A')
            max_limit = queue.get('max-limit', 'N/A')
            
            bytes_mb = bytes_val / (1024*1024)
            
            # Destacar colas importantes
            if 'Kevin' in name or 'DL-2' in name or 'UL-2' in name:
                marker = "⭐ KEVIN"
            elif 'Bulk' in name or 'DL-8' in name or 'UL-8' in name:
                marker = "📦 BULK"
            else:
                marker = ""
            
            print(f"{name:20} | Parent: {parent:15} {marker}")
            print(f"  Bytes: {bytes_mb:8.1f} MB | Packets: {packets_val:8} | Dropped: {dropped:6}")
            print(f"  Limit: {limit_at:8} | Max: {max_limit:8}")
            print()
        
        # ============================================================
        # 4. ANÁLISIS Y RECOMENDACIONES
        # ============================================================
        print_header("4️⃣  ANÁLISIS Y DIAGNÓSTICO")
        
        # Contar bytes en cada categoría
        kevin_bytes = sum(r['bytes'] for r in marks.get('P2_Kevin', {}).get('rules', []))
        bulk_bytes = sum(r['bytes'] for r in marks.get('P8_Bulk', {}).get('rules', []))
        
        print("HALLAZGOS:\n")
        
        if kevin_bytes > 100_000_000:
            print("✓ Kevin está siendo priorizado — muchos bytes pasando por pkt_kevin")
        else:
            print("⚠️  Kevin no tiene muchos bytes — verificar si está activo")
        
        if bulk_bytes > 50_000_000:
            print("✓ Reglas de bulk están detectando tráfico > 30MB")
        else:
            print("⚠️  Reglas de bulk NO están detectando descargas pesadas")
            print("   Causa probable: connection-bytes no funciona para tráfico local (LAN-to-LAN)")
        
        # Buscar si hay tráfico en "Resto" (pkt_resto) que debería estar en "Bulk"
        resto_bytes = sum(r['bytes'] for r in marks.get('P7_Resto', {}).get('rules', []))
        if resto_bytes > 100_000_000:
            print(f"\n❌ PROBLEMA ENCONTRADO: {resto_bytes/1024/1024:.0f} MB en P7_Resto")
            print("   Esto debería estar en P8_Bulk si es una descarga > 30MB")
            print("\nCausas posibles:")
            print("  1. connection-bytes no está funcionando para tráfico local")
            print("  2. El umbral de 30MB es muy alto para detectar rápido")
            print("  3. Las reglas de bulk están en chain=forward pero el tráfico local")
            print("     no pasa por forward, pasa por bridge")
        
        print("\n" + "="*70)
        print("RECOMENDACIONES:")
        print("="*70 + "\n")
        
        if bulk_bytes < 50_000_000 and resto_bytes > 100_000_000:
            print("1. El problema es que connection-bytes en chain=forward no captura")
            print("   tráfico local (LAN-to-LAN).\n")
            print("   SOLUCIONES:")
            print("   a) Bajar el umbral de 30MB a algo más bajo (5-10MB)")
            print("   b) Usar chain=postrouting además de chain=forward")
            print("   c) Agregar reglas basadas en velocidad (rate)")
            print("   d) Agregar puertos específicos de descargas (Steam, Epic, etc)\n")
        
        elif bulk_bytes > 50_000_000:
            print("El QoS parece estar funcionando pero Kevin sigue perdiendo prioridad.\n")
            print("POSIBLES PROBLEMAS:")
            print("  • DL-8-Bulk tiene limit-at=4M, que es muy bajo")
            print("  • Si hay múltiples descargas, podrían sumar >92M total")
            print("  • Verificar que DL-2-Kevin tiene suficiente limit-at\n")
        


if __name__ == "__main__":
    run_script(main)
