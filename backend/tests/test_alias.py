"""
test_alias.py — Endpoints de alias y su efecto en el resto del panel
====================================================================

El alias se guarda en config/alias.json (tmp_path del fixture) sin
tocar el router, y aparece en Dispositivos y en la lista blanca.
"""

import json

from lib import config_path, load_aliases
from backend.app import ws as ws_mod

KEVIN = "F0:2F:74:CB:97:3F"


def test_requiere_sesion(client):
    assert client.get("/api/alias").status_code == 401
    r = client.put(f"/api/alias/{KEVIN}", json={"alias": "x"})
    assert r.status_code == 401


def test_guardar_y_leer(session):
    r = session.put(f"/api/alias/{KEVIN.lower()}",
                    json={"alias": "PC de Kevin"})
    assert r.status_code == 200
    assert r.json()["mac"] == KEVIN
    assert r.json()["alias"] == "PC de Kevin"
    assert session.get("/api/alias").json() == {"alias": {KEVIN: "PC de Kevin"}}
    # No toca el router
    assert session.fake_api.writes == []


def test_alias_vacio_lo_quita(session):
    session.put(f"/api/alias/{KEVIN}", json={"alias": "PC de Kevin"})
    r = session.put(f"/api/alias/{KEVIN}", json={"alias": ""})
    assert r.status_code == 200
    assert r.json()["alias"] == ""
    assert load_aliases() == {}


def test_mac_invalida_400(session):
    r = session.put("/api/alias/no-es-mac", json={"alias": "x"})
    assert r.status_code == 400


def test_alias_largo_400(session):
    r = session.put(f"/api/alias/{KEVIN}", json={"alias": "x" * 41})
    assert r.status_code == 400
    assert load_aliases() == {}


def test_archivo_corrupto_500_con_mensaje(session):
    with open(config_path("alias"), "w", encoding="utf-8") as f:
        f.write("{ no es json")
    r = session.get("/api/alias")
    assert r.status_code == 500
    assert "alias.json" in r.json()["detail"]


def test_invalida_cache_de_nombres_del_monitor(session):
    ws_mod._EstadoMonitor.nombres_ts = 10**12
    session.put(f"/api/alias/{KEVIN}", json={"alias": "PC de Kevin"})
    assert ws_mod._EstadoMonitor.nombres_ts == 0.0


def test_dispositivos_muestra_alias(session):
    session.put(f"/api/alias/{KEVIN}", json={"alias": "PC de Kevin"})
    filas = {d["mac"]: d for d in
             session.get("/api/dispositivos").json()["dispositivos"]}
    assert filas[KEVIN]["nombre"] == "PC de Kevin"
    assert filas[KEVIN]["nombre_detectado"] == "kevin-pc"
    assert filas[KEVIN]["alias"] == "PC de Kevin"


def test_whitelist_muestra_alias_e_ip(session):
    session.put("/api/horario/whitelist", json={
        "macs": [KEVIN], "confirmar": True})
    session.put(f"/api/alias/{KEVIN}", json={"alias": "PC de Kevin"})
    for ruta, clave in (("/api/horario/whitelist", "dispositivos"),
                        ("/api/horario", "whitelist")):
        filas = {d["mac"]: d for d in session.get(ruta).json()[clave]}
        assert filas[KEVIN]["nombre"] == "PC de Kevin", ruta
        assert filas[KEVIN]["nombre_detectado"] == "kevin-pc", ruta
        assert filas[KEVIN]["ip"] == "192.168.5.22", ruta


def test_whitelist_json_guarda_nombre_detectado(session):
    """Quitar el alias no debe dejar su texto en whitelist.json."""
    session.put(f"/api/alias/{KEVIN}", json={"alias": "PC de Kevin"})
    session.put("/api/horario/whitelist", json={
        "macs": [KEVIN], "confirmar": True})
    with open(config_path("whitelist"), encoding="utf-8") as f:
        guardado = json.load(f)["dispositivos"]
    assert guardado[0]["nombre"] == "kevin-pc"
