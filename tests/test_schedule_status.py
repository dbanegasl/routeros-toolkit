"""
test_schedule_status.py — Tests del estado del corte de internet (script 09)
=============================================================================

Funciones puras de 09_schedule_internet.py:
- normalize_ros_time: RouterOS v6 devuelve tiempos en formato de duración
  ('1h1m'), hay que normalizarlos a HH:MM:SS
- parse_drop_time: extracción de horario y días de la regla DROP
- parse_router_date: fecha del reloj del router (formato v6 y v7)
- corte_en_curso: si el corte está bloqueando AHORA (incluye rangos que
  cruzan medianoche)

No requiere router.
"""

import importlib.util
import unittest
from datetime import date
from pathlib import Path

# Importar el script 09 como módulo (su nombre empieza con dígito)
_spec = importlib.util.spec_from_file_location(
    "schedule_internet",
    Path(__file__).resolve().parent.parent / "scripts" / "09_schedule_internet.py")
schedule = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(schedule)


class TestNormalizeRosTime(unittest.TestCase):

    def test_duracion_routeros_v6(self):
        # RouterOS v6 devuelve '1h1m-6h1m' para un corte 01:01 → 06:01
        self.assertEqual(schedule.normalize_ros_time("1h1m"), "01:01:00")
        self.assertEqual(schedule.normalize_ros_time("6h1m"), "06:01:00")

    def test_solo_horas_o_minutos(self):
        self.assertEqual(schedule.normalize_ros_time("6h"), "06:00:00")
        self.assertEqual(schedule.normalize_ros_time("45m"), "00:45:00")
        self.assertEqual(schedule.normalize_ros_time("1h30m15s"), "01:30:15")

    def test_medianoche(self):
        self.assertEqual(schedule.normalize_ros_time("0s"), "00:00:00")

    def test_formato_hhmmss_pasa_intacto(self):
        self.assertEqual(schedule.normalize_ros_time("01:01:00"), "01:01:00")
        self.assertEqual(schedule.normalize_ros_time("23:59"), "23:59:00")

    def test_valor_irreconocible_se_retorna_tal_cual(self):
        self.assertEqual(schedule.normalize_ros_time("???"), "???")


class TestParseDropTime(unittest.TestCase):

    def test_formato_duracion_v6(self):
        rule = {"time": "1h1m-6h1m,mon,tue,wed"}
        start, end, days = schedule.parse_drop_time(rule)
        self.assertEqual(start, "01:01:00")
        self.assertEqual(end, "06:01:00")
        self.assertEqual(days, ["mon", "tue", "wed"])

    def test_sin_dias_significa_todos(self):
        start, end, days = schedule.parse_drop_time({"time": "22h-6h"})
        self.assertEqual((start, end), ("22:00:00", "06:00:00"))
        self.assertEqual(days, schedule.ALL_DAYS)

    def test_sin_campo_time(self):
        start, end, days = schedule.parse_drop_time({})
        self.assertEqual((start, end), ("", ""))
        self.assertEqual(days, schedule.ALL_DAYS)


class TestParseRouterDate(unittest.TestCase):

    def test_formato_v6(self):
        self.assertEqual(schedule.parse_router_date("jul/02/2026"),
                         date(2026, 7, 2))

    def test_formato_v7(self):
        self.assertEqual(schedule.parse_router_date("2026-07-02"),
                         date(2026, 7, 2))

    def test_invalida(self):
        self.assertIsNone(schedule.parse_router_date("no-es-fecha"))
        self.assertIsNone(schedule.parse_router_date(""))


class TestCorteEnCurso(unittest.TestCase):
    """Caso real del usuario: corte 01:01 → 06:01 todos los días."""

    DIAS = list(schedule.ALL_DAYS)

    def _min(self, hhmm: str) -> int:
        h, m = hhmm.split(":")
        return int(h) * 60 + int(m)

    def test_fuera_de_horario_manana(self):
        # 08:37 de un jueves — el corte NO debe reportarse en curso
        self.assertFalse(schedule.corte_en_curso(
            "01:01", "06:01", self.DIAS, self._min("08:37"), "thu"))

    def test_dentro_del_horario(self):
        self.assertTrue(schedule.corte_en_curso(
            "01:01", "06:01", self.DIAS, self._min("03:00"), "thu"))

    def test_bordes_inicio_inclusive_fin_exclusive(self):
        self.assertTrue(schedule.corte_en_curso(
            "01:01", "06:01", self.DIAS, self._min("01:01"), "thu"))
        self.assertFalse(schedule.corte_en_curso(
            "01:01", "06:01", self.DIAS, self._min("06:01"), "thu"))

    def test_dia_no_incluido(self):
        solo_lunes = ["mon"]
        self.assertFalse(schedule.corte_en_curso(
            "01:01", "06:01", solo_lunes, self._min("03:00"), "thu"))
        self.assertTrue(schedule.corte_en_curso(
            "01:01", "06:01", solo_lunes, self._min("03:00"), "mon"))

    def test_cruza_medianoche(self):
        # Corte 22:00 → 06:00 solo viernes: la madrugada del sábado cuenta
        viernes = ["fri"]
        self.assertTrue(schedule.corte_en_curso(
            "22:00", "06:00", viernes, self._min("23:00"), "fri"))
        self.assertTrue(schedule.corte_en_curso(
            "22:00", "06:00", viernes, self._min("03:00"), "sat"))
        self.assertFalse(schedule.corte_en_curso(
            "22:00", "06:00", viernes, self._min("12:00"), "fri"))
        self.assertFalse(schedule.corte_en_curso(
            "22:00", "06:00", viernes, self._min("23:00"), "sat"))

    def test_rango_vacio_o_sin_horario(self):
        self.assertFalse(schedule.corte_en_curso(
            "01:00", "01:00", self.DIAS, self._min("01:00"), "thu"))
        self.assertFalse(schedule.corte_en_curso(
            "", "", self.DIAS, self._min("01:00"), "thu"))


if __name__ == "__main__":
    unittest.main()
