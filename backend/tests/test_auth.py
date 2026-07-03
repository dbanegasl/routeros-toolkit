"""
test_auth.py — Login, sesiones, rate-limit y protección de rutas
================================================================
"""

from backend.app.auth import generar_hash, verificar_password
from backend.tests.conftest import PASSWORD_TEST


class TestHash:

    def test_roundtrip(self):
        h = generar_hash("secreta123")
        assert verificar_password("secreta123", h)
        assert not verificar_password("otra", h)

    def test_hash_invalido_no_explota(self):
        assert not verificar_password("x", "")
        assert not verificar_password("x", "basura$sin$formato")
        assert not verificar_password("x", "pbkdf2_sha256$abc$zz$zz")


class TestLogin:

    def test_login_correcto_crea_cookie(self, client):
        r = client.post("/api/auth/login", json={"password": PASSWORD_TEST})
        assert r.status_code == 200
        assert "sesion" in r.cookies

    def test_password_incorrecta_401(self, client):
        r = client.post("/api/auth/login", json={"password": "mala"})
        assert r.status_code == 401
        assert "incorrecta" in r.json()["detail"]

    def test_sin_hash_configurado_503(self, client, monkeypatch):
        monkeypatch.setenv("APP_PASSWORD_HASH", "")
        r = client.post("/api/auth/login", json={"password": PASSWORD_TEST})
        assert r.status_code == 503

    def test_rate_limit_tras_5_intentos(self, client):
        for _ in range(5):
            r = client.post("/api/auth/login", json={"password": "mala"})
            assert r.status_code == 401
        r = client.post("/api/auth/login", json={"password": "mala"})
        assert r.status_code == 429
        # Incluso con la contraseña buena: la IP quedó limitada
        r = client.post("/api/auth/login", json={"password": PASSWORD_TEST})
        assert r.status_code == 429

    def test_logout_invalida_la_sesion(self, session):
        assert session.get("/api/sistema").status_code == 200
        session.post("/api/auth/logout")
        assert session.get("/api/sistema").status_code == 401


class TestRutasProtegidas:

    RUTAS = ["/api/sistema", "/api/interfaces", "/api/dispositivos",
             "/api/escaneo", "/api/horario", "/api/validacion", "/api/config",
             "/api/consumo"]

    def test_todas_exigen_sesion(self, client):
        for ruta in self.RUTAS:
            assert client.get(ruta).status_code == 401, ruta

    def test_salud_es_publica(self, client):
        r = client.get("/api/salud")
        assert r.status_code == 200
        assert r.json() == {"estado": "ok"}
