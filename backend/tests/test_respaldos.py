"""
test_respaldos.py — Endpoints de respaldos (snapshot local + .backup)
=====================================================================

MIKROTIK_BACKUP_DIR apunta a un directorio temporal: ningún test toca
backups/ real.
"""

import json


class TestListar:

    def test_requiere_sesion(self, client):
        assert client.get("/api/respaldos").status_code == 401

    def test_lista_vacia_y_router(self, session, monkeypatch, tmp_path):
        monkeypatch.setenv("MIKROTIK_BACKUP_DIR", str(tmp_path / "backups"))
        r = session.get("/api/respaldos")
        assert r.status_code == 200
        datos = r.json()
        assert datos["locales"] == []
        # De /file/print solo pasan los .backup (el .txt se filtra)
        assert len(datos["router"]) == 1
        assert datos["router"][0]["nombre"].endswith(".backup")
        assert datos["router"][0]["bytes"] == 12345


class TestCrear:

    def test_snapshot_local(self, session, monkeypatch, tmp_path):
        destino = tmp_path / "backups"
        monkeypatch.setenv("MIKROTIK_BACKUP_DIR", str(destino))

        r = session.post("/api/respaldos", json={"full": False})
        assert r.status_code == 200
        datos = r.json()
        assert datos["backup_router"] is None
        assert datos["snapshot"].startswith("snapshot_")

        # El archivo existe y es un snapshot válido con sus 9 secciones
        archivos = list(destino.glob("snapshot_*.json"))
        assert len(archivos) == 1
        with open(archivos[0]) as f:
            contenido = json.load(f)
        assert contenido["meta"]["routeros"] == "6.49.19"
        assert len(contenido["secciones"]) == 9
        assert datos["secciones"]["dhcp_leases"] == 1

        # Solo lectura sobre el router: sin /system/backup/save
        cmds = [cmd for cmd, _ in session.fake_api.writes]
        assert "/system/backup/save" not in cmds

    def test_snapshot_mas_backup_en_router(self, session, monkeypatch,
                                           tmp_path):
        monkeypatch.setenv("MIKROTIK_BACKUP_DIR", str(tmp_path / "backups"))

        r = session.post("/api/respaldos", json={"full": True})
        assert r.status_code == 200
        datos = r.json()
        assert datos["backup_router"].endswith(".backup")

        saves = [(cmd, p) for cmd, p in session.fake_api.writes
                 if cmd == "/system/backup/save"]
        assert len(saves) == 1
        assert saves[0][1][0].startswith("=name=respaldo-")

    def test_luego_aparece_en_la_lista(self, session, monkeypatch, tmp_path):
        monkeypatch.setenv("MIKROTIK_BACKUP_DIR", str(tmp_path / "backups"))
        session.post("/api/respaldos", json={"full": False})
        datos = session.get("/api/respaldos").json()
        assert len(datos["locales"]) == 1
        assert datos["locales"][0]["meta"]["equipo"] == "hEX lite"
