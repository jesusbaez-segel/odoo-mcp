# Asistente de instalacion del MCP de Odoo para Claude (Windows).
# Instala odoo-mcp.exe, pide los datos de Odoo, los verifica, los guarda y
# registra el servidor en Claude Code y en Claude Desktop.
# Compatible con Windows PowerShell 5.1.
# EAP=Continue: con 'Stop', cualquier texto que un comando nativo (claude.cmd)
# escriba en stderr bajo redireccion aborta el script en PS 5.1.
$ErrorActionPreference = 'Continue'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 } catch { }
# El servidor escribe sus mensajes en UTF-8; sin esto los acentos salen rotos.
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }

$destDir  = Join-Path $env:LOCALAPPDATA 'Programs\odoo-mcp'
$destExe  = Join-Path $destDir 'odoo-mcp.exe'
$confDir  = Join-Path $env:APPDATA 'odoo-mcp'
$confFile = Join-Path $confDir 'config.env'

function Abortar($mensaje) {
    Write-Host "ERROR: $mensaje" -ForegroundColor Red
    Read-Host "Pulsa Enter para salir"
    exit 1
}

function Write-Utf8NoBom($path, $lines) {
    # Sin BOM: con BOM, tanto Claude como el propio servidor leerian mal la
    # primera clave del archivo.
    $enc = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($path, (($lines -join "`r`n") + "`r`n"), $enc)
}

Write-Host ""
Write-Host "  Instalacion del MCP de Odoo para Claude" -ForegroundColor Green
Write-Host "  ---------------------------------------"

# --- 1. Instalar el ejecutable ---------------------------------------------
Write-Host ""
Write-Host "[1/5] Instalando el servidor..." -ForegroundColor Cyan

$origen = $null
foreach ($cand in @((Join-Path $root 'odoo-mcp.exe'), (Join-Path $root 'dist\odoo-mcp.exe'))) {
    if (Test-Path $cand) { $origen = $cand; break }
}
if (-not $origen) {
    Abortar "no encuentro odoo-mcp.exe junto a este asistente. Descomprime el ZIP entero en una carpeta y vuelve a ejecutar instalar.bat."
}

if (-not (Test-Path $destDir)) { New-Item -ItemType Directory -Path $destDir -Force | Out-Null }
try {
    Copy-Item $origen $destExe -Force -ErrorAction Stop
} catch {
    Abortar "no pude copiar el servidor a $destDir. Si Claude esta abierto, cierralo y vuelve a intentarlo. ($($_.Exception.Message))"
}
Write-Host "      Instalado en $destExe"

# --- 2. Datos de Odoo --------------------------------------------------------
Write-Host "[2/5] Datos de tu Odoo" -ForegroundColor Cyan
$url = (Read-Host "      URL de tu Odoo (ej. https://miempresa.odoo.com)").Trim().TrimEnd('/')
if (-not $url) { Abortar "no escribiste ninguna URL." }
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
if (-not $db) { $db = (Read-Host "      Nombre de la base de datos").Trim() }
if (-not $db) { Abortar "hace falta el nombre de la base de datos." }

$user = (Read-Host "      Email con el que entras a Odoo").Trim()
if (-not $user) { Abortar "hace falta tu email de Odoo." }
$sec = Read-Host "      Contrasena (o API key; no se muestra al escribir)" -AsSecureString
$pass = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
    [Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec))
if (-not $pass) { Abortar "hace falta la contrasena o la API key." }

# --- 3. Verificar el acceso --------------------------------------------------
Write-Host "[3/5] Comprobando el acceso a $url ..." -ForegroundColor Cyan
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
        Abortar "email o contrasena incorrectos (o la base '$db' no es la correcta). Vuelve a ejecutar instalar.bat."
    }
} catch {
    Abortar "no pude conectar con $url : $($_.Exception.Message)"
}

# --- 4. Guardar la configuracion ---------------------------------------------
Write-Host "[4/5] Guardando tu configuracion..." -ForegroundColor Cyan
if (-not (Test-Path $confDir)) { New-Item -ItemType Directory -Path $confDir -Force | Out-Null }
Write-Utf8NoBom $confFile @(
    "# Datos de conexion a Odoo. Generado por el asistente de instalacion.",
    "ODOO_URL=$url",
    "ODOO_DB=$db",
    "ODOO_USERNAME=$user",
    "ODOO_PASSWORD=$pass"
)
# Solo el usuario actual puede leer el archivo: contiene la contrasena.
try {
    $yo = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
    $acl = Get-Acl $confFile
    $acl.SetAccessRuleProtection($true, $false)
    $acl.Access | ForEach-Object { [void]$acl.RemoveAccessRule($_) }
    $acl.AddAccessRule((New-Object System.Security.AccessControl.FileSystemAccessRule(
        $yo, 'FullControl', 'Allow')))
    Set-Acl -Path $confFile -AclObject $acl
} catch {
    Write-Host "      (aviso: no pude restringir los permisos del archivo)" -ForegroundColor Yellow
}
Write-Host "      Guardada en $confFile (solo en esta maquina)"

# --- 5. Registrar en Claude ---------------------------------------------------
Write-Host "[5/5] Configurando Claude..." -ForegroundColor Cyan

function Set-McpServerInJson($jsonPath, $exePath) {
    # Fusiona la entrada 'odoo' conservando cualquier otro servidor MCP ya
    # configurado. Devuelve 'ok', 'json-corrupto' o el texto del error.
    try {
        $dir = Split-Path -Parent $jsonPath
        if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
        $conf = $null
        if (Test-Path $jsonPath) {
            Copy-Item $jsonPath "$jsonPath.bak" -Force
            $texto = Get-Content $jsonPath -Raw
            if ($texto -and $texto.Trim()) {
                try { $conf = $texto | ConvertFrom-Json } catch { return 'json-corrupto' }
            }
        }
        if (-not $conf) { $conf = New-Object PSObject }
        if (-not ($conf.PSObject.Properties.Name -contains 'mcpServers') -or -not $conf.mcpServers) {
            $conf | Add-Member -NotePropertyName 'mcpServers' -NotePropertyValue (New-Object PSObject) -Force
        }
        $entrada = New-Object PSObject
        $entrada | Add-Member -NotePropertyName 'command' -NotePropertyValue $exePath
        $entrada | Add-Member -NotePropertyName 'args' -NotePropertyValue @()
        $conf.mcpServers | Add-Member -NotePropertyName 'odoo' -NotePropertyValue $entrada -Force
        Write-Utf8NoBom $jsonPath @($conf | ConvertTo-Json -Depth 30)
        return 'ok'
    } catch {
        return $_.Exception.Message
    }
}

$configurados = @()
$claudeCodeJson = Join-Path $env:USERPROFILE '.claude.json'

# Claude Code
$claude = Get-Command claude -ErrorAction SilentlyContinue
$codeOk = $false
if ($claude) {
    claude mcp remove odoo -s user 2>&1 | Out-Null
    claude mcp add odoo -s user -- $destExe 2>&1 | Out-Null
    if ($LASTEXITCODE -eq 0) { $codeOk = $true }
}
if (-not $codeOk -and ($claude -or (Test-Path $claudeCodeJson))) {
    $res = Set-McpServerInJson $claudeCodeJson $destExe
    if ($res -eq 'ok') { $codeOk = $true }
    else { Write-Host "      Claude Code: no pude configurarlo ($res)" -ForegroundColor Yellow }
}
if ($codeOk) {
    Write-Host "      Claude Code: configurado" -ForegroundColor Green
    $configurados += 'Claude Code'
} elseif (-not $claude -and -not (Test-Path $claudeCodeJson)) {
    Write-Host "      Claude Code: no esta instalado, lo omito"
}

# Claude Desktop
$desktopDir = Join-Path $env:APPDATA 'Claude'
if (Test-Path $desktopDir) {
    $res = Set-McpServerInJson (Join-Path $desktopDir 'claude_desktop_config.json') $destExe
    if ($res -eq 'ok') {
        Write-Host "      Claude Desktop: configurado" -ForegroundColor Green
        $configurados += 'Claude Desktop'
    } elseif ($res -eq 'json-corrupto') {
        Write-Host "      Claude Desktop: su archivo de configuracion tiene un error de formato." -ForegroundColor Yellow
        Write-Host "      No lo he tocado. Anade esto a mano en claude_desktop_config.json:"
        Write-Host ('      "odoo": { "command": "' + ($destExe -replace '\\', '\\\\') + '" }')
    } else {
        Write-Host "      Claude Desktop: no pude configurarlo ($res)" -ForegroundColor Yellow
    }
} else {
    Write-Host "      Claude Desktop: no esta instalado, lo omito"
}

# --- Comprobacion final -------------------------------------------------------
Write-Host ""
Write-Host "      Probando el servidor..." -ForegroundColor Cyan
# ToString(): el stderr de un .exe llega como ErrorRecord y al mostrarlo
# PowerShell escupe media pantalla de contexto del script.
$salida = ((& $destExe --check 2>&1) | ForEach-Object { $_.ToString() }) -join " "
if ($LASTEXITCODE -eq 0) {
    Write-Host "      $salida" -ForegroundColor Green
} else {
    Write-Host "      El servidor no pudo conectar con Odoo:" -ForegroundColor Yellow
    Write-Host "      $salida" -ForegroundColor Yellow
    Write-Host "      Vuelve a ejecutar instalar.bat y revisa los datos." -ForegroundColor Yellow
}

Write-Host ""
if ($configurados.Count -gt 0) {
    Write-Host "  Listo. Configurado en: $($configurados -join ' y ')." -ForegroundColor Green
    if ($configurados -contains 'Claude Desktop') {
        Write-Host "  Cierra Claude Desktop del todo (icono junto al reloj) y vuelve a abrirlo." -ForegroundColor Green
    }
    Write-Host ""
    Write-Host '  Luego pidele:  "muestrame mis proyectos de Odoo"' -ForegroundColor Green
} else {
    Write-Host "  No encontre ningun Claude instalado en esta maquina." -ForegroundColor Yellow
    Write-Host "  Instala Claude (claude.com), vuelve a ejecutar instalar.bat y listo."
}
Read-Host "Pulsa Enter para terminar"
