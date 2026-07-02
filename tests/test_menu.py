"""Tests de integridad del menú interactivo (menu.py).

No ejecuta ningún script ni toca el router: solo valida que la
definición del menú sea coherente (claves únicas, scripts existentes,
confirmaciones apuntando a opciones reales).
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import menu


class TestIntegridadMenu(unittest.TestCase):

    def _items(self):
        for section in menu.MENU.values():
            for item in section["items"]:
                yield item

    def test_claves_unicas(self):
        claves = [key for key, *_ in self._items()]
        duplicadas = {k for k in claves if claves.count(k) > 1}
        self.assertEqual(duplicadas, set(), f"Claves duplicadas en MENU: {duplicadas}")

    def test_estructura_de_items(self):
        for item in self._items():
            self.assertEqual(len(item), 5, f"Item con formato inesperado: {item}")

    def test_scripts_referenciados_existen(self):
        for key, _label, script, _args, _desc in self._items():
            if script is not None:
                ruta = os.path.join(menu.SCRIPTS, script)
                self.assertTrue(os.path.isfile(ruta),
                                f"Opción [{key}] apunta a script inexistente: {script}")

    def test_confirmar_apunta_a_opciones_reales(self):
        lookup = menu.build_lookup()
        for key in menu.CONFIRMAR:
            self.assertIn(key, lookup,
                          f"CONFIRMAR referencia la opción [{key}] que no está en MENU")

    def test_dry_run_no_requiere_confirmacion(self):
        # La opción de dry-run es de solo lectura: no debe pedir confirmación
        lookup = menu.build_lookup()
        for key, (script, args) in lookup.items():
            if args and "--dry-run" in args:
                self.assertNotIn(key, menu.CONFIRMAR)

    def test_mutadores_inmediatos_requieren_confirmacion(self):
        # Opciones que escriben en el router sin volver a preguntar:
        # 10 (deploy), 13 (reset) y 09 --remove (eliminar corte)
        lookup = menu.build_lookup()
        for key, (script, args) in lookup.items():
            inmediato = (
                (script in ("10_deploy_qos.py", "13_reset_qos.py")
                 and "--dry-run" not in args)
                or (script == "09_schedule_internet.py" and "--remove" in args)
            )
            if inmediato:
                self.assertIn(key, menu.CONFIRMAR,
                              f"Opción [{key}] ({script} {args}) escribe en el router y no pide confirmación")


if __name__ == "__main__":
    unittest.main()
