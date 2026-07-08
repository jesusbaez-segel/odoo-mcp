import pytest

from odoo_mcp import projects
from odoo_mcp.client import OdooError

from fakes import LEGACY_TASK_FIELDS, MODERN_TASK_FIELDS, FakeClient

PROJECT_ROWS = [{"id": 10, "name": "Web Corporativa"}]
STAGE_ROWS = [
    {"id": 1, "name": "Por hacer", "sequence": 1, "fold": False},
    {"id": 2, "name": "En curso", "sequence": 2, "fold": False},
    {"id": 3, "name": "Hecho", "sequence": 3, "fold": True},
]


def board_client(task_rows, fields=MODERN_TASK_FIELDS):
    return FakeClient(
        {
            ("project.project", "search_read"): PROJECT_ROWS,
            ("project.project", "read"): PROJECT_ROWS,
            ("project.task.type", "search_read"): STAGE_ROWS,
            ("project.task", "search_count"): len(task_rows),
            ("project.task", "search_read"): task_rows,
            ("res.users", "read"): [
                {"id": 5, "name": "Ana"},
                {"id": 6, "name": "Luis"},
            ],
        },
        fields=fields,
    )


def test_get_board_agrupa_por_columna_en_orden():
    tasks = [
        {
            "id": 100,
            "name": "Diseñar portada",
            "stage_id": [2, "En curso"],
            "user_ids": [5],
            "date_deadline": "2026-07-15",
            "priority": "1",
            "state": "01_in_progress",
        },
        {
            "id": 101,
            "name": "Configurar dominio",
            "stage_id": [1, "Por hacer"],
            "user_ids": [],
            "date_deadline": False,
            "priority": "0",
        },
        {
            "id": 102,
            "name": "Tarea suelta",
            "stage_id": False,
            "user_ids": [5, 6],
            "priority": "0",
        },
    ]
    board = projects.get_board(board_client(tasks), "Web Corporativa")

    assert board["project"]["id"] == 10
    assert board["total_tasks"] == 3
    names = [c["name"] for c in board["columns"]]
    assert names == ["Por hacer", "En curso", "Hecho", "(sin etapa)"]

    en_curso = board["columns"][1]
    assert [t["id"] for t in en_curso["tasks"]] == [100]
    card = en_curso["tasks"][0]
    assert card["assignees"] == ["Ana"]
    assert card["deadline"] == "2026-07-15"
    assert card["priority"] == "alta"
    assert card["state"] == "01_in_progress"
    assert card["url"] == "http://odoo.test/web#id=100&model=project.task&view_type=form"

    sin_etapa = board["columns"][3]
    assert sin_etapa["tasks"][0]["assignees"] == ["Ana", "Luis"]
    assert board["columns"][2]["folded"] is True


def test_get_board_version_antigua_usa_user_id():
    tasks = [
        {
            "id": 100,
            "name": "Tarea vieja",
            "stage_id": [1, "Por hacer"],
            "user_id": [5, "Ana"],
            "priority": "0",
            "kanban_state": "blocked",
        }
    ]
    client = board_client(tasks, fields=LEGACY_TASK_FIELDS)
    board = projects.get_board(client, 10)
    card = board["columns"][0]["tasks"][0]
    assert card["assignees"] == ["Ana"]
    assert card["state"] == "blocked"
    _, kwargs = client.last_call("project.task", "search_read")
    assert "user_id" in kwargs["fields"]
    assert "user_ids" not in kwargs["fields"]


def test_get_board_trunca_y_avisa():
    tasks = [
        {"id": 100, "name": "A", "stage_id": [1, "Por hacer"], "user_ids": [], "priority": "0"},
        {"id": 101, "name": "B", "stage_id": [1, "Por hacer"], "user_ids": [], "priority": "0"},
    ]
    client = board_client(tasks)
    client.responses[("project.task", "search_count")] = 500
    board = projects.get_board(client, "Web Corporativa", max_tasks=2)
    assert board["total_tasks"] == 500
    assert "Mostrando 2 de 500" in board["note"]
    _, kwargs = client.last_call("project.task", "search_read")
    assert kwargs["limit"] == 2


def test_resolve_project_prefiere_coincidencia_exacta():
    client = FakeClient(
        {
            ("project.project", "search_read"): [
                {"id": 1, "name": "Web"},
                {"id": 2, "name": "Web Corporativa"},
            ]
        }
    )
    assert projects.resolve_project(client, "web") == (1, "Web")


def test_resolve_project_ambiguo_lista_candidatos():
    client = FakeClient(
        {
            ("project.project", "search_read"): [
                {"id": 1, "name": "Web Interna"},
                {"id": 2, "name": "Web Corporativa"},
            ]
        }
    )
    with pytest.raises(OdooError, match="varios proyectos.*Web Interna.*Web Corporativa"):
        projects.resolve_project(client, "web")


def test_resolve_project_inexistente():
    client = FakeClient({("project.project", "search_read"): []})
    with pytest.raises(OdooError, match="No se encontró"):
        projects.resolve_project(client, "NoExiste")


def test_resolve_project_nombre_numerico_cae_a_busqueda_por_nombre():
    client = FakeClient(
        {
            ("project.project", "search_read"): lambda args, kwargs: (
                [] if args[0][0] == ("id", "=", 2024) else [{"id": 33, "name": "2024"}]
            )
        }
    )
    assert projects.resolve_project(client, "2024") == (33, "2024")


def test_resolve_stage_por_id_valida_pertenencia_al_proyecto():
    client = FakeClient({("project.task.type", "search_read"): []})
    with pytest.raises(OdooError, match="id 42"):
        projects.resolve_stage(client, 10, 42)
    args, kwargs = client.last_call("project.task.type", "search_read")
    assert args[0] == [("id", "=", 42), ("project_ids", "=", 10)]
    assert kwargs["context"] == {"active_test": False}


def test_resolve_tags_exige_igualdad_exacta_y_escapa_comodines():
    client = FakeClient(
        {
            ("project.tags", "search_read"): [{"id": 70, "name": "500 páginas"}],
            ("project.tags", "create"): 71,
        }
    )
    assert projects._resolve_tags(client, ["50%"]) == [71]
    args, _ = client.last_call("project.tags", "search_read")
    assert args[0] == [("name", "ilike", "50\\%")]


def test_list_tasks_combina_filtros():
    client = FakeClient(
        {
            ("project.project", "search_read"): PROJECT_ROWS,
            ("project.task.type", "search_read"): [{"id": 2, "name": "En curso"}],
            ("res.users", "search_read"): [{"id": 5, "name": "Ana", "login": "ana"}],
            ("project.task", "search_read"): [
                {
                    "id": 100,
                    "name": "Diseñar portada",
                    "stage_id": [2, "En curso"],
                    "project_id": [10, "Web Corporativa"],
                    "user_ids": [5],
                    "priority": "0",
                }
            ],
            ("res.users", "read"): [{"id": 5, "name": "Ana"}],
        },
        fields=MODERN_TASK_FIELDS,
    )
    result = projects.list_tasks(
        client,
        project="Web Corporativa",
        stage="En curso",
        assignee="Ana",
        query="portada",
        limit=10,
    )
    args, kwargs = client.last_call("project.task", "search_read")
    assert args == [
        [
            ("project_id", "=", 10),
            ("stage_id", "=", 2),
            ("user_ids", "in", [5]),
            ("name", "ilike", "portada"),
        ]
    ]
    assert kwargs["limit"] == 10
    assert result[0]["project"] == "Web Corporativa"
    assert result[0]["stage"] == "En curso"
    assert result[0]["assignees"] == ["Ana"]


def test_list_tasks_etapa_sin_proyecto():
    client = FakeClient(
        {("project.task", "search_read"): []}, fields=MODERN_TASK_FIELDS
    )
    projects.list_tasks(client, stage="En curso")
    args, _ = client.last_call("project.task", "search_read")
    assert args == [[("stage_id.name", "ilike", "En curso")]]

    client2 = FakeClient(
        {("project.task", "search_read"): []}, fields=MODERN_TASK_FIELDS
    )
    projects.list_tasks(client2, stage="12")
    args, _ = client2.last_call("project.task", "search_read")
    assert args == [[("stage_id", "=", 12)]]


def test_list_tasks_version_antigua_filtra_por_user_id():
    client = FakeClient(
        {
            ("res.users", "search_read"): [{"id": 5, "name": "Ana", "login": "ana"}],
            ("project.task", "search_read"): [],
        },
        fields=LEGACY_TASK_FIELDS,
    )
    projects.list_tasks(client, assignee="Ana")
    args, _ = client.last_call("project.task", "search_read")
    assert args == [[("user_id", "in", [5])]]


def test_move_task_resuelve_etapa_por_nombre():
    client = FakeClient(
        {
            ("project.task", "read"): [
                {
                    "id": 100,
                    "name": "Diseñar portada",
                    "project_id": [10, "Web Corporativa"],
                    "stage_id": [1, "Por hacer"],
                }
            ],
            ("project.task.type", "search_read"): [{"id": 2, "name": "En curso"}],
            ("project.task", "write"): True,
        },
        fields=MODERN_TASK_FIELDS,
    )
    result = projects.move_task(client, 100, "en curso")
    assert result["from_stage"] == "Por hacer"
    assert result["to_stage"] == "En curso"
    args, _ = client.last_call("project.task", "write")
    assert args == [[100], {"stage_id": 2}]
    stage_args, _ = client.last_call("project.task.type", "search_read")
    assert ("project_ids", "=", 10) in stage_args[0]


def test_move_task_inexistente():
    client = FakeClient({("project.task", "read"): []})
    with pytest.raises(OdooError, match="No existe la tarea"):
        projects.move_task(client, 999, "En curso")


def test_create_task_completa():
    client = FakeClient(
        {
            ("project.project", "search_read"): PROJECT_ROWS,
            ("project.task.type", "search_read"): [{"id": 1, "name": "Por hacer"}],
            ("res.users", "search_read"): [{"id": 5, "name": "Ana", "login": "ana"}],
            ("project.tags", "search_read"): lambda args, kwargs: (
                [{"id": 70, "name": "urgente"}]
                if args[0][0][2] == "urgente"
                else []
            ),
            ("project.tags", "create"): 71,
            ("project.task", "create"): 500,
        },
        fields=MODERN_TASK_FIELDS,
    )
    result = projects.create_task(
        client,
        "Web Corporativa",
        "Nueva tarea",
        description="<p>Detalle</p>",
        stage="Por hacer",
        assignees=["Ana"],
        deadline="2026-08-01",
        priority="alta",
        tags=["urgente", "frontend"],
    )
    assert result["id"] == 500
    args, _ = client.last_call("project.task", "create")
    values = args[0]
    assert values["project_id"] == 10
    assert values["name"] == "Nueva tarea"
    assert values["stage_id"] == 1
    assert values["user_ids"] == [(6, 0, [5])]
    assert values["date_deadline"] == "2026-08-01"
    assert values["priority"] == "1"
    assert values["tag_ids"] == [(6, 0, [70, 71])]


def test_create_task_version_antigua_un_solo_asignado():
    client = FakeClient(
        {
            ("project.project", "search_read"): PROJECT_ROWS,
            ("res.users", "search_read"): [{"id": 5, "name": "Ana", "login": "ana"}],
            ("project.task", "create"): 500,
        },
        fields=LEGACY_TASK_FIELDS,
    )
    projects.create_task(client, "Web Corporativa", "Tarea", assignees=["Ana"])
    args, _ = client.last_call("project.task", "create")
    assert args[0]["user_id"] == 5


def test_create_task_prioridad_invalida():
    client = FakeClient({("project.project", "search_read"): PROJECT_ROWS})
    with pytest.raises(OdooError, match="Prioridad desconocida"):
        projects.create_task(client, "Web Corporativa", "Tarea", priority="misteriosa")


def test_update_task_sin_campos():
    client = FakeClient({})
    with pytest.raises(OdooError, match="ningún campo"):
        projects.update_task(client, 100)


def test_update_task_resuelve_etapa_con_el_proyecto_de_la_tarea():
    client = FakeClient(
        {
            ("project.task", "read"): [
                {"id": 100, "project_id": [10, "Web Corporativa"]}
            ],
            ("project.task.type", "search_read"): [{"id": 3, "name": "Hecho"}],
            ("project.task", "write"): True,
        },
        fields=MODERN_TASK_FIELDS,
    )
    result = projects.update_task(client, 100, stage="Hecho", priority="normal")
    assert sorted(result["updated"]) == ["priority", "stage_id"]
    args, _ = client.last_call("project.task", "write")
    assert args == [[100], {"stage_id": 3, "priority": "0"}]


def test_assign_task_reemplaza_o_agrega():
    responses = {
        ("res.users", "search_read"): [{"id": 5, "name": "Ana", "login": "ana"}],
        ("project.task", "write"): True,
    }
    client = FakeClient(responses, fields=MODERN_TASK_FIELDS)
    projects.assign_task(client, 100, ["Ana"])
    args, _ = client.last_call("project.task", "write")
    assert args == [[100], {"user_ids": [(6, 0, [5])]}]

    projects.assign_task(client, 100, ["Ana"], replace=False)
    args, _ = client.last_call("project.task", "write")
    assert args == [[100], {"user_ids": [(4, 5)]}]


def test_assign_task_version_antigua_rechaza_varios():
    client = FakeClient(
        {
            ("res.users", "search_read"): lambda args, kwargs: [
                {"id": 5, "name": "Ana", "login": "ana"}
            ]
            if "Ana" in str(args)
            else [{"id": 6, "name": "Luis", "login": "luis"}],
        },
        fields=LEGACY_TASK_FIELDS,
    )
    with pytest.raises(OdooError, match="un asignado"):
        projects.assign_task(client, 100, ["Ana", "Luis"])


def test_resolve_user_ambiguo():
    client = FakeClient(
        {
            ("res.users", "search_read"): [
                {"id": 5, "name": "Ana García", "login": "anag"},
                {"id": 6, "name": "Ana López", "login": "anal"},
            ]
        }
    )
    with pytest.raises(OdooError, match="varios usuarios"):
        projects.resolve_user(client, "ana")


def test_add_comment():
    client = FakeClient({("project.task", "message_post"): 900})
    result = projects.add_comment(client, 100, "<p>Hola equipo</p>")
    assert result["message_id"] == 900
    args, kwargs = client.last_call("project.task", "message_post")
    assert args == [[100]]
    assert kwargs["body"] == "<p>Hola equipo</p>"
    assert kwargs["message_type"] == "comment"
    assert kwargs["subtype_xmlid"] == "mail.mt_comment"


def test_add_comment_odoo_13_usa_subtype():
    client = FakeClient({("project.task", "message_post"): 900}, version_major=13)
    projects.add_comment(client, 100, "Hola")
    _, kwargs = client.last_call("project.task", "message_post")
    assert kwargs["subtype"] == "mail.mt_comment"
    assert "subtype_xmlid" not in kwargs


def test_add_comment_tolera_error_de_marshalling():
    def boom(args, kwargs):
        raise OdooError("Odoo: cannot marshal <class 'odoo.api.mail.message'> objects")

    client = FakeClient({("project.task", "message_post"): boom})
    result = projects.add_comment(client, 100, "Hola")
    assert result["message_id"] is None
    assert result["task_id"] == 100


def test_list_stages_incluye_recuentos():
    client = FakeClient(
        {
            ("project.project", "search_read"): PROJECT_ROWS,
            ("project.task.type", "search_read"): STAGE_ROWS,
            ("project.task", "read_group"): [
                {"stage_id": [1, "Por hacer"], "stage_id_count": 4},
                {"stage_id": [2, "En curso"], "stage_id_count": 2},
            ],
        }
    )
    stages = projects.list_stages(client, "Web Corporativa")
    assert [(s["name"], s["task_count"]) for s in stages] == [
        ("Por hacer", 4),
        ("En curso", 2),
        ("Hecho", 0),
    ]


def test_create_stage_vincula_el_proyecto():
    client = FakeClient(
        {
            ("project.project", "search_read"): PROJECT_ROWS,
            ("project.task.type", "create"): 9,
        }
    )
    result = projects.create_stage(client, "Web Corporativa", "Revisión", sequence=15)
    assert result["id"] == 9
    args, _ = client.last_call("project.task.type", "create")
    assert args[0] == {"name": "Revisión", "project_ids": [(4, 10)], "sequence": 15}


def test_list_projects_formatea():
    client = FakeClient(
        {
            ("project.project", "search_read"): [
                {"id": 10, "name": "Web", "task_count": 7, "user_id": [5, "Ana"]}
            ]
        },
        fields=MODERN_TASK_FIELDS,
    )
    result = projects.list_projects(client)
    assert result == [
        {
            "id": 10,
            "name": "Web",
            "url": "http://odoo.test/web#id=10&model=project.project&view_type=form",
            "task_count": 7,
            "manager": "Ana",
        }
    ]


def test_get_task_detalle():
    client = FakeClient(
        {
            ("project.task", "read"): [
                {
                    "id": 100,
                    "name": "Diseñar portada",
                    "stage_id": [2, "En curso"],
                    "project_id": [10, "Web Corporativa"],
                    "user_ids": [5],
                    "priority": "0",
                    "description": "<p>Detalle</p>",
                    "tag_ids": [70],
                    "create_date": "2026-07-01 10:00:00",
                    "write_date": "2026-07-05 12:00:00",
                }
            ],
            ("res.users", "read"): [{"id": 5, "name": "Ana"}],
            ("project.tags", "read"): [{"id": 70, "name": "urgente"}],
        },
        fields=MODERN_TASK_FIELDS,
    )
    detail = projects.get_task(client, 100)
    assert detail["name"] == "Diseñar portada"
    assert detail["project"] == {"id": 10, "name": "Web Corporativa"}
    assert detail["stage"] == "En curso"
    assert detail["assignees"] == ["Ana"]
    assert detail["tags"] == ["urgente"]
    assert detail["description"] == "<p>Detalle</p>"


def test_get_task_inexistente():
    client = FakeClient({("project.task", "read"): []}, fields=MODERN_TASK_FIELDS)
    with pytest.raises(OdooError, match="No existe la tarea"):
        projects.get_task(client, 12345)
