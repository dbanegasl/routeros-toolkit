"""
app_config.py — Configuración de la aplicación en archivos JSON
================================================================

Sistema genérico de archivos de configuración del toolkit, separado de
config.env (que solo guarda credenciales de conexión).

Los archivos viven en <raíz del proyecto>/config/ (overrideable con la
variable de entorno MIKROTIK_CONFIG_DIR). Los reales están en .gitignore;
las plantillas *.example sí se versionan.

Uso:
    from lib.app_config import load_json_config, save_json_config

    qos = load_json_config("qos", default=QOS_DEFAULTS)
    save_json_config("whitelist", {"dispositivos": [...]})
"""

import json
import os
from pathlib import Path


class ConfigError(RuntimeError):
    """Error de configuración con mensaje apto para mostrar al usuario."""


def get_config_dir() -> Path:
    """Directorio de configuración: env MIKROTIK_CONFIG_DIR o config/ del proyecto."""
    env_dir = os.environ.get("MIKROTIK_CONFIG_DIR")
    if env_dir:
        return Path(env_dir)
    return Path(__file__).parent.parent / "config"


def config_path(name: str) -> Path:
    """Ruta completa del archivo de configuración <name>.json."""
    return get_config_dir() / f"{name}.json"


def load_json_config(name: str, default: dict = None) -> dict:
    """
    Lee config/<name>.json.

    - Si el archivo no existe, retorna una copia de `default` (o {} si no hay).
    - Si el JSON está corrupto, lanza ConfigError con mensaje claro
      (nunca un traceback crudo).
    - Las claves faltantes se completan desde `default` (merge superficial),
      así agregar opciones nuevas no rompe archivos viejos.
    """
    path = config_path(name)
    base = dict(default) if default else {}

    if not path.exists():
        return base

    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise ConfigError(
            f"El archivo {path} tiene JSON inválido "
            f"(línea {e.lineno}): {e.msg}.\n"
            f"Corrígelo o bórralo para regenerarlo con valores por defecto."
        )
    except OSError as e:
        raise ConfigError(f"No se pudo leer {path}: {e}")

    if not isinstance(data, dict):
        raise ConfigError(
            f"El archivo {path} debe contener un objeto JSON "
            f"(se encontró {type(data).__name__})."
        )

    base.update(data)
    return base


def save_json_config(name: str, data: dict):
    """Escribe config/<name>.json (crea el directorio si no existe)."""
    path = config_path(name)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write("\n")
    except OSError as e:
        raise ConfigError(f"No se pudo escribir {path}: {e}")
