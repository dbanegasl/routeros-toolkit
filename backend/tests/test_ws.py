"""
test_ws.py — WebSockets: auth, payloads y muestreo compartido
=============================================================
"""

import pytest
from starlette.websockets import WebSocketDisconnect

from backend.app.ws import CIERRE_SIN_SESION


class TestAuthWs:

    def test_sin_sesion_cierra_4401(self, client):
        with pytest.raises(WebSocketDisconnect) as exc:
            with client.websocket_connect("/ws/monitor") as ws:
                ws.receive_json()
        assert exc.value.code == CIERRE_SIN_SESION

    def test_log_sin_sesion_cierra_4401(self, client):
        with pytest.raises(WebSocketDisconnect) as exc:
            with client.websocket_connect("/ws/log") as ws:
                ws.receive_json()
        assert exc.value.code == CIERRE_SIN_SESION


class TestMonitor:

    def test_payload_monitor(self, session):
        with session.websocket_connect("/ws/monitor") as ws:
            datos = ws.receive_json()
        assert "ts" in datos
        assert datos["conexiones_totales"] == 2
        # Kevin es el único con tráfico LAN en la FakeAPI
        ips = [d["ip"] for d in datos["dispositivos"]]
        assert "192.168.5.22" in ips
        # Interfaces presentes, con velocidad calculada (0 en primera muestra)
        nombres = [i["nombre"] for i in datos["interfaces"]]
        assert "ether1" in nombres and "bridge1" in nombres

    def test_payload_log(self, session):
        session.fake_api.responses["/log/print"] = [
            {"time": "10:00:00", "topics": "dhcp,info", "message": "lease OK"},
            {"time": "10:00:01", "topics": "system,error", "message": "falló"},
        ]
        with session.websocket_connect("/ws/log") as ws:
            datos = ws.receive_json()
        assert len(datos["entradas"]) == 2
        assert datos["entradas"][0]["nivel"] == "info"
        assert datos["entradas"][1]["nivel"] == "error"


class TestMuestreoCompartido:

    def test_dos_clientes_una_conexion_al_router(self, session):
        """Dos pestañas conectadas = UNA sola conexión API al router."""
        with session.websocket_connect("/ws/monitor") as ws1:
            ws1.receive_json()
            with session.websocket_connect("/ws/monitor") as ws2:
                # Ambos reciben datos del mismo bucle
                d2 = ws2.receive_json()
                assert "dispositivos" in d2
        # crear_api se llamó exactamente una vez pese a 2 clientes y N ciclos
        assert session.ws_conexiones == [1]

    def test_navegar_entre_paginas_no_reconecta(self, session):
        """Entrar y salir de Monitoreo/Log repetidas veces reutiliza la
        conexión compartida: cero logins extra en el syslog del router."""
        for _ in range(3):
            with session.websocket_connect("/ws/monitor") as ws:
                ws.receive_json()
            with session.websocket_connect("/ws/log") as ws:
                ws.receive_json()
        assert session.ws_conexiones == [1]

    def test_ultimo_cliente_detiene_muestreo(self, session):
        with session.websocket_connect("/ws/monitor") as ws:
            ws.receive_json()
            muestras_previas = len(session.ws_conexiones)
        # Al salir del with no quedan clientes; el bucle se canceló
        from backend.app.ws import muestreador_monitor
        assert muestreador_monitor.clientes == set()
        assert muestras_previas == 1