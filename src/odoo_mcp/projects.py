"""Operaciones de proyectos y tableros kanban (app Proyecto de Odoo)."""

from __future__ import annotations

from typing import Any

from .client import OdooClient, OdooError

_PRIORITY_ALIASES = {
    "0": "0",
    "normal": "0",
    "baja": "0",
    "low": "0",
    "1": "1",
    "alta": "1",
    "high": "1",
    "urgente": "1",
    "importante": "1",
}


def _priority_value(priority: str) -> str:
    key = str(priority).strip().lower()
    if key not in _PRIORITY_ALIASES:
        raise OdooError(f"Prioridad desconocida: {priority!r}. Usa 'normal' o 'alta'.")
    return _PRIORITY_ALIASES[key]


def _escape_like(value: str) -> str:
    """Escapa los comodines SQL de like/ilike para tratar el valor como literal."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _task_url(client: OdooClient, task_id: int) -> str:
    return f"{client.base_url}/web#id={task_id}&model=project.task&view_type=form"


def _project_url(client: OdooClient, project_id: int) -> str:
    return f"{client.base_url}/web#id={project_id}&model=project.project&view_type=form"


def _assignee_field(client: OdooClient) -> str:
    return "user_ids" if "user_ids" in client.fields_info("project.task") else "user_id"


def _existing_fields(client: OdooClient, model: str, wanted: list[str]) -> list[str]:
    info = client.fields_info(model)
    return [f for f in wanted if f in info]


def _resolve_by_name(
    client: OdooClient,
    model: str,
    ref: str | int,
    domain_extra: list | None = None,
    what: str = "registro",
    hint: str = "",
) -> tuple[int, str]:
    """Resuelve una referencia por id o por nombre (exacto primero, ilike después)."""
    if isinstance(ref, int) or (isinstance(ref, str) and ref.strip().isdecimal()):
        record_id = int(str(ref).strip())
        domain = [("id", "=", record_id)] + list(domain_extra or [])
        rows = client.execute(
            model,
            "search_read",
            [domain],
            {"fields": ["name"], "limit": 1, "context": {"active_test": False}},
        )
        if rows:
            return record_id, rows[0]["name"]
        if isinstance(ref, int):
            scope = " (o no pertenece al ámbito indicado)" if domain_extra else ""
            raise OdooError(f"No existe {what} con id {record_id}{scope}.{hint}")
        # Un string numérico puede ser un nombre ('2024'): probar por nombre.
    name = str(ref).strip()
    domain = list(domain_extra or []) + [("name", "ilike", name)]
    rows = client.execute(
        model, "search_read", [domain], {"fields": ["name"], "limit": 10}
    )
    exact = [r for r in rows if str(r["name"]).strip().lower() == name.lower()]
    if len(exact) == 1:
        return exact[0]["id"], exact[0]["name"]
    if len(rows) == 1:
        return rows[0]["id"], rows[0]["name"]
    if not rows:
        raise OdooError(f"No se encontró {what} llamado {name!r}.{hint}")
    options = ", ".join(f"{r['name']!r} (id {r['id']})" for r in rows)
    raise OdooError(
        f"Hay varios {what}s que coinciden con {name!r}: {options}. Usa el id."
    )


def resolve_project(client: OdooClient, project: str | int) -> tuple[int, str]:
    return _resolve_by_name(
        client,
        "project.project",
        project,
        what="proyecto",
        hint=" Usa list_projects para ver los disponibles.",
    )


def resolve_stage(client: OdooClient, project_id: int, stage: str | int) -> tuple[int, str]:
    return _resolve_by_name(
        client,
        "project.task.type",
        stage,
        domain_extra=[("project_ids", "=", project_id)],
        what="etapa",
        hint=" Usa list_stages para ver las columnas del tablero.",
    )


def resolve_user(client: OdooClient, user: str | int) -> tuple[int, str]:
    if isinstance(user, int) or (isinstance(user, str) and user.strip().isdecimal()):
        user_id = int(str(user).strip())
        rows = client.execute(
            "res.users",
            "search_read",
            [[("id", "=", user_id)]],
            {"fields": ["name"], "limit": 1, "context": {"active_test": False}},
        )
        if rows:
            return user_id, rows[0]["name"]
        if isinstance(user, int):
            raise OdooError(f"No existe el usuario con id {user_id}.")
        # Un login puramente numérico ('1234') se busca por nombre/login.
    name = str(user).strip()
    domain = ["|", ("name", "ilike", name), ("login", "ilike", name)]
    rows = client.execute(
        "res.users", "search_read", [domain], {"fields": ["name", "login"], "limit": 10}
    )
    exact = [
        r
        for r in rows
        if str(r["name"]).strip().lower() == name.lower()
        or str(r.get("login", "")).strip().lower() == name.lower()
    ]
    if len(exact) == 1:
        return exact[0]["id"], exact[0]["name"]
    if len(rows) == 1:
        return rows[0]["id"], rows[0]["name"]
    if not rows:
        raise OdooError(f"No se encontró ningún usuario llamado {name!r}.")
    options = ", ".join(f"{r['name']!r} ({r['login']}, id {r['id']})" for r in rows)
    raise OdooError(f"Hay varios usuarios que coinciden con {name!r}: {options}. Usa el id.")


def _assignee_names(client: OdooClient, tasks: list[dict], field: str) -> dict[int, str]:
    """Mapa id->nombre de los asignados que aparecen en las tareas dadas."""
    if field == "user_id":
        return {
            t["user_id"][0]: t["user_id"][1]
            for t in tasks
            if t.get("user_id")
        }
    ids = sorted({uid for t in tasks for uid in (t.get("user_ids") or [])})
    if not ids:
        return {}
    rows = client.execute("res.users", "read", [ids], {"fields": ["name"]})
    return {r["id"]: r["name"] for r in rows}


def _card(task: dict, field: str, names: dict[int, str], client: OdooClient) -> dict:
    if field == "user_id":
        assignees = [task["user_id"][1]] if task.get("user_id") else []
    else:
        assignees = [names.get(uid, f"id {uid}") for uid in (task.get("user_ids") or [])]
    card = {
        "id": task["id"],
        "name": task["name"],
        "assignees": assignees,
        "deadline": task.get("date_deadline") or None,
        "priority": "alta" if task.get("priority") == "1" else "normal",
        "url": _task_url(client, task["id"]),
    }
    if task.get("state"):
        card["state"] = task["state"]
    elif task.get("kanban_state"):
        card["state"] = task["kanban_state"]
    return card


_TASK_CARD_FIELDS = [
    "name",
    "stage_id",
    "project_id",
    "date_deadline",
    "priority",
    "sequence",
    "kanban_state",
    "state",
]


def list_projects(
    client: OdooClient, name: str | None = None, limit: int = 50
) -> list[dict]:
    domain: list = [("name", "ilike", name)] if name else []
    fields = _existing_fields(
        client, "project.project", ["name", "task_count", "user_id"]
    )
    rows = client.execute(
        "project.project",
        "search_read",
        [domain],
        {"fields": fields, "limit": limit, "order": "name"},
    )
    result = []
    for row in rows:
        item = {"id": row["id"], "name": row["name"], "url": _project_url(client, row["id"])}
        if "task_count" in row:
            item["task_count"] = row["task_count"]
        if row.get("user_id"):
            item["manager"] = row["user_id"][1]
        result.append(item)
    return result


def get_board(client: OdooClient, project: str | int, max_tasks: int = 200) -> dict:
    project_id, project_name = resolve_project(client, project)
    stages = client.execute(
        "project.task.type",
        "search_read",
        [[("project_ids", "=", project_id)]],
        {"fields": ["name", "sequence", "fold"], "order": "sequence asc, id asc"},
    )
    afield = _assignee_field(client)
    fields = _existing_fields(client, "project.task", _TASK_CARD_FIELDS + [afield])
    total = client.execute(
        "project.task", "search_count", [[("project_id", "=", project_id)]]
    )
    tasks = client.execute(
        "project.task",
        "search_read",
        [[("project_id", "=", project_id)]],
        {"fields": fields, "order": "sequence asc, id asc", "limit": max_tasks},
    )
    names = _assignee_names(client, tasks, afield)

    columns: dict[int | None, dict] = {}
    order: list[int | None] = []
    for stage in stages:
        columns[stage["id"]] = {
            "id": stage["id"],
            "name": stage["name"],
            "folded": bool(stage.get("fold")),
            "tasks": [],
        }
        order.append(stage["id"])
    for task in tasks:
        stage_ref = task.get("stage_id")
        key = stage_ref[0] if stage_ref else None
        if key not in columns:
            columns[key] = {
                "id": key,
                "name": stage_ref[1] if stage_ref else "(sin etapa)",
                "folded": False,
                "tasks": [],
            }
            order.append(key)
        columns[key]["tasks"].append(_card(task, afield, names, client))

    board = {
        "project": {
            "id": project_id,
            "name": project_name,
            "url": _project_url(client, project_id),
        },
        "total_tasks": total,
        "columns": [columns[key] for key in order],
    }
    if total > len(tasks):
        board["note"] = (
            f"Mostrando {len(tasks)} de {total} tareas; usa list_tasks con filtros "
            "para ver el resto."
        )
    return board


def list_tasks(
    client: OdooClient,
    project: str | int | None = None,
    stage: str | None = None,
    assignee: str | None = None,
    query: str | None = None,
    limit: int = 100,
) -> list[dict]:
    afield = _assignee_field(client)
    domain: list = []
    if project is not None:
        project_id, _ = resolve_project(client, project)
        domain.append(("project_id", "=", project_id))
        if stage:
            stage_id, _ = resolve_stage(client, project_id, stage)
            domain.append(("stage_id", "=", stage_id))
    elif stage:
        stage_text = str(stage).strip()
        if stage_text.isdecimal():
            domain.append(("stage_id", "=", int(stage_text)))
        else:
            domain.append(("stage_id.name", "ilike", _escape_like(stage_text)))
    if assignee:
        user_id, _ = resolve_user(client, assignee)
        domain.append((afield, "in", [user_id]))
    if query:
        domain.append(("name", "ilike", query))
    fields = _existing_fields(client, "project.task", _TASK_CARD_FIELDS + [afield])
    tasks = client.execute(
        "project.task",
        "search_read",
        [domain],
        {"fields": fields, "limit": limit, "order": "project_id asc, sequence asc, id asc"},
    )
    names = _assignee_names(client, tasks, afield)
    result = []
    for task in tasks:
        card = _card(task, afield, names, client)
        if task.get("project_id"):
            card["project"] = task["project_id"][1]
        if task.get("stage_id"):
            card["stage"] = task["stage_id"][1]
        result.append(card)
    return result


def get_task(client: OdooClient, task_id: int) -> dict:
    afield = _assignee_field(client)
    wanted = _TASK_CARD_FIELDS + [
        afield,
        "description",
        "tag_ids",
        "partner_id",
        "parent_id",
        "create_date",
        "write_date",
    ]
    fields = _existing_fields(client, "project.task", wanted)
    rows = client.execute("project.task", "read", [[task_id]], {"fields": fields})
    if not rows:
        raise OdooError(f"No existe la tarea con id {task_id}.")
    task = rows[0]
    names = _assignee_names(client, [task], afield)
    detail = _card(task, afield, names, client)
    detail["description"] = task.get("description") or None
    detail["created"] = task.get("create_date")
    detail["updated"] = task.get("write_date")
    if task.get("project_id"):
        detail["project"] = {"id": task["project_id"][0], "name": task["project_id"][1]}
    if task.get("stage_id"):
        detail["stage"] = task["stage_id"][1]
    if task.get("partner_id"):
        detail["customer"] = task["partner_id"][1]
    if task.get("parent_id"):
        detail["parent_task"] = {"id": task["parent_id"][0], "name": task["parent_id"][1]}
    tag_ids = task.get("tag_ids") or []
    if tag_ids:
        tags = client.execute("project.tags", "read", [tag_ids], {"fields": ["name"]})
        detail["tags"] = [t["name"] for t in tags]
    return detail


def _resolve_tags(client: OdooClient, tags: list[str]) -> list[int]:
    """Resuelve etiquetas por nombre exacto (sin distinguir mayúsculas), creando
    las que no existan."""
    ids = []
    for tag in tags:
        name = str(tag).strip()
        rows = client.execute(
            "project.tags",
            "search_read",
            [[("name", "ilike", _escape_like(name))]],
            {"fields": ["name"], "limit": 20},
        )
        exact = next(
            (r for r in rows if str(r["name"]).strip().lower() == name.lower()), None
        )
        if exact:
            ids.append(exact["id"])
        else:
            ids.append(client.execute("project.tags", "create", [{"name": name}]))
    return ids


def _assignee_command(client: OdooClient, assignees: list[str | int]) -> tuple[str, Any]:
    afield = _assignee_field(client)
    user_ids = [resolve_user(client, a)[0] for a in assignees]
    if afield == "user_id":
        if len(user_ids) > 1:
            raise OdooError(
                "Esta versión de Odoo solo permite un asignado por tarea; indica uno."
            )
        return afield, user_ids[0] if user_ids else False
    return afield, [(6, 0, user_ids)]


def create_task(
    client: OdooClient,
    project: str | int,
    name: str,
    description: str | None = None,
    stage: str | None = None,
    assignees: list[str] | None = None,
    deadline: str | None = None,
    priority: str | None = None,
    tags: list[str] | None = None,
) -> dict:
    project_id, project_name = resolve_project(client, project)
    values: dict[str, Any] = {"project_id": project_id, "name": name}
    if description:
        values["description"] = description
    if stage:
        values["stage_id"] = resolve_stage(client, project_id, stage)[0]
    if assignees:
        field, command = _assignee_command(client, assignees)
        values[field] = command
    if deadline:
        values["date_deadline"] = deadline
    if priority:
        values["priority"] = _priority_value(priority)
    if tags:
        values["tag_ids"] = [(6, 0, _resolve_tags(client, tags))]
    task_id = client.execute("project.task", "create", [values])
    return {
        "id": task_id,
        "name": name,
        "project": project_name,
        "url": _task_url(client, task_id),
    }


def update_task(
    client: OdooClient,
    task_id: int,
    name: str | None = None,
    description: str | None = None,
    stage: str | None = None,
    deadline: str | None = None,
    priority: str | None = None,
) -> dict:
    values: dict[str, Any] = {}
    if name is not None:
        values["name"] = name
    if description is not None:
        values["description"] = description
    if deadline is not None:
        values["date_deadline"] = deadline
    if priority is not None:
        values["priority"] = _priority_value(priority)
    if stage is not None:
        rows = client.execute(
            "project.task", "read", [[task_id]], {"fields": ["project_id"]}
        )
        if not rows:
            raise OdooError(f"No existe la tarea con id {task_id}.")
        if not rows[0].get("project_id"):
            raise OdooError(
                f"La tarea {task_id} no pertenece a ningún proyecto; no tiene tablero."
            )
        project_id = rows[0]["project_id"][0]
        values["stage_id"] = resolve_stage(client, project_id, stage)[0]
    if not values:
        raise OdooError("No se indicó ningún campo que actualizar.")
    client.execute("project.task", "write", [[task_id], values])
    return {
        "id": task_id,
        "updated": sorted(values),
        "url": _task_url(client, task_id),
    }


def move_task(client: OdooClient, task_id: int, stage: str | int) -> dict:
    rows = client.execute(
        "project.task", "read", [[task_id]], {"fields": ["name", "project_id", "stage_id"]}
    )
    if not rows:
        raise OdooError(f"No existe la tarea con id {task_id}.")
    task = rows[0]
    if not task.get("project_id"):
        raise OdooError(f"La tarea {task_id} no pertenece a ningún proyecto; no tiene tablero.")
    stage_id, stage_name = resolve_stage(client, task["project_id"][0], stage)
    client.execute("project.task", "write", [[task_id], {"stage_id": stage_id}])
    return {
        "id": task_id,
        "task": task["name"],
        "from_stage": task["stage_id"][1] if task.get("stage_id") else None,
        "to_stage": stage_name,
        "url": _task_url(client, task_id),
    }


def assign_task(
    client: OdooClient, task_id: int, assignees: list[str], replace: bool = True
) -> dict:
    afield = _assignee_field(client)
    user_pairs = [resolve_user(client, a) for a in assignees]
    user_ids = [uid for uid, _ in user_pairs]
    if afield == "user_id":
        if len(user_ids) != 1:
            raise OdooError(
                "Esta versión de Odoo solo permite un asignado por tarea; indica uno."
            )
        values: dict[str, Any] = {"user_id": user_ids[0]}
    elif replace:
        values = {"user_ids": [(6, 0, user_ids)]}
    else:
        values = {"user_ids": [(4, uid) for uid in user_ids]}
    client.execute("project.task", "write", [[task_id], values])
    return {
        "id": task_id,
        "assignees": [name for _, name in user_pairs],
        "replaced": replace,
        "url": _task_url(client, task_id),
    }


def add_comment(client: OdooClient, task_id: int, body: str) -> dict:
    kwargs: dict[str, Any] = {"body": body, "message_type": "comment"}
    major = client.server_major()
    if major and major < 14:
        kwargs["subtype"] = "mail.mt_comment"  # Odoo <=13 no conoce subtype_xmlid
    else:
        kwargs["subtype_xmlid"] = "mail.mt_comment"
    try:
        message_id = client.execute("project.task", "message_post", [[task_id]], kwargs)
    except OdooError as exc:
        # En algunas versiones el mail.message devuelto no se puede serializar
        # por XML-RPC, pero el comentario sí queda publicado.
        if "marshal" not in str(exc).lower():
            raise
        message_id = None
    return {"task_id": task_id, "message_id": message_id, "url": _task_url(client, task_id)}


def list_stages(client: OdooClient, project: str | int) -> list[dict]:
    project_id, _ = resolve_project(client, project)
    stages = client.execute(
        "project.task.type",
        "search_read",
        [[("project_ids", "=", project_id)]],
        {"fields": ["name", "sequence", "fold"], "order": "sequence asc, id asc"},
    )
    grouped = client.execute(
        "project.task",
        "read_group",
        [[("project_id", "=", project_id)], ["stage_id"], ["stage_id"]],
    )
    counts = {
        g["stage_id"][0]: g.get("stage_id_count", 0)
        for g in grouped
        if g.get("stage_id")
    }
    return [
        {
            "id": s["id"],
            "name": s["name"],
            "sequence": s["sequence"],
            "folded": bool(s.get("fold")),
            "task_count": counts.get(s["id"], 0),
        }
        for s in stages
    ]


def create_stage(
    client: OdooClient, project: str | int, name: str, sequence: int | None = None
) -> dict:
    project_id, project_name = resolve_project(client, project)
    values: dict[str, Any] = {"name": name, "project_ids": [(4, project_id)]}
    if sequence is not None:
        values["sequence"] = sequence
    stage_id = client.execute("project.task.type", "create", [values])
    return {"id": stage_id, "name": name, "project": project_name}


def create_project(client: OdooClient, name: str, description: str | None = None) -> dict:
    values: dict[str, Any] = {"name": name}
    if description:
        values["description"] = description
    project_id = client.execute("project.project", "create", [values])
    return {
        "id": project_id,
        "name": name,
        "url": _project_url(client, project_id),
        "note": "Proyecto creado. Añade columnas al tablero con create_stage.",
    }
