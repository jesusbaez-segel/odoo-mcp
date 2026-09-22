# odoo-mcp

Servidor MCP local que conecta Claude con tu instancia de Odoo. Pensado para
**gestionar proyectos y tableros kanban** (crear/mover/asignar tareas, comentar,
gestionar columnas…) y, además, con una capa genérica para operar sobre
**cualquier modelo de Odoo** (clientes, ventas, facturas…).

Compatible con Odoo 13–18 self-hosted y Odoo.sh (detecta las diferencias de versión
en tiempo de ejecución). Nota: Odoo 13 no tiene API keys; usa la contraseña.

## Instalación (Windows)

**Un solo archivo, y ningún requisito.** No hace falta Docker, ni Python, ni Node.
Solo tener Claude Code o Claude Desktop.

1. Doble clic en **`odoo-mcp.exe`**.
2. Responde tres preguntas: URL de tu Odoo, tu email y tu contraseña (o API key).

Ya está. El asistente se instala solo, detecta el nombre de la base de datos,
verifica el acceso contra Odoo, guarda tus datos y **registra el servidor en Claude
Code y en Claude Desktop a la vez**. Después abre Claude y pide:
*«muéstrame mis proyectos de Odoo»*.

El mismo archivo es el instalador y el servidor: cuando lo abres tú con doble clic
(hay una consola detrás) hace de asistente; cuando lo lanza Claude (con la entrada
conectada a una tubería) hace de servidor MCP.

Si vuelves a abrirlo cuando ya está instalado, sale un menú: reconfigurar,
comprobar la conexión, desinstalar o salir.

## Instalación (macOS)

Igual de simple, con un archivo distinto según el chip del Mac:

| Mac | Archivo |
|---|---|
| Chip Apple (M1–M4) | `odoo-mcp-mac-apple-silicon.command` |
| Intel | `odoo-mcp-mac-intel.command` |

En el menú Apple → *Acerca de este Mac* pone cuál es.

1. Doble clic en el archivo. **La primera vez macOS lo bloqueará** porque no está
   firmado: cierra el aviso, haz **clic derecho sobre el archivo → Abrir → Abrir**.
   Solo hace falta una vez.
2. Responde las tres preguntas de siempre.

Dónde deja las cosas en Mac:

| Qué | Dónde |
|---|---|
| El servidor | `~/Library/Application Support/odoo-mcp/odoo-mcp` |
| Tus datos de Odoo | `~/Library/Application Support/odoo-mcp/config.env` (permisos 600) |
| Registro en Claude Code | `~/.claude.json` |
| Registro en Claude Desktop | `~/Library/Application Support/Claude/claude_desktop_config.json` |

El asistente le quita al ejecutable la marca de cuarentena (`com.apple.quarantine`)
al instalarlo. Sin eso, Gatekeeper impediría que Claude arrancase el servidor
aunque tú ya hubieras autorizado el archivo original.

### Cómo pasárselo a otra persona

Mándale **un solo archivo** (~20 MB, por Drive, USB o lo que sea): el `.exe` si
usa Windows, o el `.command` que corresponda a su Mac. Doble clic y el asistente
le pide **sus** datos de Odoo.

Ni WhatsApp ni Gmail dejan adjuntar `.exe`: mételo en un ZIP o usa Drive.

⚠️ No compartas nunca tu archivo `config.env` (en `%APPDATA%\odoo-mcp\` o en
`~/Library/Application Support/odoo-mcp/`): contiene tu contraseña. El ejecutable
no la lleva dentro.

### Dónde deja las cosas (Windows)

| Qué | Dónde |
|---|---|
| El servidor | `%LOCALAPPDATA%\Programs\odoo-mcp\odoo-mcp.exe` |
| Tus datos de Odoo | `%APPDATA%\odoo-mcp\config.env` (solo tu usuario puede leerlo) |
| Registro en Claude Code | `%USERPROFILE%\.claude.json` |
| Registro en Claude Desktop (clásico) | `%APPDATA%\Claude\claude_desktop_config.json` |
| Registro en Claude Desktop (Microsoft Store) | `%LOCALAPPDATA%\Packages\Claude_*\LocalCache\Roaming\Claude\claude_desktop_config.json` |

Claude Desktop guarda su configuración en un sitio u otro según cómo se haya
instalado; el asistente busca en los dos. Si ya tenías otros servidores MCP, se
conservan: **fusiona** su entrada en esos archivos en vez de sobrescribirlos, y
deja una copia `.bak` antes de tocarlos.

### Si algo falla

Ejecuta esto y te dirá si conecta y con qué usuario, o cuál es el error exacto:

```
:: Windows (en una ventana de comandos)
%LOCALAPPDATA%\Programs\odoo-mcp\odoo-mcp.exe --check
```

```bash
# macOS (en Terminal)
~/Library/Application\ Support/odoo-mcp/odoo-mcp --check
```

## Herramientas

**Proyectos y tableros** — `list_projects`, `get_board` (tablero completo por
columnas), `list_tasks`, `get_task`, `create_task`, `update_task`, `move_task`
(mover tarjeta de columna), `assign_task`, `add_comment`, `list_stages`,
`create_stage`, `create_project`. Aceptan nombres o ids (proyectos, etapas,
usuarios) y devuelven URLs directas a Odoo.

**Genéricas (cualquier modelo)** — `list_models`, `get_model_fields`,
`search_records`, `count_records`, `read_records`, `create_record`,
`update_records`, `delete_records`, `call_method` (cualquier método del ORM:
confirmar pedidos, validar facturas…).

Ejemplos de peticiones a Claude:

- «Muéstrame el tablero del proyecto Web Corporativa»
- «Crea una tarea "Migrar servidor" en Infraestructura, asígnasela a Ana con
  prioridad alta para el viernes»
- «Mueve la tarea 214 a En curso y comenta que ya está desplegada»
- «¿Cuántas facturas quedan por validar? Valídalas»

## Argumentos del ejecutable

| Argumento | Qué hace |
|---|---|
| *(ninguno)* | Decide solo: doble clic → asistente; lanzado por Claude → servidor |
| `--mcp` | Fuerza el servidor MCP por stdio (es lo que se registra en Claude) |
| `--instalar` | Fuerza el asistente de instalación |
| `--registrar` | Vuelve a registrarlo en Claude sin volver a pedir los datos |
| `--menu` | Abre el menú (registrar, reconfigurar, comprobar, desinstalar) |
| `--desinstalar` | Lo quita de Claude y borra la instalación |
| `--check` | Comprueba la conexión con Odoo y sale |
| `--version`, `--help` | Lo que parece |

## Desarrollo

```bash
uv sync                  # instala dependencias
uv run pytest            # ejecuta las pruebas
uv run odoo-mcp --check  # comprueba la conexión con Odoo
uv run odoo-mcp --mcp    # arranca el servidor por stdio
```

Copia `.env.example` a `.env` con tus datos: en desarrollo el servidor lo lee del
directorio actual. Este repositorio incluye `.mcp.json`, así que Claude Code
ejecuta el servidor desde el código fuente al abrirlo en esta carpeta.

Para generar los ejecutables que se reparten:

```
powershell -ExecutionPolicy Bypass -File build.ps1   # en Windows -> dist\odoo-mcp.exe
./build.sh                                           # en macOS   -> dist/odoo-mcp-mac-*.command
```

Ambos instalan dependencias, pasan las pruebas, empaquetan con PyInstaller y
verifican el binario resultante.

**PyInstaller no cruza plataformas**: el ejecutable de cada sistema hay que
compilarlo en ese sistema. Para no necesitar un Mac, `.github/workflows/build.yml`
los construye los tres en GitHub Actions (Windows, Mac Apple Silicon en `macos-14`
y Mac Intel en `macos-13`). Se lanza desde *Actions → Construir ejecutables → Run
workflow*, o publicando una etiqueta `vX.Y.Z`, que además los adjunta a la Release.

## Configuración

El servidor busca sus datos en este orden (gana el primero que exista):

1. Variables de entorno del proceso (`ODOO_URL`, `ODOO_DB`, …). Siempre tienen
   prioridad sobre el archivo.
2. La ruta que indique `ODOO_MCP_CONFIG`.
3. Lo que escribe el asistente: `%APPDATA%\odoo-mcp\config.env` en Windows,
   `~/Library/Application Support/odoo-mcp/config.env` en macOS.
4. `.env` en el directorio actual — comodidad al desarrollar.

| Variable | Descripción |
|---|---|
| `ODOO_URL` | URL base, p. ej. `https://odoo.miempresa.com` o `http://localhost:8069` |
| `ODOO_DB` | Nombre de la base de datos |
| `ODOO_USERNAME` | Usuario (email de login) |
| `ODOO_API_KEY` | API key (o usa `ODOO_PASSWORD`) |
| `ODOO_TIMEOUT` | Segundos de espera por llamada (60 por defecto) |

La API key se genera en Odoo: *Preferencias → Seguridad de la cuenta → Claves API
→ Nueva clave*.
