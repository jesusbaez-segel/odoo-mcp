# odoo-mcp

Servidor MCP local (dockerizado) que conecta Claude con tu instancia de Odoo.
Pensado para **gestionar proyectos y tableros kanban** (crear/mover/asignar tareas,
comentar, gestionar columnas…) y, además, con una capa genérica para operar sobre
**cualquier modelo de Odoo** (clientes, ventas, facturas…).

Compatible con Odoo 13–18 self-hosted y Odoo.sh (detecta las diferencias de versión
en tiempo de ejecución). Nota: Odoo 13 no tiene API keys; usa `ODOO_PASSWORD`.

## Requisitos

- Docker
- Una instancia de Odoo accesible y una **API key** de tu usuario
  (en Odoo: *Preferencias → Seguridad de la cuenta → Claves API → Nueva clave*)

## Instalación

1. Construye la imagen:

   ```bash
   docker build -t odoo-mcp .
   ```

2. Crea tu configuración:

   ```bash
   cp .env.example .env
   # edita .env con tu URL, base de datos, usuario y API key
   ```

3. Registra el servidor en Claude:

   - **Claude Code**: este repositorio ya incluye `.mcp.json`; abre Claude Code en
     esta carpeta y aprueba el servidor. Para usarlo desde cualquier carpeta
     (sustituye `<RUTA-DEL-PROYECTO>` por la ruta absoluta de tu copia de este
     repositorio; en Windows usa barras normales, p. ej. `C:/proyectos/mcpOdoo`):

     ```bash
     claude mcp add odoo -s user -- docker run -i --rm --env-file <RUTA-DEL-PROYECTO>/.env --add-host=host.docker.internal:host-gateway odoo-mcp
     ```

   - **Claude Desktop**: añade a `claude_desktop_config.json` (misma nota sobre
     `<RUTA-DEL-PROYECTO>`):

     ```json
     {
       "mcpServers": {
         "odoo": {
           "command": "docker",
           "args": [
             "run", "-i", "--rm",
             "--env-file", "<RUTA-DEL-PROYECTO>/.env",
             "--add-host=host.docker.internal:host-gateway",
             "odoo-mcp"
           ]
         }
       }
     }
     ```

> **Odoo en localhost:** si `ODOO_URL` apunta a `localhost`/`127.0.0.1`, el servidor
> la reescribe automáticamente a `host.docker.internal` dentro del contenedor (el
> flag `--add-host` del comando lo hace funcionar también en Linux).

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

## Desarrollo (sin Docker)

```bash
uv sync            # instala dependencias
uv run pytest      # ejecuta las pruebas
uv run odoo-mcp    # arranca el servidor por stdio (requiere variables ODOO_*)
```

## Variables de entorno

| Variable | Descripción |
|---|---|
| `ODOO_URL` | URL base, p. ej. `https://odoo.miempresa.com` o `http://localhost:8069` |
| `ODOO_DB` | Nombre de la base de datos |
| `ODOO_USERNAME` | Usuario (email de login) |
| `ODOO_API_KEY` | API key (o usa `ODOO_PASSWORD`) |
