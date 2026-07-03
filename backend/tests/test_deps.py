"""
test_deps.py — Conexión persistente compartida al router (get_api)
==================================================================

Pinea que el backend NO abre una conexión por petición (eso inundaba el
log del router con "logged in/out via api"): la conexión se reutiliza,
un !trap la deja viva y un error de red la resetea.
"""

import pytest

from backend.app import deps
from lib import MikroTikCommandError


class ConnFake:
    creadas: list = []

    def __init__(self, **kwargs):
        ConnFake.creadas.append(self)
        self.cerrada = False
        self.comandos = []

    def connect(self):
        pass

    def command(self, cmd, params=None, queries=None):
        self.comandos.append(cmd)
        return [{"name": "DUOTICS"}]

    def close(self):
        self.cerrada = True


@pytest.fixture()
def deps_limpias(monkeypatch):
    ConnFake.creadas = []
    monkeypatch.setattr(deps, "MikroTikAPI", ConnFake)
    monkeypatch.setattr(deps, "load_config", lambda: {})
    deps._api_compartida = None
    deps._ultimo_uso = 0.0
    yield
    deps._api_compartida = None
    deps._ultimo_uso = 0.0


def _peticion_ok():
    """Simula el ciclo completo de una petición exitosa."""
    gen = deps.get_api()
    api = next(gen)
    with pytest.raises(StopIteration):
        next(gen)
    return api


class TestConexionCompartida:

    def test_reutiliza_entre_peticiones(self, deps_limpias):
        a1 = _peticion_ok()
        a2 = _peticion_ok()
        assert a1 is a2
        assert len(ConnFake.creadas) == 1     # una sola conexión (un login)

    def test_trap_no_resetea_la_conexion(self, deps_limpias):
        gen = deps.get_api()
        api = next(gen)
        with pytest.raises(MikroTikCommandError):
            gen.throw(MikroTikCommandError("!trap"))
        assert not api.cerrada
        assert _peticion_ok() is api

    def test_error_de_red_resetea(self, deps_limpias):
        gen = deps.get_api()
        api = next(gen)
        with pytest.raises(OSError):
            gen.throw(OSError("conexión perdida"))
        assert api.cerrada
        # La siguiente petición reconecta
        assert _peticion_ok() is not api
        assert len(ConnFake.creadas) == 2

    def test_verificacion_tras_ocio(self, deps_limpias, monkeypatch):
        api = _peticion_ok()
        assert api.comandos == []
        # Simular que pasó más del umbral de ocio
        deps._ultimo_uso -= deps.VERIFICAR_TRAS_OCIO + 1
        assert _peticion_ok() is api
        # Se verificó con una lectura barata antes de reutilizar
        assert api.comandos == ["/system/identity/print"]

    def test_conexion_muerta_tras_ocio_reconecta(self, deps_limpias):
        api = _peticion_ok()
        deps._ultimo_uso -= deps.VERIFICAR_TRAS_OCIO + 1

        def morir(*a, **kw):
            raise OSError("router cerró la conexión")

        api.command = morir
        nueva = _peticion_ok()
        assert nueva is not api
        assert api.cerrada
        assert len(ConnFake.creadas) == 2
