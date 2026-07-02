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

from lib import MikroTikAPI, load_config, print_header, run_script
from core.qos import (load_qos_config, build_mangle_rules, build_queue_tree,
                      mangle_params, buscar_lease, fijar_ip_estatica,
                      buscar_fasttrack, deshabilitar_fasttrack,
                      rehabilitar_fasttrack, eliminar_reglas_mangle,
                      eliminar_colas, aplicar_reglas_mangle, crear_colas)


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
    fasttrack = buscar_fasttrack(api)
    if fasttrack:
        for rule in fasttrack:
            status = "❌ ACTIVO" if rule.get('disabled') == 'false' else "✓ Deshabilitado"
            print(f"  {status} — {rule.get('comment', 'Sin comentario')}")
    else:
        print("  ℹ️  No hay reglas FastTrack configuradas")

    print(f"\n👤 Buscando IP de {device['nombre']} (MAC: {device['mac']}):")
    leases = buscar_lease(api, device['mac'])
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
    existing = buscar_lease(api, device['mac'])

    if dry_run:
        accion = "actualizaría" if existing else "crearía"
        print(f"  🔍 [dry-run] Se {accion} el lease: "
              f"MAC {device['mac']} → {device['ip']} ({comment})")
        return

    if existing:
        print(f"  ℹ️  Lease existente para {device['nombre']}. Actualizando...")
        lease_id = existing[0].get('.id', '')
        if lease_id:
            fijar_ip_estatica(api, device, lease_id=lease_id)
            print(f"  ✓ IP estática confirmada")
    else:
        print(f"  ℹ️  Creando nuevo lease para {device['nombre']}...")
        fijar_ip_estatica(api, device)
        print(f"  ✓ IP estática creada")


def step_2_disable_fasttrack(api: MikroTikAPI, dry_run: bool = False):
    """Deshabilitar FastTrack."""
    print_step(2, "Deshabilitar FastTrack")

    fasttrack = buscar_fasttrack(api)
    if fasttrack:
        for rule in fasttrack:
            rule_id = rule.get('.id', '')
            if not rule_id:
                continue
            if dry_run:
                print(f"  🔍 [dry-run] Se deshabilitaría FastTrack: "
                      f"{rule.get('comment', 'sin comentario')}")
                continue
            deshabilitar_fasttrack(api, [rule])
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
            eliminar_reglas_mangle(api, mangle_rules)
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
            eliminar_colas(api, queues)
            print(f"  ✓ {len(queues)} colas Queue Tree eliminadas")
    else:
        print(f"  ℹ️  No hay colas Queue Tree previas")


def step_4_apply_mangle(api: MikroTikAPI, qos: dict, dry_run: bool = False):
    """Aplicar (o mostrar) las reglas Mangle."""
    print_step(4, "Aplicar reglas Mangle (marcado de tráfico)")
    mangle_rules = build_mangle_rules(qos)

    if dry_run:
        print(f"\n  🔍 [dry-run] Se aplicarían {len(mangle_rules)} reglas Mangle:")
        for i, rule in enumerate(mangle_rules, 1):
            detalle = " ".join(p.lstrip("=") for p in mangle_params(rule)
                               if not p.startswith("=comment"))
            print(f"    [{i:2d}/{len(mangle_rules)}] {rule['comment']}")
            print(f"            {detalle}")
        return

    print(f"\n  📝 Aplicando {len(mangle_rules)} reglas Mangle...")
    for i, (rule, error) in enumerate(aplicar_reglas_mangle(api, mangle_rules), 1):
        if error is None:
            print(f"    ✓ [{i:2d}/{len(mangle_rules)}] {rule['comment']}")
        else:
            print(f"    ❌ [{i:2d}/{len(mangle_rules)}] {rule['comment']} — ERROR: {error}")

    print(f"\n  ✓ {len(mangle_rules)} reglas Mangle aplicadas")


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
    for i, (queue, error) in enumerate(crear_colas(api, queues), 1):
        if error is None:
            print(f"    ✓ [{i:2d}/{len(queues)}] {queue['name']} — {queue['comment']}")
        else:
            print(f"    ❌ [{i:2d}/{len(queues)}] {queue['name']} — ERROR: {error}")

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
    fasttrack = buscar_fasttrack(api)
    if fasttrack:
        for rule in fasttrack:
            disabled = rule.get('disabled') == 'true'
            status = "✓ Deshabilitado" if disabled else "❌ ACTIVO (debe deshabilitarse)"
            print(f"  {status} — FastTrack")
    else:
        print(f"  ℹ️  No hay reglas FastTrack")

    # Mostrar IP del dispositivo prioritario
    leases = buscar_lease(api, device['mac'])
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
    eliminar_reglas_mangle(api, mangle)
    print(f"  ✓ {len(mangle)} reglas Mangle eliminadas")

    print("\n🗑️  Eliminando todas las colas Queue Tree...")
    queues = api.command('/queue/tree/print')
    eliminar_colas(api, queues)
    print(f"  ✓ {len(queues)} colas Queue Tree eliminadas")

    print("\n🚀 Rehabilitando FastTrack...")
    rehabilitar_fasttrack(api, solo_deshabilitadas=False)
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
