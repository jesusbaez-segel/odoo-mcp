# Diseño: `odoo-mcp` — Servidor MCP local dockerizado para Odoo

**Fecha:** 2026-07-08
**Estado:** Aprobado por el usuario

## Objetivo

Un servidor MCP local, empaquetado en Docker, que conecta Claude (Code/Desktop) con una
instancia de Odoo self-hosted/Odoo.sh y permite **hacer todo lo que se le pida de Odoo**,
con la **gestión de proyectos y tableros kanban** como caso de uso principal.

## Decisiones

| Tema | Decisión | Razón |
|---|---|---|
| Lenguaje/SDK | Python 3.12 + `mcp` (FastMCP) | SDK oficial; Python es el lenguaje del ecosistema Odoo |
| Transporte | stdio (`docker run -i`) | Es lo que usan Claude Code y Claude Desktop |
| Conexión | API externa XML-RPC (`xmlrpc.client`, stdlib) | Estándar de Odoo, sin dependencias extra, funciona en self-hosted y Odoo.sh |
| Autenticación | `ODOO_URL`, `ODOO_DB`, `ODOO_USERNAME`, `ODOO_API_KEY` por `.env` | Dentro de Docker no se puede abrir el navegador del host para login interactivo; la API key se genera una vez en Odoo (Preferencias → Seguridad de la cuenta → Claves API) |
| "Ver la web" | Las herramientas devuelven URLs directas a tareas/proyectos | Claude Code abre el navegador del host de forma nativa (claude-in-chrome); no necesita ir dentro del MCP |
| Compatibilidad | Detección de campos en tiempo de ejecución (`fields_get` cacheado) | Soporta Odoo 14–18: `user_ids` vs `user_id`, `state` vs `kanban_state`, etc. |
| Docker + localhost | Reescritura automática `localhost` → `host.docker.internal` dentro del contenedor | Si Odoo corre en la misma máquina, la URL del host no es alcanzable desde el contenedor |

## Herramientas MCP

### Capa de proyectos y tableros (caso principal)

| Herramienta | Descripción |
|---|---|
| `list_projects(name?)` | Lista proyectos con nº de tareas y responsable |
| `get_board(project)` | Tablero kanban completo: columnas (etapas) con sus tarjetas |
| `list_tasks(project?, stage?, assignee?, query?)` | Búsqueda de tareas con filtros |
| `get_task(task_id)` | Detalle completo de una tarea |
| `create_task(project, name, …)` | Crea tarea (etapa, asignados, fecha límite, prioridad, etiquetas) |
| `update_task(task_id, …)` | Modifica campos de una tarea |
| `move_task(task_id, stage)` | Mueve la tarjeta a otra columna del tablero |
| `assign_task(task_id, assignees)` | Asigna usuarios (por nombre, login o id) |
| `add_comment(task_id, body)` | Comenta en el hilo de la tarea |
| `list_stages(project)` | Columnas del tablero con recuento de tareas |
| `create_stage(project, name)` | Añade una columna al tablero |
| `create_project(name)` | Crea un proyecto |

Los nombres (proyecto, etapa, usuario) se resuelven con coincidencia exacta primero e
`ilike` después; ante ambigüedad se devuelve un error con los candidatos.

### Capa genérica (todo lo demás de Odoo)

| Herramienta | Descripción |
|---|---|
| `list_models(pattern?)` | Modelos instalados (`ir.model`) |
| `get_model_fields(model)` | Campos de un modelo (`fields_get`) |
| `search_records(model, domain, fields, …)` | `search_read` con dominio Odoo |
| `count_records(model, domain)` | `search_count` |
| `read_records(model, ids, fields?)` | Lectura por IDs |
| `create_record(model, values)` | Crea un registro |
| `update_records(model, ids, values)` | Actualiza registros |
| `delete_records(model, ids)` | Elimina registros |
| `call_method(model, method, args, kwargs)` | Cualquier método del ORM (confirmar pedido, validar factura, …) |

## Arquitectura

```
src/odoo_mcp/
  config.py    # Settings desde env; ajuste localhost→host.docker.internal
  client.py    # OdooClient: XML-RPC, auth perezosa (uid cacheado), fields_info cacheado
  generic.py   # Operaciones genéricas (funciones puras que reciben el cliente)
  projects.py  # Operaciones de proyectos/tableros (reciben el cliente)
  server.py    # FastMCP: wrappers finos de herramienta → función + get_client()
tests/         # pytest con cliente falso (sin Odoo real)
Dockerfile     # python:3.12-slim + pip install .
.mcp.json      # registro del servidor vía docker run para Claude Code
```

La separación función-con-cliente / wrapper-MCP permite probar toda la lógica sin
levantar el protocolo MCP ni un Odoo real.

## Manejo de errores

- Variables de entorno faltantes → error claro al usar la primera herramienta (el
  servidor arranca igualmente para que `tools/list` funcione).
- `xmlrpc.client.Fault` → se extrae el mensaje final del traceback del servidor y se
  devuelve como `OdooError` legible.
- Referencias ambiguas o inexistentes (proyecto/etapa/usuario) → error con candidatos.

## Pruebas

`pytest` con un `FakeClient` inyectado: agrupación del tablero, resolución de
etapas/usuarios/proyectos, fallback `user_ids`/`user_id`, mapeo de prioridades,
limpieza de faults, configuración. Prueba de humo real contra la instancia del usuario
cuando aporte credenciales.

## Fuera de alcance (YAGNI)

- Transporte HTTP/SSE, multi-instancia, caché de datos, login interactivo por navegador
  (incompatible con contenedor headless), herramientas de otros módulos de negocio
  (se cubren con `call_method`/CRUD genérico).
