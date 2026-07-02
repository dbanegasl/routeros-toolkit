"""
test_app_config.py — Tests de lib/app_config.py y get_lan_prefix
=================================================================

Usa un directorio temporal vía MIKROTIK_CONFIG_DIR. No requiere router.
"""

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from lib.app_config import (load_json_config, save_json_config,
                            config_path, ConfigError)
from lib.mikrotik_api import get_lan_prefix, LAN_PREFIX


class TempConfigDirMixin:
    """Redirige config/ a un directorio temporal durante el test."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._patcher = mock.patch.dict(
            os.environ, {"MIKROTIK_CONFIG_DIR": self._tmp.name})
        self._patcher.start()
        os.environ.pop("MIKROTIK_LAN_PREFIX", None)

    def tearDown(self):
        self._patcher.stop()
        self._tmp.cleanup()


class TestJsonConfig(TempConfigDirMixin, unittest.TestCase):

    def test_archivo_inexistente_retorna_default(self):
        cfg = load_json_config("nada", default={"a": 1})
        self.assertEqual(cfg, {"a": 1})

    def test_sin_default_retorna_dict_vacio(self):
        self.assertEqual(load_json_config("nada"), {})

    def test_round_trip(self):
        data = {"dispositivos": [{"mac": "AA:BB:CC:DD:EE:FF",
                                  "nombre": "Cámara"}]}
        save_json_config("whitelist", data)
        self.assertEqual(load_json_config("whitelist"), data)

    def test_default_no_se_muta(self):
        default = {"a": 1}
        save_json_config("x", {"b": 2})
        load_json_config("x", default=default)
        self.assertEqual(default, {"a": 1})

    def test_merge_completa_claves_faltantes(self):
        """Archivos viejos sin claves nuevas se completan con el default."""
        save_json_config("qos", {"interfaz_wan": "ether5"})
        cfg = load_json_config("qos", default={"interfaz_wan": "ether1",
                                               "umbral_bulk_mb": 30})
        self.assertEqual(cfg["interfaz_wan"], "ether5")   # del archivo
        self.assertEqual(cfg["umbral_bulk_mb"], 30)       # del default

    def test_json_corrupto_lanza_config_error(self):
        path = config_path("roto")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{esto no es json", encoding="utf-8")
        with self.assertRaises(ConfigError) as ctx:
            load_json_config("roto")
        self.assertIn("JSON inválido", str(ctx.exception))

    def test_json_no_objeto_lanza_config_error(self):
        path = config_path("lista")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("[1, 2, 3]", encoding="utf-8")
        with self.assertRaises(ConfigError):
            load_json_config("lista")

    def test_utf8_preservado(self):
        save_json_config("acentos", {"nombre": "Cámara Ñoño 📷"})
        raw = config_path("acentos").read_text(encoding="utf-8")
        self.assertIn("Cámara Ñoño", raw)   # ensure_ascii=False


class FakeAPI:
    def __init__(self, addresses):
        self.addresses = addresses

    def command(self, cmd, params=None, queries=None):
        if cmd == "/ip/address/print":
            return self.addresses
        return []


class TestGetLanPrefix(unittest.TestCase):

    def setUp(self):
        os.environ.pop("MIKROTIK_LAN_PREFIX", None)

    def test_prefiere_interfaz_bridge(self):
        api = FakeAPI([
            {"address": "10.20.30.1/30", "interface": "ether1"},
            {"address": "192.168.5.1/24", "interface": "bridge1"},
        ])
        self.assertEqual(get_lan_prefix(api), "192.168.5.")

    def test_sin_bridge_usa_primera_privada(self):
        api = FakeAPI([
            {"address": "203.0.113.7/24", "interface": "ether1"},
            {"address": "192.168.88.1/24", "interface": "ether2"},
        ])
        self.assertEqual(get_lan_prefix(api), "192.168.88.")

    def test_sin_direcciones_usa_fallback(self):
        self.assertEqual(get_lan_prefix(FakeAPI([])), LAN_PREFIX)

    def test_error_de_api_usa_fallback(self):
        class BrokenAPI:
            def command(self, *a, **kw):
                raise RuntimeError("sin conexión")
        self.assertEqual(get_lan_prefix(BrokenAPI()), LAN_PREFIX)

    def test_override_por_variable_de_entorno(self):
        with mock.patch.dict(os.environ,
                             {"MIKROTIK_LAN_PREFIX": "10.0.0"}):
            self.assertEqual(get_lan_prefix(FakeAPI([])), "10.0.0.")


if __name__ == "__main__":
    unittest.main()
