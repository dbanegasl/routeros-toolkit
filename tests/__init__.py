"""Suite de tests del RouterOS Toolkit.

Ejecutar desde la raíz del proyecto:
    python3 -m unittest discover -s tests -v
"""

import sys
from pathlib import Path

# Garantiza que `lib` sea importable sin importar desde dónde se ejecute
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
