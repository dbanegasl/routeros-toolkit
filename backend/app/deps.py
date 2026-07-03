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

from lib import MikroTikAPI, MikroTikCommandError, load_config  # noqa: E402

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


def get_api():
    """Dependencia FastAPI: la conexión persistente, bajo candado global.

    El candado se mantiene durante toda la petición (los endpoints son
    síncronos y corren en el threadpool), así el router nunca ve
    peticiones concurrentes del backend. Un !trap (MikroTikCommandError)
    no daña la conexión y la deja viva; cualquier otro error se asume
    conexión rota: se cierra y la siguiente petición reconecta.
    """
    global _api_compartida, _ultimo_uso
    with _router_lock:
        # Conexión ociosa: comprobar que siga viva antes de reutilizarla
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
        try:
            yield _api_compartida
            _ultimo_uso = time.time()
        except (MikroTikCommandError, GeneratorExit):
            # Un !trap no rompe la conexión; GeneratorExit es teardown
            # normal del generador — en ambos casos sigue viva.
            _ultimo_uso = time.time()
            raise
        except BaseException:
            try:
                _api_compartida.close()
            finally:
                _api_compartida = None
            raise


def get_password_hash() -> str:
    """Hash de la contraseña de la app (APP_PASSWORD_HASH del entorno)."""
    return os.environ.get("APP_PASSWORD_HASH", "")


def get_session_ttl() -> int:
    """Duración de la sesión en segundos (APP_SESSION_TTL, default 12 h)."""
    return int(os.environ.get("APP_SESSION_TTL", 43200))
