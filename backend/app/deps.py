"""
deps.py — Dependencias compartidas del backend
==============================================

- Conexión al router: UNA conexión persistente compartida, bajo candado
  global. El hEX lite es modesto y además anota cada login/logout en su
  log ("user admin logged in via api"): abrir una conexión por petición
  inundaba el syslog. La conexión se reutiliza entre peticiones y se
  reabre sola si el router la corta.
- Settings de la app web (APP_*), leídos del entorno en cada acceso para
  que los tests puedan modificarlos.
"""

import os
import sys
import threading
import time
from pathlib import Path

# Repo raíz en sys.path: el backend importa lib/ y core/ igual que los scripts
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from fastapi import HTTPException

from lib import MikroTikAPI, MikroTikCommandError, load_config  # noqa: E402

# Excepciones que NO indican conexión rota: la dejan viva.
_EXCEPCIONES_INOCUAS = (MikroTikCommandError, HTTPException)

_router_lock = threading.Lock()
_api_compartida: MikroTikAPI | None = None
_ultimo_uso = 0.0
# Tras este tiempo sin uso se verifica que el router no haya cortado la
# conexión, con una lectura barata, antes de reutilizarla.
VERIFICAR_TRAS_OCIO = 60


def cerrar_api_compartida():
    """Cierra la conexión persistente (logout limpio al apagar la app)."""
    global _api_compartida
    with _router_lock:
        if _api_compartida is not None:
            try:
                _api_compartida.close()
            finally:
                _api_compartida = None


def _obtener_api() -> MikroTikAPI:
    """Retorna la conexión persistente, reconectando si hace falta.

    ASUME el candado tomado. Si la conexión estuvo ociosa, primero se
    comprueba con una lectura barata que el router no la haya cortado.
    """
    global _api_compartida
    if (_api_compartida is not None
            and time.time() - _ultimo_uso > VERIFICAR_TRAS_OCIO):
        try:
            _api_compartida.command("/system/identity/print")
        except Exception:
            try:
                _api_compartida.close()
            except Exception:
                pass
            _api_compartida = None

    if _api_compartida is None:
        api = MikroTikAPI(**load_config())
        api.connect()
        _api_compartida = api
    return _api_compartida


def _resetear_api():
    """Cierra y descarta la conexión (se asume rota). Candado tomado."""
    global _api_compartida
    if _api_compartida is not None:
        try:
            _api_compartida.close()
        finally:
            _api_compartida = None


def get_api():
    """Dependencia FastAPI: la conexión persistente, bajo candado global.

    El candado se mantiene durante toda la petición (los endpoints son
    síncronos y corren en el threadpool), así el router nunca ve
    peticiones concurrentes del backend. Un !trap (MikroTikCommandError)
    no daña la conexión y la deja viva; cualquier otro error se asume
    conexión rota: se cierra y la siguiente petición reconecta.
    """
    global _ultimo_uso
    with _router_lock:
        api = _obtener_api()
        try:
            yield api
            _ultimo_uso = time.time()
        except (*_EXCEPCIONES_INOCUAS, GeneratorExit):
            # Un !trap o un HTTPException (validación) no rompen la
            # conexión; GeneratorExit es teardown normal del generador.
            _ultimo_uso = time.time()
            raise
        except BaseException:
            _resetear_api()
            raise


def usar_api(func):
    """Ejecuta func(api) con la MISMA conexión persistente, bajo candado.

    Es el equivalente de get_api para código que no es un endpoint
    (el muestreo de los WebSockets): así todo el backend comparte una
    única conexión al router y el syslog no ve logins repetidos.
    """
    global _ultimo_uso
    with _router_lock:
        api = _obtener_api()
        try:
            resultado = func(api)
            _ultimo_uso = time.time()
            return resultado
        except _EXCEPCIONES_INOCUAS:
            _ultimo_uso = time.time()
            raise
        except BaseException:
            _resetear_api()
            raise


def get_password_hash() -> str:
    """Hash de la contraseña de la app (APP_PASSWORD_HASH del entorno)."""
    return os.environ.get("APP_PASSWORD_HASH", "")


def get_session_ttl() -> int:
    """Duración de la sesión en segundos (APP_SESSION_TTL, default 12 h)."""
    return int(os.environ.get("APP_SESSION_TTL", 43200))
