"""
test_device_map.py — Tests de build_device_map / build_name_map
================================================================

Usa una API falsa que responde con leases DHCP y entradas ARP
predefinidas. No requiere router.
"""

import unittest

from lib.mikrotik_api import build_device_map, build_name_map


class FakeAPI:
    """Simula MikroTikAPI.command() con respuestas predefinidas."""

    def __init__(self, responses: dict):
        self.responses = responses

    def command(self, cmd, params=None, queries=None):
        return self.responses.get(cmd, [])


def make_fake_api():
    return FakeAPI({
        "/ip/dhcp-server/lease/print": [
            {"address": "192.168.5.10", "mac-address": "F0:2F:74:CB:97:3F",
             "host-name": "PC-Kevin", "status": "bound"},
            {"address": "192.168.5.11", "mac-address": "8C:2A:85:11:22:33",
             "host-name": "", "status": "bound"},
        ],
        "/ip/arp/print": [
            # Ya está en DHCP → no debe duplicarse ni marcarse estática
            {"address": "192.168.5.10", "mac-address": "F0:2F:74:CB:97:3F"},
            # Solo en ARP → estática
            {"address": "192.168.5.50", "mac-address": "DC:62:79:AA:BB:CC"},
            # Fuera de la LAN → se ignora
            {"address": "10.99.99.1", "mac-address": "00:11:22:33:44:55"},
        ],
    })


class TestBuildDeviceMap(unittest.TestCase):

    def test_combina_dhcp_y_arp(self):
        devices = build_device_map(make_fake_api())
        self.assertEqual(set(devices),
                         {"192.168.5.10", "192.168.5.11", "192.168.5.50"})

    def test_dhcp_no_es_estatica(self):
        devices = build_device_map(make_fake_api())
        self.assertFalse(devices["192.168.5.10"]["static"])
        self.assertEqual(devices["192.168.5.10"]["hostname"], "PC-Kevin")

    def test_solo_arp_es_estatica(self):
        devices = build_device_map(make_fake_api())
        self.assertTrue(devices["192.168.5.50"]["static"])
        self.assertIn("[estática]", devices["192.168.5.50"]["name"])

    def test_ip_fuera_de_lan_se_ignora(self):
        devices = build_device_map(make_fake_api())
        self.assertNotIn("10.99.99.1", devices)

    def test_indexado_por_mac(self):
        devices = build_device_map(make_fake_api(), by="mac")
        self.assertIn("F0:2F:74:CB:97:3F", devices)
        self.assertIn("DC:62:79:AA:BB:CC", devices)
        self.assertEqual(devices["F0:2F:74:CB:97:3F"]["ip"], "192.168.5.10")
        # Todas las claves en mayúsculas
        for key in devices:
            self.assertEqual(key, key.upper())

    def test_por_mac_descarta_entradas_sin_mac(self):
        api = FakeAPI({
            "/ip/dhcp-server/lease/print": [
                {"address": "192.168.5.60", "mac-address": "",
                 "host-name": "fantasma"},
            ],
            "/ip/arp/print": [],
        })
        self.assertEqual(build_device_map(api, by="mac"), {})


class TestBuildNameMap(unittest.TestCase):

    def test_mapa_ip_a_nombre(self):
        names = build_name_map(make_fake_api())
        self.assertEqual(names["192.168.5.10"], "PC-Kevin")
        # Sin hostname → vendor de la base OUI local (8C:2A:85 = Amazon)
        self.assertIn("Amazon", names["192.168.5.11"])


if __name__ == "__main__":
    unittest.main()
