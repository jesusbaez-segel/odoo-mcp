# Desinstala el MCP de Odoo: lo quita de Claude Code y Claude Desktop, borra el
# ejecutable y pregunta si borrar tambien las credenciales guardadas.
$ErrorActionPreference = 'Continue'

$destDir  = Join-Path $env:LOCALAPPDATA 'Programs\odoo-mcp'
$confDir  = Join-Path $env:APPDATA 'odoo-mcp'

function Write-Utf8NoBom($path, $texto) {
    $enc = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($path, $texto, $enc)
}

function Remove-McpServerFromJson($jsonPath) {
    if (-not (Test-Path $jsonPath)) { return $false }
    try {
        $texto = Get-Content $jsonPath -Raw
        if (-not $texto -or -not $texto.Trim()) { return $false }
        $conf = $texto | ConvertFrom-Json
        if (-not $conf.mcpServers -or -not ($conf.mcpServers.PSObject.Properties.Name -contains 'odoo')) {
            return $false
        }
        Copy-Item $jsonPath "$jsonPath.bak" -Force
        $conf.mcpServers.PSObject.Properties.Remove('odoo')
        Write-Utf8NoBom $jsonPath ($conf | ConvertTo-Json -Depth 30)
        return $true
    } catch {
        return $false
    }
}

Write-Host ""
Write-Host "  Desinstalar el MCP de Odoo" -ForegroundColor Yellow
Write-Host "  --------------------------"
Write-Host ""

# Claude Code
$claude = Get-Command claude -ErrorAction SilentlyContinue
$quitadoCode = $false
if ($claude) {
    claude mcp remove odoo -s user 2>&1 | Out-Null
    if ($LASTEXITCODE -eq 0) { $quitadoCode = $true }
}
if (-not $quitadoCode) {
    $quitadoCode = Remove-McpServerFromJson (Join-Path $env:USERPROFILE '.claude.json')
}
if ($quitadoCode) { Write-Host "  Quitado de Claude Code" } else { Write-Host "  Claude Code: no estaba configurado" }

# Claude Desktop
if (Remove-McpServerFromJson (Join-Path $env:APPDATA 'Claude\claude_desktop_config.json')) {
    Write-Host "  Quitado de Claude Desktop"
} else {
    Write-Host "  Claude Desktop: no estaba configurado"
}

# Ejecutable
if (Test-Path $destDir) {
    try {
        Remove-Item -Recurse -Force $destDir -ErrorAction Stop
        Write-Host "  Borrado $destDir"
    } catch {
        Write-Host "  No pude borrar $destDir (cierra Claude y reintenta)" -ForegroundColor Yellow
    }
}

# Credenciales
if (Test-Path $confDir) {
    Write-Host ""
    $r = Read-Host "  Borrar tambien tus datos de conexion a Odoo? (s/N)"
    if ($r -match '^[sSyY]') {
        Remove-Item -Recurse -Force $confDir -ErrorAction SilentlyContinue
        Write-Host "  Credenciales borradas"
    } else {
        Write-Host "  Credenciales conservadas en $confDir"
    }
}

Write-Host ""
Write-Host "  Listo. Reinicia Claude para que deje de verlo." -ForegroundColor Green
Read-Host "Pulsa Enter para terminar"
