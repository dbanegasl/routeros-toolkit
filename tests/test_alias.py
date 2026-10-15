"""
test_alias.py — Tests de los alias de dispositivos (config/alias.json)
======================================================================

load_aliases / set_alias, prioridad del alias en resolve_device_name y
su propagación a build_device_map e inventario_dispositivos. Usa un
directorio temporal vía MIKROTIK_CONFIG_DIR. No requiere router.
"""

import json
import os
import tempfile
import unittest
from unittest import mock

from lib.app_config import (load_aliases, set_alias, config_path,
                            ConfigError, ALIAS_MAX)
from lib.mikrotik_api import resolve_device_name, build_device_map
from core.dispositivos import inventario_dispositivos

KEVIN = "F0:2F:74:CB:97:3F"


class FakeAPI:
    def __init__(self, responses: dict):
        self.responses = responses

    def command(self, cmd, params=None, queries=None):
        return self.responses.get(cmd, [])


def make_fake_api():
    return FakeAPI({
        "/ip/address/print": [{"address": "192.168.5.1/24",
                               "interface": "bridge1"}],
        "/ip/dhcp-server/lease/print": [
            {"address": "192.168.5.22", "mac-address": KEVIN,
             "host-name": "kevin-pc", "status": "bound"},
        ],
        "/ip/arp/print": [
            {"address": "192.168.5.7", "mac-address": "3C:7C:3F:2D:7A:4D"},
        ],
    })


class _ConConfigTemporal(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._env = mock.patch.dict(
            os.environ, {"MIKROTIK_CONFIG_DIR": self._tmp.name})
        self._env.start()

    def tearDown(self):
        self._env.stop()
        self._tmp.cleanup()


class TestAliasStorage(_ConConfigTemporal):

    def test_sin_archivo_no_hay_alias(self):
        self.assertEqual(load_aliases(), {})

    def test_guardar_normaliza_mac_y_espacios(self):
        set_alias(KEVIN.lower(), "  PC   de\nKevin ")
        self.assertEqual(load_aliases(), {KEVIN: "PC de Kevin"})

    def test_alias_vacio_lo_quita(self):
        set_alias(KEVIN, "PC de Kevin")
        set_alias(KEVIN, "   ")
        self.assertEqual(load_aliases(), {})

    def test_archivo_ordenado_por_mac(self):
        set_alias("FF:00:00:00:00:01", "Z")
        set_alias("00:00:00:00:00:01", "A")
        with open(config_path("alias"), encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(list(data["alias"]),
                         ["00:00:00:00:00:01", "FF:00:00:00:00:01"])

    def test_mac_invalida(self):
        with self.assertRaises(ValueError):
            set_alias("no-es-mac", "x")

    def test_alias_demasiado_largo(self):
        with self.assertRaises(ValueError):
            set_alias(KEVIN, "x" * (ALIAS_MAX + 1))
        self.assertEqual(load_aliases(), {})

    def test_formato_corrupto(self):
        with open(config_path("alias"), "w", encoding="utf-8") as f:
            json.dump({"alias": ["no", "es", "objeto"]}, f)
        with self.assertRaises(ConfigError):
            load_aliases()


class TestAliasEnNombres(_ConConfigTemporal):

    def test_alias_gana_al_hostname(self):
        set_alias(KEVIN, "PC de Kevin")
        self.assertEqual(
            resolve_device_name("192.168.5.22", KEVIN, "kevin-pc"),
            "PC de Kevin")

    def test_alias_sin_sufijo_estatica(self):
        set_alias(KEVIN, "PC de Kevin")
        self.assertEqual(
            resolve_device_name("192.168.5.22", KEVIN, "", is_static=True),
            "PC de Kevin")

    def test_mapa_vacio_ignora_alias(self):
        set_alias(KEVIN, "PC de Kevin")
        self.assertEqual(
            resolve_device_name("192.168.5.22", KEVIN, "kevin-pc",
                                aliases={}),
            "kevin-pc")

    def test_build_device_map(self):
        set_alias(KEVIN, "PC de Kevin")
        d = build_device_map(make_fake_api(), by="mac")
        self.assertEqual(d[KEVIN]["name"], "PC de Kevin")
        self.assertEqual(d[KEVIN]["detected_name"], "kevin-pc")
        self.assertEqual(d[KEVIN]["alias"], "PC de Kevin")
        self.assertEqual(d["3C:7C:3F:2D:7A:4D"]["alias"], "")

    def test_inventario(self):
        set_alias(KEVIN, "PC de Kevin")
        api = make_fake_api()
        api.responses["/interface/bridge/host/print"] = []
        filas = {f["mac"]: f for f in inventario_dispositivos(api)}
        self.assertEqual(filas[KEVIN]["nombre"], "PC de Kevin")
        self.assertEqual(filas[KEVIN]["nombre_detectado"], "kevin-pc")
        self.assertEqual(filas[KEVIN]["alias"], "PC de Kevin")
        self.assertEqual(filas["3C:7C:3F:2D:7A:4D"]["alias"], "")


if __name__ == "__main__":
    unittest.main()
