"""
hashing.py — Hash de la contraseña del panel (PBKDF2-SHA256, solo stdlib)
=========================================================================

Separado de auth.py para que backend/generar_hash.py pueda ejecutarse con
el Python del sistema, sin FastAPI ni el venv del backend.
"""

import hashlib
import hmac
import os

PBKDF2_ITERACIONES = 240_000


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
