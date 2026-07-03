"""
test_qos.py — Endpoints QoS: plan (paridad con el CLI), despliegue,
diagnóstico, reset selectivo y /ws/qos
====================================================================
"""

import pytest
from starlette.websockets import WebSocketDisconnect

from backend.app.ws import CIERRE_SIN_SESION
from core.qos import load_qos_config, build_mangle_rules, build_queue_tree

# Estado "desplegado" simulado: una regla/cola del QoS + una ajena
MANGLE_DESPLEGADO = [
    {".id": "*A", "comment": "regla manual ajena", "chain": "forward",
     "action": "accept", "bytes": "1", "packets": "1"},
    {".id": "*B", "comment": "QoS P1 - DNS UDP", "chain": "prerouting",
     "action": "mark-connection", "bytes": "1000", "packets": "10"},
    {".id": "*C", "comment": "QoS P2 - Kevin origen (upload + gaming)",
     "chain": "prerouting", "action": "mark-connection",
     "bytes": "5000", "packets": "50"},
]
COLAS_DESPLEGADAS = [
    {".id": "*Q1", "name": "QoS_Download", "parent": "bridge1",
     "max-limit": "85M", "bytes": "0", "packets": "0", "dropped": "0"},
    {".id": "*Q2", "name": "DL-2-Kevin", "parent": "QoS_Download",
     "packet-mark": "pkt_kevin", "limit-at": "30M", "max-limit": "85M",
     "bytes": "9000", "packets": "90", "dropped": "3"},
    {".id": "*Q3", "name": "cola-ajena", "parent": "ether2",
     "max-limit": "10M", "bytes": "0", "packets": "0", "dropped": "0"},
]
FASTTRACK_ACTIVO = [
    {".id": "*F", "action": "fasttrack-connection", "disabled": "false",
     "comment": "defconf: fasttrack"},
]
FASTTRACK_APAGADO = [
    {".id": "*F", "action": "fasttrack-connection", "disabled": "true",
     "comment": "defconf: fasttrack"},
]


class TestPlan:

    def test_requiere_sesion(self, client):
        assert client.get("/api/qos/plan").status_code == 401

    def test_plan_identico_a_los_builders_del_cli(self, session):
        """El dry-run web devuelve EXACTAMENTE lo que aplicaría el CLI:
        las mismas reglas y colas de build_mangle_rules/build_queue_tree."""
        r = session.get("/api/qos/plan")
        assert r.status_code == 200
        datos = r.json()
        qos = load_qos_config()
        assert datos["mangle"] == build_mangle_rules(qos)
        assert datos["colas"] == build_queue_tree(qos)
        assert len(datos["mangle"]) == 23
        assert len(datos["colas"]) == 16

    def test_config_y_lease(self, session):
        datos = session.get("/api/qos/plan").json()
        assert datos["config"]["dispositivo"]["ip"] == "192.168.5.22"
        assert datos["config"]["descarga_total_mbps"] == 100
        # La FakeAPI tiene el lease de Kevin
        assert datos["lease"]["existe"] is True
        assert datos["lease"]["ip_actual"] == "192.168.5.22"

    def test_estado_sin_qos_desplegado(self, session):
        estado = session.get("/api/qos/plan").json()["estado"]
        assert estado["activo"] is False
        assert estado["mangle_qos"] == 0
        assert estado["colas_qos"] == 0


class TestDesplegar:

    def test_sin_confirmar_no_toca_nada(self, session):
        r = session.post("/api/qos/desplegar", json={})
        assert r.status_code == 400
        assert "confirmar" in r.json()["detail"]
        assert session.fake_api.writes == []

    def test_despliegue_completo(self, session):
        fake = session.fake_api
        fake.responses["/ip/firewall/filter/print"] = FASTTRACK_ACTIVO
        fake.responses["/ip/firewall/mangle/print"] = MANGLE_DESPLEGADO
        fake.responses["/queue/tree/print"] = COLAS_DESPLEGADAS

        r = session.post("/api/qos/desplegar", json={"confirmar": True})
        assert r.status_code == 200
        datos = r.json()
        assert datos["mangle_aplicadas"] == 23
        assert datos["colas_creadas"] == 16
        assert datos["errores"] == []
        assert datos["fasttrack_deshabilitadas"] == 1

        cmds = [cmd for cmd, _ in fake.writes]
        # IP fija (el lease de la FakeAPI no trae .id → se crea)
        assert "/ip/dhcp-server/lease/add" in cmds
        # FastTrack deshabilitado
        assert ("/ip/firewall/filter/set",
                ["=.id=*F", "=disabled=yes"]) in fake.writes
        # Plan completo aplicado
        assert cmds.count("/ip/firewall/mangle/add") == 23
        assert cmds.count("/queue/tree/add") == 16

    def test_limpieza_previa_es_selectiva(self, session):
        """El despliegue limpia SOLO lo etiquetado del QoS: las reglas
        Mangle y colas ajenas se preservan (a diferencia del CLI)."""
        fake = session.fake_api
        fake.responses["/ip/firewall/mangle/print"] = MANGLE_DESPLEGADO
        fake.responses["/queue/tree/print"] = COLAS_DESPLEGADAS

        r = session.post("/api/qos/desplegar", json={"confirmar": True})
        datos = r.json()
        assert datos["mangle_previas_eliminadas"] == 2
        assert datos["colas_previas_eliminadas"] == 2

        removes = [p for cmd, p in fake.writes
                   if cmd == "/ip/firewall/mangle/remove"]
        assert removes == [["=.id=*B"], ["=.id=*C"]]     # *A (ajena) intacta
        q_removes = [p for cmd, p in fake.writes
                     if cmd == "/queue/tree/remove"]
        # Orden inverso: primero la subcola, después la raíz; *Q3 intacta
        assert q_removes == [["=.id=*Q2"], ["=.id=*Q1"]]


class TestReset:

    def test_sin_confirmar_no_toca_nada(self, session):
        r = session.request("DELETE", "/api/qos", json={})
        assert r.status_code == 400
        assert session.fake_api.writes == []

    def test_reset_selectivo_y_fasttrack(self, session):
        fake = session.fake_api
        fake.responses["/ip/firewall/mangle/print"] = MANGLE_DESPLEGADO
        fake.responses["/queue/tree/print"] = COLAS_DESPLEGADAS
        fake.responses["/ip/firewall/filter/print"] = FASTTRACK_APAGADO

        r = session.request("DELETE", "/api/qos", json={"confirmar": True})
        assert r.status_code == 200
        datos = r.json()
        assert datos["mangle_eliminadas"] == 2
        assert datos["colas_eliminadas"] == 2
        assert datos["fasttrack_rehabilitadas"] == 1

        removes = [p for cmd, p in fake.writes
                   if cmd == "/ip/firewall/mangle/remove"]
        assert removes == [["=.id=*B"], ["=.id=*C"]]
        assert ("/ip/firewall/filter/set",
                ["=.id=*F", "=disabled=no"]) in fake.writes

    def test_sin_qos_desplegado(self, session):
        r = session.request("DELETE", "/api/qos", json={"confirmar": True})
        assert r.status_code == 200
        assert "No había" in r.json()["mensaje"]


class TestDiagnostico:

    def test_requiere_sesion(self, client):
        assert client.get("/api/qos/diagnostico").status_code == 401

    def test_marcas_y_colas(self, session):
        fake = session.fake_api
        fake.responses["/ip/firewall/mangle/print"] = MANGLE_DESPLEGADO
        fake.responses["/queue/tree/print"] = COLAS_DESPLEGADAS
        fake.responses["/ip/firewall/filter/print"] = FASTTRACK_APAGADO

        datos = session.get("/api/qos/diagnostico").json()
        assert datos["estado"]["activo"] is True
        assert datos["estado"]["fasttrack_activo"] is False

        marcas = {m["prioridad"]: m for m in datos["marcas"]}
        # Solo reglas del QoS (la ajena no aparece)
        assert set(marcas) == {"P1_Critico", "P2_Kevin"}
        assert marcas["P2_Kevin"]["bytes"] == 5000

        colas = {c["nombre"]: c for c in datos["colas"]}
        assert set(colas) == {"QoS_Download", "DL-2-Kevin"}   # sin la ajena
        assert colas["DL-2-Kevin"]["descartados"] == 3
        assert colas["DL-2-Kevin"]["limite"] == "30M"


class TestWsQos:

    def test_sin_sesion_cierra_4401(self, client):
        with pytest.raises(WebSocketDisconnect) as exc:
            with client.websocket_connect("/ws/qos") as ws:
                ws.receive_json()
        assert exc.value.code == CIERRE_SIN_SESION

    def test_payload_qos(self, session):
        session.fake_api.responses["/queue/tree/print"] = COLAS_DESPLEGADAS
        with session.websocket_connect("/ws/qos") as ws:
            datos = ws.receive_json()
        assert "ts" in datos
        assert datos["activo"] is True
        nombres = [c["nombre"] for c in datos["colas"]]
        assert nombres == ["QoS_Download", "DL-2-Kevin"]      # sin la ajena
        kevin = datos["colas"][1]
        assert kevin["mark"] == "pkt_kevin"
        assert kevin["bytes"] == 9000
        assert kevin["rate"] == 0                # primera muestra, sin delta

    def test_comparte_la_conexion_persistente(self, session):
        with session.websocket_connect("/ws/qos") as ws:
            ws.receive_json()
        with session.websocket_connect("/ws/monitor") as ws:
            ws.receive_json()
        assert session.ws_conexiones == [1]
