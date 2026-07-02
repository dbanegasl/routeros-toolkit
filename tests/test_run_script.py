"""
test_run_script.py — Tests del manejo de errores estándar (run_script)
=======================================================================

Verifica mensajes limpios y exit codes por tipo de excepción.
No requiere router.
"""

import io
import socket
import unittest
from contextlib import redirect_stdout

from lib.mikrotik_api import (run_script, MikroTikConnectionError,
                              MikroTikCommandError)
from lib.app_config import ConfigError


def run_and_capture(exc):
    """Ejecuta run_script con un main que lanza `exc`; retorna (código, salida)."""
    def failing_main():
        raise exc

    buf = io.StringIO()
    try:
        with redirect_stdout(buf):
            run_script(failing_main)
    except SystemExit as e:
        return e.code, buf.getvalue()
    return 0, buf.getvalue()


class TestRunScript(unittest.TestCase):

    def test_exito_no_termina_el_proceso(self):
        llamado = []
        run_script(lambda: llamado.append(True))
        self.assertTrue(llamado)

    def test_login_fallido_exit_1(self):
        code, out = run_and_capture(
            MikroTikConnectionError("Login fallido: !trap"))
        self.assertEqual(code, 1)
        self.assertIn("iniciar sesión", out)
        self.assertIn("config.env", out)
        self.assertNotIn("Traceback", out)

    def test_conexion_rechazada_exit_1(self):
        code, out = run_and_capture(ConnectionRefusedError())
        self.assertEqual(code, 1)
        self.assertIn("rechazó la conexión", out)
        self.assertIn("/ip service enable api", out)

    def test_timeout_exit_1(self):
        code, out = run_and_capture(socket.timeout())
        self.assertEqual(code, 1)
        self.assertIn("Tiempo de espera", out)
        self.assertIn("MIKROTIK_TIMEOUT", out)

    def test_error_de_red_exit_1(self):
        code, out = run_and_capture(OSError(113, "No route to host"))
        self.assertEqual(code, 1)
        self.assertIn("Error de red", out)

    def test_trap_de_routeros_exit_2(self):
        code, out = run_and_capture(
            MikroTikCommandError("RouterOS error: no such item"))
        self.assertEqual(code, 2)
        self.assertIn("no such item", out)

    def test_config_error_exit_2(self):
        code, out = run_and_capture(ConfigError("JSON inválido en qos.json"))
        self.assertEqual(code, 2)
        self.assertIn("JSON inválido", out)

    def test_ctrl_c_exit_130(self):
        code, out = run_and_capture(KeyboardInterrupt())
        self.assertEqual(code, 130)
        self.assertIn("Cancelado", out)


class TestExceptionHierarchy(unittest.TestCase):

    def test_compatibilidad_con_runtime_error(self):
        """Código existente que captura RuntimeError sigue funcionando."""
        self.assertTrue(issubclass(MikroTikConnectionError, RuntimeError))
        self.assertTrue(issubclass(MikroTikCommandError, RuntimeError))


if __name__ == "__main__":
    unittest.main()
