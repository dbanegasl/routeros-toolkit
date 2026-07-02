"""
test_utils.py — Tests de las utilidades puras de lib/mikrotik_api.py
=====================================================================

fmt_speed, fmt_bytes, is_random_mac, resolve_device_name y load_config.
No requiere router.
"""

import os
import tempfile
import unittest
from unittest import mock

from lib.mikrotik_api import (fmt_speed, fmt_bytes, is_random_mac,
                              resolve_device_name, load_config)


# ---------------------------------------------------------------------------
# Formateo de velocidades y bytes
# ---------------------------------------------------------------------------

class TestFmtSpeed(unittest.TestCase):

    def test_bps(self):
        self.assertEqual(fmt_speed(0), "0 bps")
        self.assertEqual(fmt_speed(999), "999 bps")

    def test_kbps(self):
        self.assertEqual(fmt_speed(1_000), "1.0 Kbps")
        self.assertEqual(fmt_speed(999_999), "1000.0 Kbps")

    def test_mbps(self):
        self.assertEqual(fmt_speed(1_000_000), "1.00 Mbps")
        self.assertEqual(fmt_speed(87_500_000), "87.50 Mbps")


class TestFmtBytes(unittest.TestCase):

    def test_bytes(self):
        self.assertEqual(fmt_bytes(0), "0 B")
        self.assertEqual(fmt_bytes(1023), "1023 B")

    def test_kb(self):
        self.assertEqual(fmt_bytes(1024), "1.0 KB")
        self.assertEqual(fmt_bytes(1536), "1.5 KB")

    def test_mb(self):
        self.assertEqual(fmt_bytes(1_048_576), "1.00 MB")

    def test_gb(self):
        self.assertEqual(fmt_bytes(1_073_741_824), "1.00 GB")
        self.assertEqual(fmt_bytes(5 * 1_073_741_824), "5.00 GB")


# ---------------------------------------------------------------------------
# Detección de MACs aleatorias (localmente administradas)
# ---------------------------------------------------------------------------

class TestIsRandomMac(unittest.TestCase):

    def test_mac_universal_no_es_aleatoria(self):
        # 0xF0 = 11110000 → bit 1 apagado
        self.assertFalse(is_random_mac("F0:2F:74:CB:97:3F"))
        self.assertFalse(is_random_mac("00:1E:C2:AA:BB:CC"))

    def test_mac_local_es_aleatoria(self):
        # Segundo dígito hex en {2, 6, A, E} → bit 1 encendido
        self.assertTrue(is_random_mac("92:AB:CD:EF:01:23"))   # 0x92
        self.assertTrue(is_random_mac("A6:00:11:22:33:44"))   # 0xA6
        self.assertTrue(is_random_mac("3A:F9:EE:00:00:01"))   # 0x3A
        self.assertTrue(is_random_mac("DE:AD:BE:EF:00:01"))   # 0xDE

    def test_separador_con_guiones(self):
        self.assertTrue(is_random_mac("92-AB-CD-EF-01-23"))
        self.assertFalse(is_random_mac("F0-2F-74-CB-97-3F"))

    def test_entradas_invalidas(self):
        self.assertFalse(is_random_mac(""))
        self.assertFalse(is_random_mac("Z"))
        self.assertFalse(is_random_mac("ZZ:XX:YY:00:00:00"))


# ---------------------------------------------------------------------------
# Resolución de nombres de dispositivos
# ---------------------------------------------------------------------------

class TestResolveDeviceName(unittest.TestCase):

    def test_hostname_tiene_prioridad(self):
        name = resolve_device_name("192.168.5.10", "F0:2F:74:CB:97:3F",
                                   "PC-Kevin")
        self.assertEqual(name, "PC-Kevin")

    def test_hostname_generico_se_ignora(self):
        """Nombres como 'wlan0' no aportan — cae al vendor de la MAC."""
        name = resolve_device_name("192.168.5.10", "F0:2F:74:CB:97:3F",
                                   "wlan0")
        # F0:2F:74 está en la base OUI local como ASUSTeK
        self.assertIn("ASUSTeK", name)
        self.assertIn(":97:3F", name)   # últimos 5 caracteres de la MAC

    def test_sin_hostname_usa_vendor(self):
        name = resolve_device_name("192.168.5.30", "F0:2F:74:AA:BB:CC", "")
        self.assertIn("ASUSTeK", name)

    def test_mac_aleatoria_sin_hostname(self):
        name = resolve_device_name("192.168.5.40", "92:12:34:56:78:9A", "")
        self.assertIn("MAC privada", name)

    def test_sin_vendor_ni_hostname_retorna_mac(self):
        mac = "F1:23:45:67:89:AB"   # OUI que no está en la base local
        name = resolve_device_name("192.168.5.50", mac, "")
        self.assertEqual(name, mac)

    def test_sin_datos_retorna_ip(self):
        name = resolve_device_name("192.168.5.60", "", "")
        self.assertEqual(name, "192.168.5.60")

    def test_sufijo_estatica(self):
        name = resolve_device_name("192.168.5.22", "", "Servidor",
                                   is_static=True)
        self.assertEqual(name, "Servidor [estática]")


# ---------------------------------------------------------------------------
# Carga de configuración
# ---------------------------------------------------------------------------

ENV_KEYS = ["MIKROTIK_HOST", "MIKROTIK_PORT", "MIKROTIK_USER",
            "MIKROTIK_PASSWORD", "MIKROTIK_ENV_FILE"]


class TestLoadConfig(unittest.TestCase):

    def setUp(self):
        # Aísla los tests de las variables reales del sistema
        self._patcher = mock.patch.dict(os.environ, {}, clear=False)
        self._patcher.start()
        for k in ENV_KEYS:
            os.environ.pop(k, None)

    def tearDown(self):
        self._patcher.stop()

    def _write_env(self, content: str) -> str:
        f = tempfile.NamedTemporaryFile(mode="w", suffix=".env",
                                        delete=False)
        f.write(content)
        f.close()
        self.addCleanup(os.unlink, f.name)
        return f.name

    def test_archivo_explicito(self):
        path = self._write_env(
            "MIKROTIK_HOST=10.0.0.1\n"
            "MIKROTIK_PORT=9999\n"
            "MIKROTIK_USER=lectura\n"
            "MIKROTIK_PASSWORD=clave123\n")
        cfg = load_config(path)
        self.assertEqual(cfg["host"], "10.0.0.1")
        self.assertEqual(cfg["port"], 9999)
        self.assertIsInstance(cfg["port"], int)
        self.assertEqual(cfg["username"], "lectura")
        self.assertEqual(cfg["password"], "clave123")

    def test_comentarios_y_lineas_vacias(self):
        path = self._write_env(
            "# comentario\n"
            "\n"
            "MIKROTIK_HOST=10.0.0.2\n")
        cfg = load_config(path)
        self.assertEqual(cfg["host"], "10.0.0.2")

    def test_defaults_para_claves_faltantes(self):
        path = self._write_env("MIKROTIK_HOST=10.0.0.3\n")
        cfg = load_config(path)
        self.assertEqual(cfg["port"], 8728)
        self.assertEqual(cfg["username"], "admin")
        self.assertEqual(cfg["password"], "")

    def test_variable_de_entorno_sobreescribe_archivo(self):
        path = self._write_env(
            "MIKROTIK_HOST=10.0.0.4\n"
            "MIKROTIK_PASSWORD=del_archivo\n")
        os.environ["MIKROTIK_PASSWORD"] = "del_entorno"
        cfg = load_config(path)
        self.assertEqual(cfg["host"], "10.0.0.4")
        self.assertEqual(cfg["password"], "del_entorno")

    def test_mikrotik_env_file(self):
        path = self._write_env("MIKROTIK_HOST=10.0.0.5\n")
        os.environ["MIKROTIK_ENV_FILE"] = path
        cfg = load_config()
        self.assertEqual(cfg["host"], "10.0.0.5")

    def test_valores_con_espacios(self):
        path = self._write_env("MIKROTIK_HOST = 10.0.0.6 \n")
        cfg = load_config(path)
        self.assertEqual(cfg["host"], "10.0.0.6")


if __name__ == "__main__":
    unittest.main()
