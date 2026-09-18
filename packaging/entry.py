"""Punto de entrada del ejecutable empaquetado con PyInstaller.

No se usa src/odoo_mcp/__main__.py: PyInstaller ejecuta el script suelto, sin
contexto de paquete, y sus imports relativos fallarian.
"""

import sys

from odoo_mcp.server import main

if __name__ == "__main__":
    sys.exit(main())
