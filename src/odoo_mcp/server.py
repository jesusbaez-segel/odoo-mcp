"""Servidor MCP: wrappers finos de herramienta sobre generic.py y projects.py.

Las tools son async y delegan el trabajo bloqueante (XML-RPC) a un hilo para que
el event loop siga atendiendo el protocolo (ping, cancelaciones) mientras una
llamada a Odoo está en vuelo.
"""

from __future__ import annotations

from functools import partial
from typing import Any

from anyio import to_thread
from mcp.server.fastmcp import FastMCP

from . import generic, projects
from .client import OdooClient
from .config import load_settings

mcp = FastMCP(
    "odoo",
    instructions=(
        "Servidor MCP conectado a una instancia de Odoo. Para gestionar proyectos y "
        "tableros kanban usa las herramientas de alto nivel (list_projects, get_board, "
        "create_task, move_task, ...): aceptan nombres o ids y devuelven URLs directas "
        "a Odoo. Para cualquier otro modelo de Odoo usa la capa genérica "
        "(search_records, create_record, call_method, ...); consulta primero "
        "get_model_fields para conocer los campos."
    ),
)

_client: OdooClient | None = None


def get_client() -> OdooClient:
    global _client
    if _client is None:
        _client = OdooClient(load_settings())
    return _client


async def _run(func, *args, **kwargs):
    return await to_thread.run_sync(partial(func, *args, **kwargs))


# --- Proyectos y tableros -----------------------------------------------------


@mcp.tool()
async def list_projects(name: str | None = None, limit: int = 50):
    """Lista los proyectos de Odoo (opcionalmente filtrados por nombre), con su
    número de tareas, responsable y URL."""
    return await _run(projects.list_projects, get_client(), name=name, limit=limit)


@mcp.tool()
async def get_board(project: str | int, max_tasks: int = 200):
    """Devuelve el tablero kanban completo de un proyecto (por nombre o id):
    columnas/etapas en orden con sus tarjetas (asignados, fecha límite, prioridad).
    Si hay más tareas que max_tasks, lo indica en 'note'."""
    return await _run(projects.get_board, get_client(), project, max_tasks=max_tasks)


@mcp.tool()
async def list_tasks(
    project: str | int | None = None,
    stage: str | None = None,
    assignee: str | None = None,
    query: str | None = None,
    limit: int = 100,
):
    """Busca tareas con filtros opcionales: proyecto, etapa/columna, asignado
    (nombre o login) y texto en el título."""
    return await _run(
        projects.list_tasks,
        get_client(),
        project=project,
        stage=stage,
        assignee=assignee,
        query=query,
        limit=limit,
    )


@mcp.tool()
async def get_task(task_id: int):
    """Detalle completo de una tarea: descripción, etapa, asignados, etiquetas,
    fechas y URL."""
    return await _run(projects.get_task, get_client(), task_id)


@mcp.tool()
async def create_task(
    project: str | int,
    name: str,
    description: str | None = None,
    stage: str | None = None,
    assignees: list[str] | None = None,
    deadline: str | None = None,
    priority: str | None = None,
    tags: list[str] | None = None,
):
    """Crea una tarea en un proyecto. description admite HTML; deadline en formato
    YYYY-MM-DD; priority 'normal' o 'alta'; assignees por nombre, login o id; las
    etiquetas (tags) se crean si no existen."""
    return await _run(
        projects.create_task,
        get_client(),
        project,
        name,
        description=description,
        stage=stage,
        assignees=assignees,
        deadline=deadline,
        priority=priority,
        tags=tags,
    )


@mcp.tool()
async def update_task(
    task_id: int,
    name: str | None = None,
    description: str | None = None,
    stage: str | None = None,
    deadline: str | None = None,
    priority: str | None = None,
):
    """Actualiza campos de una tarea (solo los indicados). deadline YYYY-MM-DD;
    priority 'normal' o 'alta'; stage por nombre o id de columna."""
    return await _run(
        projects.update_task,
        get_client(),
        task_id,
        name=name,
        description=description,
        stage=stage,
        deadline=deadline,
        priority=priority,
    )


@mcp.tool()
async def move_task(task_id: int, stage: str | int):
    """Mueve una tarjeta a otra columna del tablero (etapa por nombre o id)."""
    return await _run(projects.move_task, get_client(), task_id, stage)


@mcp.tool()
async def assign_task(task_id: int, assignees: list[str], replace: bool = True):
    """Asigna usuarios a una tarea (por nombre, login o id). Con replace=False los
    añade sin quitar los actuales."""
    return await _run(projects.assign_task, get_client(), task_id, assignees, replace=replace)


@mcp.tool()
async def add_comment(task_id: int, body: str):
    """Publica un comentario en el hilo de mensajes de una tarea (admite HTML)."""
    return await _run(projects.add_comment, get_client(), task_id, body)


@mcp.tool()
async def list_stages(project: str | int):
    """Lista las columnas/etapas del tablero de un proyecto con su número de tareas."""
    return await _run(projects.list_stages, get_client(), project)


@mcp.tool()
async def create_stage(project: str | int, name: str, sequence: int | None = None):
    """Añade una columna/etapa al tablero de un proyecto. sequence controla el orden
    (menor = más a la izquierda)."""
    return await _run(projects.create_stage, get_client(), project, name, sequence=sequence)


@mcp.tool()
async def create_project(name: str, description: str | None = None):
    """Crea un proyecto nuevo. Después añade columnas con create_stage."""
    return await _run(projects.create_project, get_client(), name, description=description)


# --- Capa genérica (cualquier modelo de Odoo) ---------------------------------


@mcp.tool()
async def list_models(pattern: str | None = None, limit: int = 100):
    """Lista los modelos instalados en Odoo (nombre técnico y etiqueta), filtrables
    por texto. Ej.: pattern='sale' -> sale.order, sale.order.line, ..."""
    return await _run(generic.list_models, get_client(), pattern=pattern, limit=limit)


@mcp.tool()
async def get_model_fields(model: str):
    """Campos de un modelo con tipo, etiqueta, requerido y relación. Úsalo antes de
    crear o actualizar registros de un modelo que no conozcas."""
    return await _run(generic.get_model_fields, get_client(), model)


@mcp.tool()
async def search_records(
    model: str,
    domain: list[Any] | None = None,
    fields: list[str] | None = None,
    limit: int = 80,
    offset: int = 0,
    order: str | None = None,
):
    """Busca y lee registros de cualquier modelo con un dominio Odoo.
    Ej.: model='res.partner', domain=[["is_company","=",true]], fields=["name","email"]."""
    return await _run(
        generic.search_records,
        get_client(),
        model,
        domain=domain,
        fields=fields,
        limit=limit,
        offset=offset,
        order=order,
    )


@mcp.tool()
async def count_records(model: str, domain: list[Any] | None = None):
    """Cuenta los registros que cumplen un dominio Odoo."""
    return await _run(generic.count_records, get_client(), model, domain=domain)


@mcp.tool()
async def read_records(model: str, ids: list[int], fields: list[str] | None = None):
    """Lee registros por id. Sin fields devuelve todos los campos."""
    return await _run(generic.read_records, get_client(), model, ids, fields=fields)


@mcp.tool()
async def create_record(model: str, values: dict[str, Any]):
    """Crea un registro y devuelve su id. Para relaciones many2one pasa el id;
    para many2many usa comandos Odoo, p. ej. [[6,0,[ids]]]."""
    return await _run(generic.create_record, get_client(), model, values)


@mcp.tool()
async def update_records(model: str, ids: list[int], values: dict[str, Any]):
    """Escribe los mismos valores en todos los registros indicados."""
    return await _run(generic.update_records, get_client(), model, ids, values)


@mcp.tool()
async def delete_records(model: str, ids: list[int]):
    """Elimina registros de forma permanente. Confirma con el usuario antes de usar
    esta herramienta."""
    return await _run(generic.delete_records, get_client(), model, ids)


@mcp.tool()
async def call_method(
    model: str,
    method: str,
    args: list[Any] | None = None,
    kwargs: dict[str, Any] | None = None,
):
    """Ejecuta cualquier método público del ORM de Odoo. Para métodos de registro,
    el primer elemento de args es la lista de ids.
    Ej.: model='sale.order', method='action_confirm', args=[[42]]."""
    return await _run(generic.call_method, get_client(), model, method, args=args, kwargs=kwargs)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
