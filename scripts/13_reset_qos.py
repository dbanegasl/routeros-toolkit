#!/usr/bin/env python3
"""
Reset Total de QoS
==================

Elimina las reglas Mangle y colas Queue Tree creadas por el despliegue
QoS (script 10) y rehabilita FastTrack, para volver a estado limpio.

SOLO toca elementos del QoS (reglas Mangle con comentario 'QoS ...' y
colas 'QoS_*/DL-*/UL-*'). Las reglas de otros gestores (bloqueos del
script 06, horarios del script 09, reglas manuales) se preservan.

Uso:
    python3 scripts/13_reset_qos.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from lib import MikroTikAPI, load_config, print_header, run_script

# Prefijos que identifican los elementos creados por 10_deploy_qos.py
QOS_COMMENT_PREFIX = "QoS"
QOS_QUEUE_PREFIXES = ("QoS_", "DL-", "UL-")


def main():
    print_header("🔄 RESET QoS - Limpiar reglas y colas del QoS")

    config = load_config()
    print(f"Conectando a {config['host']}...")

    with MikroTikAPI(**config) as api:
        print("✓ Conectado\n")

        # 1. Eliminar reglas Mangle del QoS (comentario 'QoS ...')
        print("[1] Eliminando reglas Mangle del QoS...")
        mangle = api.command('/ip/firewall/mangle/print')
        qos_mangle = [m for m in mangle
                      if m.get('comment', '').startswith(QOS_COMMENT_PREFIX)]
        otras = len(mangle) - len(qos_mangle)
        for m in qos_mangle:
            print(f"    - {m.get('comment', 'Sin comentario')}")
            api.command('/ip/firewall/mangle/remove',
                        params=[f"=.id={m['.id']}"])
        print(f"    ✓ {len(qos_mangle)} reglas Mangle eliminadas"
              + (f" ({otras} ajenas preservadas)" if otras else "") + "\n")

        # 2. Eliminar colas Queue Tree del QoS (orden inverso:
        #    primero subcolas, luego colas padre)
        print("[2] Eliminando Queue Tree del QoS...")
        trees = api.command('/queue/tree/print')
        qos_trees = [t for t in trees
                     if t.get('name', '').startswith(QOS_QUEUE_PREFIXES)]
        otras_q = len(trees) - len(qos_trees)
        for t in reversed(qos_trees):
            print(f"    - {t.get('name', 'Sin nombre')}")
            api.command('/queue/tree/remove', params=[f"=.id={t['.id']}"])
        print(f"    ✓ {len(qos_trees)} colas eliminadas"
              + (f" ({otras_q} ajenas preservadas)" if otras_q else "") + "\n")

        # 3. Rehabilitar FastTrack (el despliegue lo deshabilita)
        print("[3] Rehabilitando FastTrack...")
        ft = api.command('/ip/firewall/filter/print',
                         queries=['?action=fasttrack-connection'])
        rehabilitadas = 0
        for rule in ft:
            if rule.get('disabled') == 'true':
                api.command('/ip/firewall/filter/set',
                            params=[f"=.id={rule['.id']}", '=disabled=no'])
                rehabilitadas += 1
        if rehabilitadas:
            print(f"    ✓ {rehabilitadas} regla(s) FastTrack rehabilitada(s)\n")
        elif ft:
            print(f"    ℹ️  FastTrack ya estaba activo\n")
        else:
            print(f"    ℹ️  Sin reglas FastTrack\n")

        print_header("✅ RESET COMPLETADO")
        print(f"Eliminado:")
        print(f"  • {len(qos_mangle)} reglas Mangle del QoS")
        print(f"  • {len(qos_trees)} colas Queue Tree del QoS")
        print(f"\n✓ Reglas de otros gestores (bloqueos, horarios) intactas")
        print(f"\nPróximo paso:")
        print(f"  python3 scripts/10_deploy_qos.py")



if __name__ == "__main__":
    run_script(main)
