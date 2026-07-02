"""
deps.py — Dependencias compartidas del backend
==============================================

- Conexión al router: una sola a la vez (candado global). El hEX lite es
  modesto; serializar evita N conexiones API simultáneas.
- Settings de la app web (APP_*), leídos del entorno en cada acceso para
  que los tests puedan modificarlos.
"""

import os
import sys
import threading
from pathlib import Path

# Repo raíz en sys.path: el backend importa lib/ y core/ igual que los scripts
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from lib import MikroTikAPI, load_config  # noqa: E402

_router_lock = threading.Lock()


def get_api():
    """Dependencia FastAPI: MikroTikAPI conectada, bajo candado global.

    El candado se mantiene durante toda la petición (los endpoints son
    síncronos y corren en el threadpool), así el router nunca ve más de
    una conexión API del backend a la vez.
    """
    with _router_lock:
        cfg = load_config()
        with MikroTikAPI(**cfg) as api:
            yield api


def get_password_hash() -> str:
    """Hash de la contraseña de la app (APP_PASSWORD_HASH del entorno)."""
    return os.environ.get("APP_PASSWORD_HASH", "")


def get_session_ttl() -> int:
    """Duración de la sesión en segundos (APP_SESSION_TTL, default 12 h)."""
    return int(os.environ.get("APP_SESSION_TTL", 43200))
