# odoo-mcp

Servidor MCP local que conecta Claude con tu instancia de Odoo. Pensado para
**gestionar proyectos y tableros kanban** (crear/mover/asignar tareas, comentar,
gestionar columnas…) y, además, con una capa genérica para operar sobre
**cualquier modelo de Odoo** (clientes, ventas, facturas…).

Compatible con Odoo 13–18 self-hosted y Odoo.sh (detecta las diferencias de versión
en tiempo de ejecución). Nota: Odoo 13 no tiene API keys; usa la contraseña.

## Instalación (Windows)

**Requisitos: ninguno.** No hace falta Docker, ni Python, ni Node. Solo tener
Claude Code o Claude Desktop instalado.

1. Descomprime el ZIP en una carpeta.
2. Doble clic en **`instalar.bat`**.
3. Responde tres preguntas: URL de tu Odoo, tu email y tu contraseña.

El asistente instala el servidor, detecta solo el nombre de la base de datos,
verifica el acceso, guarda tus datos y **registra el servidor en Claude Code y en
Claude Desktop a la vez**. Al terminar, abre Claude y pide:
*«muéstrame mis proyectos de Odoo»*.

Dónde deja las cosas:

| Qué | Dónde |
|---|---|
| El servidor | `%LOCALAPPDATA%\Programs\odoo-mcp\odoo-mcp.exe` |
| Tus datos de Odoo | `%APPDATA%\odoo-mcp\config.env` (solo tu usuario puede leerlo) |
| Registro en Claude Code | `%USERPROFILE%\.claude.json` |
| Registro en Claude Desktop | `%APPDATA%\Claude\claude_desktop_config.json` |

Si ya tenías otros servidores MCP configurados, se conservan: el asistente
**fusiona** su entrada en esos archivos en vez de sobrescribirlos, y deja una copia
`.bak` antes de tocarlos.

### Cómo pasárselo a otra persona

Comprime y comparte estos cuatro archivos:

1. `odoo-mcp.exe` (el servidor, ~20 MB — lo genera `build.ps1` en `dist\`)
2. `instalar.bat`
3. `configurar.ps1`
4. `desinstalar.bat` y `desinstalar.ps1` (opcional pero recomendable)

La otra persona los pone en una carpeta, hace doble clic en `instalar.bat` y el
asistente le pide **sus** datos de Odoo.

⚠️ No compartas tu `%APPDATA%\odoo-mcp\config.env`: contiene tu contraseña.

### Desinstalar

Doble clic en `desinstalar.bat`: quita el servidor de ambos Claude, borra el
ejecutable y pregunta si borrar también tus credenciales.

### Si algo falla

Ejecuta esto en una terminal para ver qué ocurre:

```
%LOCALAPPDATA%\Programs\odoo-mcp\odoo-mcp.exe --check
```

Te dirá si conecta y con qué usuario, o cuál es el error exacto.

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

## Desarrollo

```bash
uv sync                  # instala dependencias
uv run pytest            # ejecuta las pruebas
uv run odoo-mcp --check  # comprueba la conexión con Odoo
uv run odoo-mcp          # arranca el servidor por stdio
```

Copia `.env.example` a `.env` con tus datos: en desarrollo el servidor lo lee del
directorio actual. Este repositorio incluye `.mcp.json`, así que Claude Code
ejecuta el servidor desde el código fuente al abrirlo en esta carpeta.

Para generar el ejecutable que se reparte:

```
powershell -ExecutionPolicy Bypass -File build.ps1
```

Instala dependencias, pasa las pruebas, empaqueta con PyInstaller y verifica el
binario. Deja `dist\odoo-mcp.exe`.

## Configuración

El servidor busca sus datos en este orden (gana el primero que exista):

1. Variables de entorno del proceso (`ODOO_URL`, `ODOO_DB`, …). Siempre tienen
   prioridad sobre el archivo.
2. La ruta que indique `ODOO_MCP_CONFIG`.
3. `%APPDATA%\odoo-mcp\config.env` — lo que escribe el asistente.
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
