"""
core/ — Lógica de negocio del toolkit (stdlib puro)
====================================================

Única fuente de lógica compartida entre los scripts CLI (scripts/) y el
futuro backend web (backend/). Los módulos NO imprimen ni piden input:
reciben una MikroTikAPI ya conectada y retornan datos; la capa de
presentación (CLI o web) decide cómo mostrarlos.

Módulos:
    dispositivos — inventario, escaneo y clasificación de dispositivos
    monitoreo    — consumo por dispositivo, interfaces, sistema, log
    bloqueos     — bloqueo/desbloqueo de IPs en el firewall
    horario      — corte de internet por horario + lista blanca persistente
    qos          — builders del plan QoS + operaciones de despliegue/reset
    respaldo     — snapshot local y respaldo .backup en el router
"""
