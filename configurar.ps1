# Asistente de configuracion del MCP de Odoo (Windows).
# Pide URL, email y contrasena, los verifica contra Odoo, guarda el .env y
# registra el servidor en Claude Code. Compatible con Windows PowerShell 5.1.
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host ""
Write-Host "  Asistente de configuracion del MCP de Odoo" -ForegroundColor Green
Write-Host "  ------------------------------------------"

# --- 1. Docker -----------------------------------------------------------
Write-Host ""
Write-Host "[1/5] Comprobando Docker..." -ForegroundColor Cyan
docker info *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Docker no responde. Instala Docker Desktop (docker.com), abrelo," -ForegroundColor Red
    Write-Host "espera a que arranque y vuelve a ejecutar este asistente." -ForegroundColor Red
    Read-Host "Pulsa Enter para salir"
    exit 1
}
Write-Host "      Docker OK"

# --- 2. Imagen del servidor ----------------------------------------------
Write-Host "[2/5] Comprobando la imagen odoo-mcp..." -ForegroundColor Cyan
docker image inspect odoo-mcp *> $null
if ($LASTEXITCODE -ne 0) {
    if (Test-Path (Join-Path $root 'odoo-mcp.tar.gz')) {
        Write-Host "      Cargando imagen desde odoo-mcp.tar.gz (1-2 minutos)..."
        docker load -i (Join-Path $root 'odoo-mcp.tar.gz')
    } elseif (Test-Path (Join-Path $root 'Dockerfile')) {
        Write-Host "      Construyendo la imagen..."
        docker build -t odoo-mcp $root
    } else {
        Write-Host "ERROR: no encuentro ni odoo-mcp.tar.gz ni Dockerfile junto a este script." -ForegroundColor Red
        Read-Host "Pulsa Enter para salir"
        exit 1
    }
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR: no se pudo preparar la imagen." -ForegroundColor Red
        Read-Host "Pulsa Enter para salir"
        exit 1
    }
} else {
    Write-Host "      Imagen ya cargada"
}

# --- 3. Datos de Odoo ------------------------------------------------------
Write-Host "[3/5] Datos de tu Odoo" -ForegroundColor Cyan
$url = (Read-Host "      URL de tu Odoo (ej. https://miempresa.odoo.com)").Trim().TrimEnd('/')
if ($url -notmatch '^https?://') { $url = "https://$url" }

$db = $null
try {
    $resp = Invoke-RestMethod -Method Post -Uri "$url/web/database/list" `
        -ContentType 'application/json' `
        -Body '{"jsonrpc":"2.0","method":"call","params":{}}' -TimeoutSec 10
    $dbs = @($resp.result)
    if ($dbs.Count -eq 1) {
        $db = $dbs[0]
        Write-Host "      Base de datos detectada: $db"
    } elseif ($dbs.Count -gt 1) {
        Write-Host "      Bases disponibles: $($dbs -join ', ')"
        $db = Read-Host "      Cual usar"
    }
} catch { }
if (-not $db) { $db = Read-Host "      Nombre de la base de datos" }

$user = (Read-Host "      Email con el que entras a Odoo").Trim()
$sec = Read-Host "      Contrasena (o API key; no se muestra al escribir)" -AsSecureString
$pass = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
    [Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec))

# --- 4. Verificar el acceso ------------------------------------------------
Write-Host "[4/5] Comprobando el acceso a $url ..." -ForegroundColor Cyan
function Escape-Xml([string]$s) {
    ($s -replace '&', '&amp;') -replace '<', '&lt;' -replace '>', '&gt;'
}
$body = '<?xml version="1.0"?><methodCall><methodName>authenticate</methodName><params>' +
    "<param><value><string>$(Escape-Xml $db)</string></value></param>" +
    "<param><value><string>$(Escape-Xml $user)</string></value></param>" +
    "<param><value><string>$(Escape-Xml $pass)</string></value></param>" +
    '<param><value><struct/></value></param></params></methodCall>'
try {
    $r = Invoke-WebRequest -Method Post -Uri "$url/xmlrpc/2/common" `
        -ContentType 'text/xml' -Body $body -TimeoutSec 20 -UseBasicParsing
    if ($r.Content -match '<(int|i4)>(\d+)</') {
        Write-Host "      Acceso verificado correctamente." -ForegroundColor Green
    } else {
        Write-Host "ERROR: email o contrasena incorrectos (o la base '$db' no es la correcta)." -ForegroundColor Red
        Read-Host "Pulsa Enter para salir y vuelve a intentarlo"
        exit 1
    }
} catch {
    Write-Host "ERROR: no pude conectar con $url : $($_.Exception.Message)" -ForegroundColor Red
    Read-Host "Pulsa Enter para salir"
    exit 1
}

# --- 5. Guardar y registrar en Claude --------------------------------------
Write-Host "[5/5] Guardando configuracion..." -ForegroundColor Cyan
$envPath = Join-Path $root '.env'
# WriteAllLines escribe UTF-8 sin BOM; con BOM, docker --env-file corrompe la primera variable
[System.IO.File]::WriteAllLines($envPath, @(
    "ODOO_URL=$url",
    "ODOO_DB=$db",
    "ODOO_USERNAME=$user",
    "ODOO_PASSWORD=$pass"
))
Write-Host "      Guardado en $envPath (queda solo en esta maquina)"

$claude = Get-Command claude -ErrorAction SilentlyContinue
if ($claude) {
    claude mcp remove odoo -s user *> $null
    claude mcp add odoo -s user -- docker run -i --rm --env-file "$envPath" --add-host=host.docker.internal:host-gateway odoo-mcp
    if ($LASTEXITCODE -eq 0) {
        Write-Host "      Servidor 'odoo' registrado en Claude Code." -ForegroundColor Green
    } else {
        Write-Host "      No pude registrarlo automaticamente; hazlo a mano (ver README.md)." -ForegroundColor Yellow
    }
} else {
    Write-Host "      No encontre Claude Code en esta maquina." -ForegroundColor Yellow
    Write-Host "      Si usas Claude Desktop, anade a claude_desktop_config.json:"
    Write-Host ('      {"mcpServers":{"odoo":{"command":"docker","args":["run","-i","--rm","--env-file","' + ($envPath -replace '\\', '/') + '","--add-host=host.docker.internal:host-gateway","odoo-mcp"]}}}')
}

Write-Host ""
Write-Host "  Listo. Abre (o reinicia) Claude y pide:" -ForegroundColor Green
Write-Host '  "muestrame mis proyectos de Odoo"' -ForegroundColor Green
Read-Host "Pulsa Enter para terminar"
