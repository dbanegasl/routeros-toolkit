"""
test_endpoints.py — Endpoints de lectura con FakeAPI (sin router)
=================================================================

Un test por sección más el mapeo de excepciones a códigos HTTP.
"""

import pytest

from backend.app.deps import get_api
from backend.app.main import app
from lib import MikroTikConnectionError, MikroTikCommandError


class TestDispositivos:

    def test_inventario(self, session):
        r = session.get("/api/dispositivos")
        assert r.status_code == 200
        data = r.json()
        # 1 lease DHCP + 1 estática de ARP
        assert data["total"] == 2
        ips = [d["ip"] for d in data["dispositivos"]]
        assert "192.168.5.22" in ips and "192.168.5.7" in ips
        kevin = next(d for d in data["dispositivos"]
                     if d["ip"] == "192.168.5.22")
        assert kevin["tipo"] == "DHCP"
        assert kevin["estado"] == "bound"

    def test_escaneo_con_filtro(self, session):
        r = session.get("/api/escaneo")
        assert r.status_code == 200
        assert r.json()["total"] == 2
        r = session.get("/api/escaneo", params={"filtro": "apple"})
        assert r.status_code == 200
        assert r.json()["total"] == 0


class TestSistema:

    def test_sistema(self, session):
        r = session.get("/api/sistema")
        assert r.status_code == 200
        data = r.json()
        assert data["name"] == "DUOTICS"
        assert data["cpu_load"] == 7
        assert data["used_mem"] == 24000000

    def test_interfaces(self, session):
        r = session.get("/api/interfaces")
        assert r.status_code == 200
        ifaces = {i["nombre"]: i for i in r.json()["interfaces"]}
        assert ifaces["ether1"]["tx_bytes"] == 100
        assert ifaces["bridge1"]["activa"] is True

    def test_validacion(self, session):
        r = session.get("/api/validacion")
        assert r.status_code == 200
        data = r.json()
        assert data["identidad"]["nombre"] == "DUOTICS"
        assert data["identidad"]["version"] == "6.49.19"
        assert data["qos"]["activo"] is False
        assert data["reloj"]["ntp_habilitado"] is True
        assert data["dispositivo_prioritario"]["lease"]["hostname"] == "kevin-pc"

    def test_config_sin_secretos(self, session):
        r = session.get("/api/config")
        assert r.status_code == 200
        texto = r.text.lower()
        assert "password" not in texto
        assert "hash" not in texto
        assert r.json()["router"]["host"]


class TestMonitoreo:

    def test_consumo(self, session):
        r = session.get("/api/consumo")
        assert r.status_code == 200
        data = r.json()
        assert data["conexiones_totales"] == 2
        # Ordenado por velocidad actual: Kevin primero
        assert data["dispositivos"][0]["ip"] == "192.168.5.22"
        assert data["dispositivos"][0]["dl_rate"] == 1000
        assert data["dispositivos"][0]["nombre"] == "kevin-pc"

    def test_consumo_orden_invalido_422(self, session):
        r = session.get("/api/consumo", params={"orden": "malo"})
        assert r.status_code == 422


class TestSesion:

    def test_sesion_sin_login(self, client):
        r = client.get("/api/auth/sesion")
        assert r.status_code == 200
        assert r.json() == {"autenticada": False}

    def test_sesion_con_login(self, session):
        r = session.get("/api/auth/sesion")
        assert r.json() == {"autenticada": True}


class TestHorario:

    def test_estado_completo(self, session):
        r = session.get("/api/horario")
        assert r.status_code == 200
        data = r.json()
        # La regla DROP del FakeAPI: 01:01 → 06:01 lun/mar (formato v6)
        assert data["corte"]["inicio"] == "01:01"
        assert data["corte"]["fin"] == "06:01"
        assert data["corte"]["dias"] == ["mon", "tue"]
        assert data["corte"]["paquetes_bloqueados"] == 10
        # Whitelist con la MAC de la regla ACCEPT, conectada según ARP? No:
        # AA:BB... no está en DHCP/ARP → en_red False, aplicada True
        wl = {w["mac"]: w for w in data["whitelist"]}
        assert wl["AA:BB:CC:11:22:33"]["aplicada_en_router"] is True
        assert wl["AA:BB:CC:11:22:33"]["en_red"] is False

    def test_sin_corte(self, session):
        session.fake_api.responses["/ip/firewall/filter/print"] = []
        r = session.get("/api/horario")
        assert r.status_code == 200
        data = r.json()
        assert data["corte"] is None
        assert data["en_curso"] is False


class TestMapeoErrores:

    @pytest.fixture()
    def _con_error(self, session):
        def romper(exc):
            def dep():
                raise exc
                yield  # pragma: no cover
            app.dependency_overrides[get_api] = dep
        yield romper
        # conftest restaura overrides al salir del fixture client

    def test_error_conexion_502(self, session, _con_error):
        _con_error(MikroTikConnectionError("login fallido"))
        r = session.get("/api/sistema")
        assert r.status_code == 502
        assert "router" in r.json()["detail"]
        assert "sugerencia" in r.json()

    def test_error_comando_400(self, session, _con_error):
        _con_error(MikroTikCommandError("!trap: invalid argument"))
        r = session.get("/api/sistema")
        assert r.status_code == 400
        assert "rechazó" in r.json()["detail"]

    def test_error_red_502(self, session, _con_error):
        _con_error(OSError("Network is unreachable"))
        r = session.get("/api/sistema")
        assert r.status_code == 502
