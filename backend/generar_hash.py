#!/usr/bin/env python3
"""
generar_hash.py — Genera el APP_PASSWORD_HASH del panel web
===========================================================

Pide la contraseña (sin mostrarla) y imprime la línea lista para pegar
en config.env. Solo stdlib.

Uso:
    python3 backend/generar_hash.py
"""

import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.app.auth import generar_hash  # noqa: E402


def main():
    print("Contraseña para el panel web (no es la del router).")
    password = getpass.getpass("  Contraseña: ")
    if len(password) < 8:
        print("  ⚠️  Muy corta: usa al menos 8 caracteres.")
        sys.exit(1)
    repetida = getpass.getpass("  Repítela  : ")
    if password != repetida:
        print("  ❌ No coinciden.")
        sys.exit(1)

    print("\nAgrega esta línea a config.env (junto a las MIKROTIK_*):\n")
    print(f"APP_PASSWORD_HASH={generar_hash(password)}\n")


if __name__ == "__main__":
    main()
