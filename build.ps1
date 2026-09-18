# Construye dist\odoo-mcp.exe (un solo archivo, sin dependencias externas).
# Uso:  powershell -ExecutionPolicy Bypass -File build.ps1
$ErrorActionPreference = 'Continue'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

Write-Host ""
Write-Host "  Construyendo odoo-mcp.exe" -ForegroundColor Green
Write-Host "  -------------------------"

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "ERROR: falta 'uv'. Instalalo con:" -ForegroundColor Red
    Write-Host "  powershell -c ""irm https://astral.sh/uv/install.ps1 | iex"""
    exit 1
}

Write-Host "[1/4] Instalando dependencias..." -ForegroundColor Cyan
uv sync --group dev
if ($LASTEXITCODE -ne 0) { Write-Host "ERROR: fallo 'uv sync'." -ForegroundColor Red; exit 1 }

Write-Host "[2/4] Ejecutando las pruebas..." -ForegroundColor Cyan
uv run pytest -q
if ($LASTEXITCODE -ne 0) { Write-Host "ERROR: hay pruebas en rojo; no se empaqueta." -ForegroundColor Red; exit 1 }

Write-Host "[3/4] Empaquetando con PyInstaller (1-2 minutos)..." -ForegroundColor Cyan
Remove-Item -Recurse -Force (Join-Path $root 'build'), (Join-Path $root 'dist') -ErrorAction SilentlyContinue
# mcp.server / pydantic / anyio cargan submodulos de forma dinamica y el
# analisis estatico de imports no los ve. Se excluye mcp.cli: es la linea de
# comandos del SDK, exige 'typer' (un extra que no instalamos) y no la usamos.
uv run pyinstaller --onefile --console --clean --noconfirm `
    --name odoo-mcp `
    --collect-submodules mcp.server `
    --collect-submodules mcp.shared `
    --copy-metadata mcp `
    --collect-all pydantic `
    --collect-all anyio `
    --exclude-module mcp.cli `
    --exclude-module typer `
    --paths src `
    (Join-Path $root 'packaging\entry.py')
if ($LASTEXITCODE -ne 0) { Write-Host "ERROR: PyInstaller fallo." -ForegroundColor Red; exit 1 }

$exe = Join-Path $root 'dist\odoo-mcp.exe'
if (-not (Test-Path $exe)) { Write-Host "ERROR: no se genero $exe" -ForegroundColor Red; exit 1 }

Write-Host "[4/4] Verificando el ejecutable..." -ForegroundColor Cyan
$salida = & $exe --version 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: el ejecutable no arranca: $salida" -ForegroundColor Red
    exit 1
}
$mb = [math]::Round((Get-Item $exe).Length / 1MB, 1)
Write-Host ""
Write-Host "  Listo: dist\odoo-mcp.exe ($mb MB) - $salida" -ForegroundColor Green
Write-Host "  Es un unico archivo: doble clic instala, y Claude lo usa como servidor." -ForegroundColor Green
Write-Host "  Para repartirlo, manda solo dist\odoo-mcp.exe" -ForegroundColor Green
