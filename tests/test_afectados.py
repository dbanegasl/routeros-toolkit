"""
test_afectados.py — Dispositivos afectados por el corte de internet
===================================================================

duracion_a_segundos, intentos_recientes (address-list HORARIO-INTENTOS)
y dispositivos_afectados. config/ aislado vía MIKROTIK_CONFIG_DIR (los
nombres pasan por los alias). No requiere router.
"""

import os
import tempfile
import unittest
from unittest import mock

from core.horario import (duracion_a_segundos, intentos_recientes,
                          dispositivos_afectados, TRY_LIST, TRY_TIMEOUT_S)

WL = "D8:5E:D3:83:0A:D2"


class FakeAPI:
    def __init__(self, responses: dict):
        self.responses = responses

    def command(self, cmd, params=None, queries=None):
        return self.responses.get(cmd, [])


def make_fake_api(intentos=None):
    return FakeAPI({
        "/ip/address/print": [{"address": "192.168.5.1/24",
                               "interface": "bridge1"}],
        "/ip/dhcp-server/lease/print": [
            {"address": "192.168.5.48", "mac-address": "3A:F9:EE:40:2D:C3",
             "host-name": "Infinix", "status": "bound"},
            {"address": "192.168.5.66", "mac-address": "22:AE:16:5C:8D:B9",
             "host-name": "POCO", "status": "bound"},
            # Lease reservada pero el equipo no está → no es afectado
            {"address": "192.168.5.22", "mac-address": "F0:2F:74:CB:97:3F",
             "host-name": "", "status": "waiting"},
            # En lista blanca → no es afectado
            {"address": "192.168.5.21", "mac-address": WL,
             "host-name": "PC-BEAST", "status": "bound"},
        ],
        "/ip/arp/print": [
            # Estática viva → afectada
            {"address": "192.168.5.20", "mac-address": "00:90:A9:44:C2:62",
             "status": "stale"},
            # Estática que ya no responde → no
            {"address": "192.168.5.88", "mac-address": "58:05:D9:60:A3:3E",
             "status": "failed"},
        ],
        "/ip/firewall/address-list/print": intentos or [],
    })


class TestDuracion(unittest.TestCase):

    def test_formatos(self):
        self.assertEqual(duracion_a_segundos("9m41s"), 581)
        self.assertEqual(duracion_a_segundos("1h2m"), 3720)
        self.assertEqual(duracion_a_segundos("10m"), 600)
        self.assertEqual(duracion_a_segundos("00:09:41"), 581)

    def test_milisegundos_v7_se_ignoran(self):
        self.assertEqual(duracion_a_segundos("41s870ms"), 41)

    def test_no_reconocida(self):
        for v in ("", "abc", "5x", None):
            self.assertIsNone(duracion_a_segundos(v), v)


class _ConConfigTemporal(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._env = mock.patch.dict(
            os.environ, {"MIKROTIK_CONFIG_DIR": self._tmp.name})
        self._env.start()

    def tearDown(self):
        self._env.stop()
        self._tmp.cleanup()


class TestAfectados(_ConConfigTemporal):

    def test_intentos_recientes(self):
        api = make_fake_api([
            {"list": TRY_LIST, "address": "192.168.5.48", "timeout": "9m20s"},
            {"list": TRY_LIST, "address": "192.168.5.66", "timeout": "raro"},
        ])
        self.assertEqual(intentos_recientes(api), {"192.168.5.48": 40})

    def test_solo_conectados_fuera_de_whitelist(self):
        ips = [a["ip"] for a in dispositivos_afectados(make_fake_api(), [WL])]
        self.assertEqual(ips, ["192.168.5.20", "192.168.5.48", "192.168.5.66"])

    def test_whitelist_insensible_a_mayusculas(self):
        ips = [a["ip"] for a in
               dispositivos_afectados(make_fake_api(), [WL.lower()])]
        self.assertNotIn("192.168.5.21", ips)

    def test_los_que_intentan_van_primero(self):
        api = make_fake_api([
            {"list": TRY_LIST, "address": "192.168.5.66", "timeout": "8m"},
            {"list": TRY_LIST, "address": "192.168.5.48", "timeout": "9m50s"},
        ])
        filas = dispositivos_afectados(api, [WL])
        self.assertEqual([(f["ip"], f["intento_hace_s"]) for f in filas], [
            ("192.168.5.48", 10),
            ("192.168.5.66", TRY_TIMEOUT_S - 480),
            ("192.168.5.20", None),
        ])

    def test_campos(self):
        fila = dispositivos_afectados(make_fake_api(), [WL])[1]
        self.assertEqual(fila, {
            "ip": "192.168.5.48", "mac": "3A:F9:EE:40:2D:C3",
            "nombre": "Infinix", "nombre_detectado": "Infinix", "alias": "",
            "intento_hace_s": None,
        })


if __name__ == "__main__":
    unittest.main()
