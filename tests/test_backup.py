"""
test_backup.py — Tests del respaldo de configuración (script 14)
=================================================================

build_snapshot / save_snapshot / snapshot_filename con una API falsa y
un directorio temporal (MIKROTIK_BACKUP_DIR). También get_router_datetime
de la lib. No requiere router.
"""

import importlib.util
import json
import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from lib import get_router_datetime

# Importar el script 14 como módulo (su nombre empieza con dígito)
_spec = importlib.util.spec_from_file_location(
    "backup",
    Path(__file__).resolve().parent.parent / "scripts" / "14_backup.py")
backup = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(backup)


class FakeAPI:
    """Simula MikroTikAPI.command() con respuestas predefinidas."""

    def __init__(self, responses: dict):
        self.responses = responses
        self.writes = []

    def command(self, cmd, params=None, queries=None):
        if params:
            self.writes.append((cmd, params))
        return self.responses.get(cmd, [])


def make_fake_api():
    return FakeAPI({
        "/system/resource/print": [
            {"version": "6.49.19", "board-name": "hEX lite"}],
        "/system/clock/print": [
            {"date": "jul/02/2026", "time": "10:15:30"}],
        "/system/identity/print": [{"name": "MiRouter"}],
        "/ip/firewall/filter/print": [
            {"chain": "forward", "action": "drop", "comment": "HORARIO-INTERNET"},
            {"chain": "forward", "action": "accept"},
        ],
        "/queue/tree/print": [{"name": "QoS_Download"}],
        "/file/print": [
            {"name": "respaldo-20260702.backup", "size": "150000",
             "creation-time": "jul/02/2026 10:00:00"},
            {"name": "log.txt", "size": "10"},
        ],
    })


class TestSnapshot(unittest.TestCase):

    def test_build_snapshot_estructura(self):
        snap = backup.build_snapshot(make_fake_api())
        self.assertEqual(snap["meta"]["routeros"], "6.49.19")
        self.assertEqual(snap["meta"]["equipo"], "hEX lite")
        self.assertEqual(snap["meta"]["hora_router"], "2026-07-02T10:15:30")
        # Todas las secciones declaradas están presentes (vacías si no hay datos)
        self.assertEqual(set(snap["secciones"]),
                         set(backup.SNAPSHOT_SECTIONS))
        self.assertEqual(len(snap["secciones"]["firewall_filter"]), 2)
        self.assertEqual(snap["secciones"]["queue_tree"][0]["name"], "QoS_Download")
        self.assertEqual(snap["secciones"]["firewall_mangle"], [])

    def test_build_snapshot_es_solo_lectura(self):
        api = make_fake_api()
        backup.build_snapshot(api)
        self.assertEqual(api.writes, [])

    def test_snapshot_filename(self):
        nombre = backup.snapshot_filename(datetime(2026, 7, 2, 10, 15, 30))
        self.assertEqual(nombre, "snapshot_2026-07-02_101530.json")

    def test_save_snapshot_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["MIKROTIK_BACKUP_DIR"] = tmp
            try:
                ruta = backup.save_snapshot(backup.build_snapshot(make_fake_api()))
                self.assertTrue(ruta.exists())
                self.assertEqual(ruta.parent, Path(tmp))
                with open(ruta) as f:
                    leido = json.load(f)
                self.assertEqual(leido["meta"]["routeros"], "6.49.19")
            finally:
                del os.environ["MIKROTIK_BACKUP_DIR"]

    def test_list_router_backups_filtra_solo_backup(self):
        archivos = backup.list_router_backups(make_fake_api())
        self.assertEqual(len(archivos), 1)
        self.assertEqual(archivos[0]["name"], "respaldo-20260702.backup")

    def test_create_router_backup_ejecuta_save(self):
        api = make_fake_api()
        nombre = backup.create_router_backup(api)
        self.assertTrue(nombre.startswith("respaldo-"))
        self.assertTrue(nombre.endswith(".backup"))
        self.assertEqual(len(api.writes), 1)
        cmd, params = api.writes[0]
        self.assertEqual(cmd, "/system/backup/save")
        self.assertTrue(params[0].startswith("=name=respaldo-"))


class TestGetRouterDatetime(unittest.TestCase):

    def test_formato_v6(self):
        api = FakeAPI({"/system/clock/print": [
            {"date": "jul/02/2026", "time": "08:42:07"}]})
        self.assertEqual(get_router_datetime(api),
                         datetime(2026, 7, 2, 8, 42, 7))

    def test_formato_v7(self):
        api = FakeAPI({"/system/clock/print": [
            {"date": "2026-07-02", "time": "23:59"}]})
        self.assertEqual(get_router_datetime(api),
                         datetime(2026, 7, 2, 23, 59, 0))

    def test_reloj_ilegible(self):
        self.assertIsNone(get_router_datetime(FakeAPI({})))
        api = FakeAPI({"/system/clock/print": [{"date": "???", "time": "??"}]})
        self.assertIsNone(get_router_datetime(api))


if __name__ == "__main__":
    unittest.main()
