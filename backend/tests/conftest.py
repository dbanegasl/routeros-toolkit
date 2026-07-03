"""
conftest.py — Fixtures del backend: app con FakeAPI y sesión iniciada
=====================================================================

El router se simula con el mismo patrón FakeAPI de tests/ (respuestas
predefinidas por comando); se inyecta con dependency_overrides. Ningún
test toca el router real.
"""

import sys
from pathlib import Path

import pytest

# Repo raíz en sys.path (backend/, lib/ y core/ importables)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from fastapi.testclient import TestClient      # noqa: E402

from backend.app import auth, deps as deps_mod, ws as ws_mod  # noqa: E402
from backend.app.deps import get_api           # noqa: E402
from backend.app.main import app               # noqa: E402

PASSWORD_TEST = "clave-de-prueba"


class FakeAPI:
    """Simula MikroTikAPI.command() con respuestas predefinidas."""

    def __init__(self, responses: dict = None):
        self.responses = responses or {}
        self.writes = []
        self.cerrada = False

    def command(self, cmd, params=None, queries=None):
        if params:
            self.writes.append((cmd, params))
        return self.responses.get(cmd, [])

    def connect(self):
        pass

    def close(self):
        self.cerrada = True


def make_fake_api():
    """Router simulado con datos coherentes para todos los endpoints."""
    return FakeAPI({
        "/system/identity/print": [{"name": "DUOTICS"}],
        "/system/resource/print": [{
            "uptime": "1w2d", "version": "6.49.19", "board-name": "hEX lite",
            "architecture-name": "smips", "cpu-count": "1", "cpu-load": "7",
            "free-memory": "40000000", "total-memory": "64000000",
            "free-hdd-space": "10000000", "total-hdd-space": "16000000",
        }],
        "/system/clock/print": [{"date": "jul/02/2026", "time": "10:15:30"}],
        "/interface/print": [
            {"name": "ether1", "type": "ether", "running": "true",
             "mtu": "1500", "tx-byte": "100", "rx-byte": "200"},
            {"name": "bridge1", "type": "bridge", "running": "true",
             "mtu": "1500", "tx-byte": "300", "rx-byte": "400"},
        ],
        "/ip/address/print": [
            {"address": "192.168.5.1/24", "interface": "bridge1"},
        ],
        "/ip/arp/print": [
            {"address": "192.168.5.7", "mac-address": "3C:7C:3F:2D:7A:4D"},
        ],
        "/interface/bridge/host/print": [
            {"mac-address": "AA:BB:CC:11:22:33", "interface": "ether3",
             "local": "false"},
        ],
        "/ip/dhcp-server/lease/print": [
            {"address": "192.168.5.22", "mac-address": "F0:2F:74:CB:97:3F",
             "host-name": "kevin-pc", "status": "bound"},
        ],
        "/ip/firewall/filter/print": [
            {".id": "*1", "chain": "forward", "action": "drop",
             "comment": "HORARIO-INTERNET", "time": "1h1m-6h1m,mon,tue",
             "out-interface": "ether1", "packets": "10", "bytes": "1000"},
            {".id": "*2", "chain": "forward", "action": "accept",
             "comment": "HORARIO-PERMITIDO-AA:BB:CC:11:22:33",
             "src-mac-address": "AA:BB:CC:11:22:33", "bytes": "500"},
        ],
        "/ip/firewall/connection/print": [
            {"src-address": "192.168.5.22:5000", "repl-rate": "1000",
             "orig-rate": "100", "repl-bytes": "2000", "orig-bytes": "200"},
            {"src-address": "192.168.5.7:80", "repl-rate": "50",
             "orig-rate": "5", "repl-bytes": "10", "orig-bytes": "1"},
        ],
        "/ip/firewall/mangle/print": [],
        "/queue/tree/print": [],
        "/queue/simple/print": [],
        "/system/ntp/client/print": [{"enabled": "true"}],
    })


def _reset_ws():
    """Estado limpio de los muestreadores WS y la conexión compartida."""
    for m in (ws_mod.muestreador_monitor, ws_mod.muestreador_log):
        m.clientes.clear()
        m._tarea = None
    ws_mod._EstadoMonitor.nombres = {}
    ws_mod._EstadoMonitor.nombres_ts = 0.0
    ws_mod._EstadoMonitor.ifaces_prev = {}
    ws_mod._EstadoMonitor.ifaces_prev_ts = 0.0
    deps_mod._api_compartida = None
    deps_mod._ultimo_uso = 0.0


@pytest.fixture()
def client(monkeypatch, tmp_path):
    """TestClient con FakeAPI inyectada, hash de prueba y estado limpio."""
    monkeypatch.setenv("APP_PASSWORD_HASH", auth.generar_hash(PASSWORD_TEST))
    # config/ vacío y aislado: sin qos.json ni whitelist.json reales
    monkeypatch.setenv("MIKROTIK_CONFIG_DIR", str(tmp_path))
    monkeypatch.setenv("APP_WS_INTERVALO", "0.05")
    auth.limpiar_estado()
    _reset_ws()

    fake = make_fake_api()
    app.dependency_overrides[get_api] = lambda: fake
    # La conexión compartida de deps (usada por el muestreo WS) también
    # debe ser la FakeAPI; se cuentan las "conexiones" abiertas.
    conexiones = []

    def crear_fake(**kwargs):
        conexiones.append(1)
        return fake

    monkeypatch.setattr(deps_mod, "MikroTikAPI", crear_fake)
    monkeypatch.setattr(deps_mod, "load_config", lambda: {})
    with TestClient(app) as c:
        c.fake_api = fake
        c.ws_conexiones = conexiones
        yield c
    app.dependency_overrides.clear()
    auth.limpiar_estado()
    _reset_ws()


@pytest.fixture()
def session(client):
    """Cliente ya autenticado (cookie de sesión puesta)."""
    r = client.post("/api/auth/login", json={"password": PASSWORD_TEST})
    assert r.status_code == 200
    return client
