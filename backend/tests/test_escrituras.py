"""
test_escrituras.py — Endpoints de escritura ⚠️ (bloqueos + horario)
===================================================================

Todas las escrituras exigen {"confirmar": true} y solo tocan reglas
etiquetadas propias. Incluye el ciclo completo crear → eliminar →
reprogramar con reaplicación automática de la lista blanca, usando una
FakeAPI con estado. No requiere router.
"""

import pytest

from backend.app.deps import get_api
from backend.app.main import app
from core.horario import load_whitelist


REGLA_AJENA = {".id": "*9", "chain": "forward", "action": "accept",
               "comment": "regla manual de Daniel"}


class TestBloqueos:

    def _con_bloqueo(self, session):
        session.fake_api.responses["/ip/firewall/filter/print"] = [
            {".id": "*5", "src-address": "192.168.5.30",
             "comment": "BLOQUEADO-POR-MENU-192.168.5.30"},
            REGLA_AJENA,
        ]

    def test_listar_solo_propias(self, session):
        self._con_bloqueo(session)
        r = session.get("/api/bloqueos")
        assert r.status_code == 200
        assert r.json()["total"] == 1
        assert r.json()["bloqueos"][0]["ip"] == "192.168.5.30"

    def test_bloquear_sin_confirmar_400_y_sin_escritura(self, session):
        r = session.post("/api/bloqueos", json={"ip": "192.168.5.40"})
        assert r.status_code == 400
        assert "confirmar" in r.json()["detail"]
        assert session.fake_api.writes == []

    def test_bloquear_ok(self, session):
        r = session.post("/api/bloqueos",
                         json={"ip": "192.168.5.40", "confirmar": True})
        assert r.status_code == 200
        cmd, params = session.fake_api.writes[0]
        assert cmd == "/ip/firewall/filter/add"
        assert "=src-address=192.168.5.40" in params
        assert "=comment=BLOQUEADO-POR-MENU-192.168.5.40" in params
        assert "=place-before=0" in params

    def test_bloquear_ip_invalida_400(self, session):
        r = session.post("/api/bloqueos",
                         json={"ip": "no-es-ip", "confirmar": True})
        assert r.status_code == 400
        assert session.fake_api.writes == []

    def test_bloquear_duplicada_409(self, session):
        self._con_bloqueo(session)
        r = session.post("/api/bloqueos",
                         json={"ip": "192.168.5.30", "confirmar": True})
        assert r.status_code == 409
        assert session.fake_api.writes == []

    def test_desbloquear_ok(self, session):
        self._con_bloqueo(session)
        r = session.request("DELETE", "/api/bloqueos/192.168.5.30",
                            json={"confirmar": True})
        assert r.status_code == 200
        assert session.fake_api.writes == [
            ("/ip/firewall/filter/remove", ["=.id=*5"])]

    def test_desbloquear_inexistente_404(self, session):
        r = session.request("DELETE", "/api/bloqueos/192.168.5.99",
                            json={"confirmar": True})
        assert r.status_code == 404

    def test_desbloquear_sin_confirmar_400(self, session):
        self._con_bloqueo(session)
        r = session.request("DELETE", "/api/bloqueos/192.168.5.30",
                            json={})
        assert r.status_code == 400
        assert session.fake_api.writes == []


class TestHorarioEscrituras:

    def test_crear_sin_confirmar_400(self, session):
        r = session.post("/api/horario",
                         json={"inicio": "01:00", "fin": "06:00"})
        assert r.status_code == 400
        assert session.fake_api.writes == []

    def test_hora_invalida_400(self, session):
        for mala in ("25:00", "1:99", "0100", ""):
            r = session.post("/api/horario", json={
                "inicio": mala, "fin": "06:00", "confirmar": True})
            assert r.status_code in (400, 422), mala

    def test_dias_invalidos_400(self, session):
        r = session.post("/api/horario", json={
            "inicio": "01:00", "fin": "06:00",
            "dias": ["lunes"], "confirmar": True})
        assert r.status_code == 400

    def test_crear_conserva_whitelist_y_ordena_reglas(self, session):
        # La FakeAPI tiene un corte previo (*1) y una ACCEPT (*2, AA:BB…)
        session.fake_api.responses["/ip/route/print"] = [
            {"dst-address": "0.0.0.0/0", "active": "true",
             "interface": "ether1"}]
        r = session.post("/api/horario", json={
            "inicio": "22:00", "fin": "06:30",
            "dias": ["fri", "sat"], "confirmar": True})
        assert r.status_code == 200
        assert r.json()["whitelist_aplicada"] == 1

        writes = session.fake_api.writes
        # 1º: se eliminan las reglas propias previas (*1 DROP, *2 ACCEPT)
        assert writes[0] == ("/ip/firewall/filter/remove", ["=.id=*1"])
        assert writes[1] == ("/ip/firewall/filter/remove", ["=.id=*2"])
        # 2º: ACCEPT de la whitelist conservada, 3º: DROP con el horario
        assert "=comment=HORARIO-PERMITIDO-AA:BB:CC:11:22:33" in writes[2][1]
        drop_params = writes[3][1]
        assert "=action=drop" in drop_params
        assert "=time=22:00:00-06:30:00,fri,sat" in drop_params

    def test_eliminar_solo_reglas_propias(self, session):
        session.fake_api.responses["/ip/firewall/filter/print"].append(
            REGLA_AJENA)
        r = session.request("DELETE", "/api/horario",
                            json={"confirmar": True})
        assert r.status_code == 200
        assert r.json()["reglas_eliminadas"] == 2
        ids = [p[0] for _, p in session.fake_api.writes]
        assert ids == ["=.id=*1", "=.id=*2"]      # *9 ajena intacta

    def test_whitelist_put_mac_invalida_400(self, session):
        r = session.put("/api/horario/whitelist", json={
            "macs": ["ZZ:no:va"], "confirmar": True})
        assert r.status_code == 400

    def test_whitelist_put_persiste_archivo(self, session):
        r = session.put("/api/horario/whitelist", json={
            "macs": ["aa:bb:cc:11:22:33", "F0:2F:74:CB:97:3F"],
            "confirmar": True})
        assert r.status_code == 200
        stored = load_whitelist()
        assert set(stored) == {"AA:BB:CC:11:22:33", "F0:2F:74:CB:97:3F"}
        # Nombre resuelto desde la red (lease de kevin-pc)
        assert stored["F0:2F:74:CB:97:3F"]["nombre"] == "kevin-pc"

    def test_whitelist_get(self, session):
        r = session.get("/api/horario/whitelist")
        assert r.status_code == 200
        macs = {d["mac"] for d in r.json()["dispositivos"]}
        assert "AA:BB:CC:11:22:33" in macs       # de la regla aplicada


# ---------------------------------------------------------------------------
# Ciclo completo con estado: crear → eliminar → reprogramar
# (el pendiente histórico: la whitelist debe reaplicarse sola)
# ---------------------------------------------------------------------------

class StatefulFakeAPI:
    """FakeAPI cuyo firewall filter SÍ cambia con add/remove."""

    def __init__(self, base_responses: dict):
        self.responses = dict(base_responses)
        self.filtros: list = []
        self._next_id = 10

    def command(self, cmd, params=None, queries=None):
        if cmd == "/ip/firewall/filter/print":
            return list(self.filtros)
        if cmd == "/ip/firewall/filter/add":
            regla = {".id": f"*{self._next_id}"}
            self._next_id += 1
            for p in params:
                clave, _, valor = p.lstrip("=").partition("=")
                regla[clave] = valor
            self.filtros.append(regla)
            return []
        if cmd == "/ip/firewall/filter/remove":
            rid = params[0].split("=")[-1]
            self.filtros = [f for f in self.filtros if f[".id"] != rid]
            return []
        return self.responses.get(cmd, [])

    def connect(self):
        pass

    def close(self):
        pass


@pytest.fixture()
def sesion_stateful(session):
    """Reemplaza la FakeAPI del cliente por una con estado."""
    from backend.tests.conftest import make_fake_api
    stateful = StatefulFakeAPI(make_fake_api().responses)
    stateful.responses["/ip/route/print"] = [
        {"dst-address": "0.0.0.0/0", "active": "true", "interface": "ether1"}]
    app.dependency_overrides[get_api] = lambda: stateful
    session.stateful = stateful
    return session


class TestCicloCompleto:

    def test_crear_eliminar_reprogramar_reaplica_whitelist(self, sesion_stateful):
        s = sesion_stateful

        # 1. Armar la lista blanca (sin corte aún)
        r = s.put("/api/horario/whitelist", json={
            "macs": ["F0:2F:74:CB:97:3F"], "confirmar": True})
        assert r.status_code == 200

        # 2. Crear el corte → ACCEPT + DROP en el router
        r = s.post("/api/horario", json={
            "inicio": "01:00", "fin": "06:00", "confirmar": True})
        assert r.status_code == 200
        comentarios = [f.get("comment", "") for f in s.stateful.filtros]
        assert "HORARIO-PERMITIDO-F0:2F:74:CB:97:3F" in comentarios
        assert "HORARIO-INTERNET" in comentarios

        # 3. Eliminar el corte → router limpio, archivo intacto
        r = s.request("DELETE", "/api/horario", json={"confirmar": True})
        assert r.status_code == 200
        assert r.json()["whitelist_guardada"] == 1
        assert s.stateful.filtros == []
        assert set(load_whitelist()) == {"F0:2F:74:CB:97:3F"}

        # 4. Reprogramar → la whitelist vuelve sola desde el archivo
        r = s.post("/api/horario", json={
            "inicio": "22:00", "fin": "05:00", "dias": ["sun"],
            "confirmar": True})
        assert r.status_code == 200
        assert r.json()["whitelist_aplicada"] == 1
        comentarios = [f.get("comment", "") for f in s.stateful.filtros]
        assert "HORARIO-PERMITIDO-F0:2F:74:CB:97:3F" in comentarios
        assert "HORARIO-INTERNET" in comentarios
        # Y el orden correcto: ACCEPT antes que DROP
        assert (comentarios.index("HORARIO-PERMITIDO-F0:2F:74:CB:97:3F")
                < comentarios.index("HORARIO-INTERNET"))
