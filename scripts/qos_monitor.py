#!/usr/bin/env python3
"""
Monitor de QoS en Tiempo Real
==============================

Monitorea el tráfico por categoría (Kevin, Trabajo, Streaming, etc)
en tiempo real mientras se está usando la red.

Uso:
    python3 scripts/qos_monitor.py
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from lib import MikroTikAPI, load_config, print_header, fmt_bytes, run_script


def format_bps(bytes_per_sec):
    """Convierte bytes/segundo a Mbps (multiplica por 8 para obtener bits)."""
    return f"{bytes_per_sec * 8 / 1_000_000:.2f} Mbps"


def main():
    print_header("📊 Monitor QoS en Tiempo Real")
    print("Presiona Ctrl+C para salir\n")
    
    config = load_config()
    
    with MikroTikAPI(**config) as api:
        # Categorías a monitorear basadas en Mangle marks
        categories = {
            'pkt_critico': ('🔴 CRÍTICO', 'DNS + ICMP'),
            'pkt_kevin': ('🎮 KEVIN', 'Gaming + OBS'),
            'pkt_trabajo': ('💼 TRABAJO', 'SSH/VPN/Dev'),
            'pkt_streaming': ('🎬 STREAMING', 'Netflix/HBO'),
            'pkt_web': ('🌐 WEB', 'HTTP General'),
            'pkt_resto': ('📡 RESTO', 'Sin clasificar'),
            'pkt_bulk': ('📥 BULK', 'Descargas >30MB'),
        }
        
        prev_bytes = {}
        prev_time = time.time()
        
        iteration = 0
        while True:
            iteration += 1
            current_time = time.time()
            time_diff = current_time - prev_time
            
            if iteration == 1:
                print(f"{'Categoría':<15} {'Bytes':<15} {'Velocidad':<15} {'Descripción':<25}")
                print("-" * 70)
            
            # Obtener estadísticas de Queue Tree
            queues = api.command('/queue/tree/print')
            
            total_rate = 0
            for queue in queues:
                packet_mark = queue.get('packet-mark', '')
                bytes_val = int(queue.get('bytes', 0))
                
                if packet_mark in categories:
                    label, desc = categories[packet_mark]
                    
                    # Calcular velocidad
                    if packet_mark in prev_bytes:
                        bytes_diff = bytes_val - prev_bytes[packet_mark]
                        rate = bytes_diff / time_diff if time_diff > 0 else 0
                        total_rate += rate
                    else:
                        rate = 0
                    
                    prev_bytes[packet_mark] = bytes_val
                    
                    print(f"{label:<15} {fmt_bytes(bytes_val):<15} "
                          f"{format_bps(rate):<15} {desc:<25}")
            
            print(f"{'═'*70}")
            print(f"{'📈 TOTAL':<15} {'':<15} {format_bps(total_rate):<15}")
            print(f"{'═'*70}\n")
            
            prev_time = current_time
            time.sleep(5)  # Actualizar cada 5 segundos
            


if __name__ == "__main__":
    run_script(main)
