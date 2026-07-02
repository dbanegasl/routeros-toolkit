"""
auth.py — Login con contraseña propia de la app, sesiones y rate-limit
======================================================================

- La contraseña se valida contra APP_PASSWORD_HASH (PBKDF2-SHA256,
  generado con backend/generar_hash.py). La contraseña del ROUTER nunca
  participa aquí ni viaja al navegador.
- Sesiones en memoria: token aleatorio → expiración. Cookie httpOnly.
  (Un solo proceso uvicorn; si algún día hay varios workers, esto debe
  moverse a un almacén compartido.)
- Rate-limit del login: 5 intentos por minuto por IP.
"""

import hashlib
import hmac
import os
import secrets
import threading
import time

from fastapi import APIRouter, Cookie, HTTPException, Request, Response
from pydantic import BaseModel

from .deps import get_password_hash, get_session_ttl

COOKIE_SESION = "sesion"
PBKDF2_ITERACIONES = 240_000

MAX_INTENTOS = 5          # intentos de login permitidos…
VENTANA_SEGUNDOS = 60     # …por IP dentro de esta ventana

_lock = threading.Lock()
_sesiones: dict = {}      # token → expiración (epoch)
_intentos: dict = {}      # ip → [timestamps de intentos fallidos]

router = APIRouter(prefix="/api/auth", tags=["auth"])


# ---------------------------------------------------------------------------
# Hash de contraseña (PBKDF2-SHA256, solo stdlib)
# ---------------------------------------------------------------------------

def generar_hash(password: str) -> str:
    """'pbkdf2_sha256$<iteraciones>$<salt_hex>$<hash_hex>'"""
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt,
                             PBKDF2_ITERACIONES)
    return f"pbkdf2_sha256${PBKDF2_ITERACIONES}${salt.hex()}${dk.hex()}"


def verificar_password(password: str, almacenado: str) -> bool:
    try:
        algoritmo, iteraciones, salt_hex, hash_hex = almacenado.split("$")
        if algoritmo != "pbkdf2_sha256":
            return False
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(),
                                 bytes.fromhex(salt_hex), int(iteraciones))
        return hmac.compare_digest(dk.hex(), hash_hex)
    except (ValueError, AttributeError):
        return False


# ---------------------------------------------------------------------------
# Sesiones
# ---------------------------------------------------------------------------

def _crear_sesion() -> str:
    token = secrets.token_urlsafe(32)
    with _lock:
        _sesiones[token] = time.time() + get_session_ttl()
    return token


def _sesion_valida(token: str) -> bool:
    with _lock:
        exp = _sesiones.get(token)
        if exp is None:
            return False
        if time.time() > exp:
            del _sesiones[token]
            return False
        return True


def _destruir_sesion(token: str):
    with _lock:
        _sesiones.pop(token, None)


def limpiar_estado():
    """Borra sesiones e intentos registrados (para los tests)."""
    with _lock:
        _sesiones.clear()
        _intentos.clear()


def require_session(sesion: str = Cookie(default="")):
    """Dependencia: toda ruta protegida exige cookie de sesión vigente."""
    if not _sesion_valida(sesion):
        raise HTTPException(
            status_code=401,
            detail="Sesión inválida o expirada. Inicia sesión en /api/auth/login.")


# ---------------------------------------------------------------------------
# Rate-limit del login
# ---------------------------------------------------------------------------

def _permitir_intento(ip: str) -> bool:
    ahora = time.time()
    with _lock:
        recientes = [t for t in _intentos.get(ip, [])
                     if ahora - t < VENTANA_SEGUNDOS]
        _intentos[ip] = recientes
        return len(recientes) < MAX_INTENTOS


def _registrar_intento(ip: str):
    with _lock:
        _intentos.setdefault(ip, []).append(time.time())


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

class LoginBody(BaseModel):
    password: str


@router.post("/login")
def login(body: LoginBody, request: Request, response: Response):
    """Valida la contraseña de la app y crea la cookie de sesión."""
    ip = request.client.host if request.client else "?"
    if not _permitir_intento(ip):
        raise HTTPException(
            status_code=429,
            detail=f"Demasiados intentos. Espera {VENTANA_SEGUNDOS} segundos.")

    almacenado = get_password_hash()
    if not almacenado:
        raise HTTPException(
            status_code=503,
            detail="APP_PASSWORD_HASH no está configurado en el servidor. "
                   "Genera uno con: python3 backend/generar_hash.py")

    if not verificar_password(body.password, almacenado):
        _registrar_intento(ip)
        raise HTTPException(status_code=401, detail="Contraseña incorrecta.")

    token = _crear_sesion()
    response.set_cookie(COOKIE_SESION, token, httponly=True,
                        samesite="lax", max_age=get_session_ttl())
    return {"mensaje": "Sesión iniciada."}


@router.post("/logout")
def logout(response: Response, sesion: str = Cookie(default="")):
    _destruir_sesion(sesion)
    response.delete_cookie(COOKIE_SESION)
    return {"mensaje": "Sesión cerrada."}
