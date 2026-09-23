#!/usr/bin/env bash
# Construye el ejecutable de macOS (o Linux). El equivalente de build.ps1.
#
#   ./build.sh
#
# Deja dist/odoo-mcp. Para repartirlo en Mac se renombra a .command, que es lo
# que hace que el doble clic en Finder lo abra en una terminal.
set -euo pipefail
cd "$(dirname "$0")"

echo
echo "  Construyendo el ejecutable de odoo-mcp"
echo "  --------------------------------------"

if ! command -v uv >/dev/null 2>&1; then
    echo "ERROR: falta 'uv'. Instalalo con:" >&2
    echo "  curl -LsSf https://astral.sh/uv/install.sh | sh" >&2
    exit 1
fi

echo "[1/4] Instalando dependencias..."
uv sync --group dev

echo "[2/4] Ejecutando las pruebas..."
uv run pytest -q

echo "[3/4] Empaquetando con PyInstaller (1-2 minutos)..."
rm -rf build dist
# Mismos motivos que en build.ps1: mcp.server/pydantic/anyio cargan submodulos de
# forma dinamica, y mcp.cli exige 'typer', que no instalamos.
uv run pyinstaller --onefile --console --clean --noconfirm \
    --name odoo-mcp \
    --collect-submodules mcp.server \
    --collect-submodules mcp.shared \
    --copy-metadata mcp \
    --collect-all pydantic \
    --collect-all anyio \
    --exclude-module mcp.cli \
    --exclude-module typer \
    --paths src \
    packaging/entry.py

EXE="dist/odoo-mcp"
[ -f "$EXE" ] || { echo "ERROR: no se genero $EXE" >&2; exit 1; }
chmod +x "$EXE"

echo "[4/4] Verificando el ejecutable..."
SALIDA="$("$EXE" --version)"

# La arquitectura la decide el Python que ejecuta PyInstaller, no la maquina:
# un Python x86_64 bajo Rosetta en un Mac arm64 genera un binario x86_64.
ARQ="$(uv run python -c 'import platform; print(platform.machine())')"
MB="$(du -m "$EXE" | cut -f1)"
if [ "$(uname -s)" = "Darwin" ]; then
    case "$ARQ" in
        arm64)  NOMBRE="odoo-mcp-mac-apple-silicon.command" ;;
        x86_64) NOMBRE="odoo-mcp-mac-intel.command" ;;
        *)      NOMBRE="odoo-mcp-mac-$ARQ.command" ;;
    esac
    cp "$EXE" "dist/$NOMBRE"
    chmod +x "dist/$NOMBRE"
    echo
    echo "  Listo: dist/$NOMBRE (${MB} MB, $ARQ) - $SALIDA"
    echo "  Doble clic instala; Claude lo usa como servidor."
else
    echo
    echo "  Listo: $EXE (${MB} MB, $ARQ) - $SALIDA"
fi
