#!/usr/bin/env python3
"""
04_interface_stats.py — Estadísticas de tráfico por interfaz
=============================================================

Muestra el tráfico acumulado y la velocidad actual de cada interfaz
del router. Útil para identificar qué puerto físico (ether1–ether5)
está generando más tráfico.

Interfaces típicas en esta instalación:
    ether1   — WAN (conexión al ISP)
    ether2   — sin uso
    ether3   — switch / AP zona 1
    ether4   — switch / AP zona 2
    ether5   — switch / AP zona 3
    bridge1  — bridge virtual que agrupa ether3/4/5 (LAN total)

Modo continuo (--watch):
    Toma dos muestras con N segundos de diferencia y calcula la
    velocidad real en ese intervalo. Más preciso que orig-rate.

Uso:
    cd mikrotik/
    python3 scripts/04_interface_stats.py               # instantáneo
    python3 scripts/04_interface_stats.py --watch        # mide 5s
    python3 scripts/04_interface_stats.py --watch --interval 10
"""

import sys
import os
import time
import argparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from lib import MikroTikAPI, load_config, fmt_speed, fmt_bytes, run_script


def get_iface_stats(api) -> dict:
    """Retorna dict nombre → stats del comando /interface/print stats."""
    ifaces = api.command("/interface/print", params=["=stats="])
    return {i["name"]: i for i in ifaces}


def print_table(stats: dict, delta: dict = None, interval: float = None):
    """
    Imprime la tabla de interfaces.
    Si se pasan delta y interval, añade columna de velocidad calculada.
    """
    header = (f"  {'INTERFAZ':<12} {'TIPO':<10} {'TX TOTAL':>14} "
              f"{'RX TOTAL':>14}")
    if delta:
        header += f"  {'TX/s':>12} {'RX/s':>12}"
    header += "  ESTADO"

    print(f"\n{'─'*len(header)}")
    print(header)
    print(f"{'─'*len(header)}")

    for name, s in sorted(stats.items(), key=lambda x: x[0]):
        tipo   = s.get("type", "?")
        tx     = int(s.get("tx-byte", 0))
        rx     = int(s.get("rx-byte", 0))
        status = "up" if s.get("running") == "true" else "down"

        row = (f"  {name:<12} {tipo:<10} {fmt_bytes(tx):>14} "
               f"{fmt_bytes(rx):>14}")

        if delta and name in delta:
            d = delta[name]
            tx_rate = int(d.get("tx-byte", 0)) * 8 // max(interval, 1)
            rx_rate = int(d.get("rx-byte", 0)) * 8 // max(interval, 1)
            row += f"  {fmt_speed(tx_rate):>12} {fmt_speed(rx_rate):>12}"

        row += f"  {status}"
        print(row)

    print(f"{'─'*len(header)}\n")


def main():
    parser = argparse.ArgumentParser(
        description="Estadísticas de tráfico por interfaz MikroTik")
    parser.add_argument("--watch", action="store_true",
                        help="Medir velocidad real (toma 2 muestras)")
    parser.add_argument("--interval", type=float, default=5.0,
                        help="Segundos entre muestras en modo --watch (default: 5)")
    args = parser.parse_args()

    cfg = load_config()
    print(f"\nConectando a {cfg['host']}...")

    with MikroTikAPI(**cfg) as api:
        if not args.watch:
            # Snapshot instantáneo
            stats = get_iface_stats(api)
            print_table(stats)
        else:
            # Dos muestras para calcular velocidad real
            print(f"Tomando muestra inicial...")
            sample1 = get_iface_stats(api)
            print(f"Esperando {args.interval}s para calcular velocidad...")
            time.sleep(args.interval)
            sample2 = get_iface_stats(api)

            # Calcular delta de bytes
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

            print_table(sample2, delta=delta, interval=args.interval)

            # Identificar interfaz más activa
            if delta:
                busiest = max(delta.items(),
                              key=lambda kv: kv[1]["tx-byte"] + kv[1]["rx-byte"])
                bname, bd = busiest
                tx_r = bd["tx-byte"] * 8 // args.interval
                rx_r = bd["rx-byte"] * 8 // args.interval
                print(f"  Interfaz más activa: {bname}  "
                      f"TX {fmt_speed(tx_r)}  RX {fmt_speed(rx_r)}\n")


if __name__ == "__main__":
    run_script(main)
