"""Smoke test del contrato MCP: registro de tools y una llamada de punta a punta."""

import asyncio

from odoo_mcp import server

from fakes import MODERN_TASK_FIELDS, FakeClient

EXPECTED_TOOLS = {
    "list_projects",
    "get_board",
    "list_tasks",
    "get_task",
    "create_task",
    "update_task",
    "move_task",
    "assign_task",
    "add_comment",
    "list_stages",
    "create_stage",
    "create_project",
    "list_models",
    "get_model_fields",
    "search_records",
    "count_records",
    "read_records",
    "create_record",
    "update_records",
    "delete_records",
    "call_method",
}


def test_registra_todas_las_tools():
    tools = asyncio.run(server.mcp.list_tools())
    assert {t.name for t in tools} == EXPECTED_TOOLS


def test_move_task_de_punta_a_punta(monkeypatch):
    fake = FakeClient(
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
    monkeypatch.setattr(server, "_client", fake)

    result = asyncio.run(
        server.mcp.call_tool("move_task", {"task_id": 100, "stage": "En curso"})
    )

    assert "En curso" in str(result)
    args, _ = fake.last_call("project.task", "write")
    assert args == [[100], {"stage_id": 2}]


# --- CLI ----------------------------------------------------------------------


def test_check_connection_describe_la_conexion():
    fake = FakeClient({("res.users", "read"): [{"name": "Ana Ruiz", "login": "ana@x.com"}]})

    mensaje = server.check_connection(fake)

    assert mensaje.startswith("OK:")
    assert "Ana Ruiz" in mensaje
    assert "test_db" in mensaje
    assert "Odoo 17" in mensaje
    args, _ = fake.last_call("res.users", "read")
    assert args == [[2], ["name", "login"]]


def test_check_devuelve_1_si_falla_la_autenticacion(monkeypatch, capsys):
    from odoo_mcp.client import OdooError

    fake = FakeClient(uid=OdooError("Autenticación fallida: revisa ODOO_DB."))
    monkeypatch.setattr(server, "_client", fake)

    assert server.main(["--check"]) == 1
    assert "Autenticación fallida" in capsys.readouterr().err


def test_check_devuelve_0_si_conecta(monkeypatch, capsys):
    fake = FakeClient({("res.users", "read"): [{"name": "Ana", "login": "ana@x.com"}]})
    monkeypatch.setattr(server, "_client", fake)

    assert server.main(["--check"]) == 0
    assert "OK:" in capsys.readouterr().out


def test_version_y_ayuda(capsys):
    assert server.main(["--version"]) == 0
    assert "odoo-mcp" in capsys.readouterr().out
    assert server.main(["--help"]) == 0
    assert "--check" in capsys.readouterr().out


def test_argumento_desconocido(capsys):
    assert server.main(["--loquesea"]) == 2
    assert "no reconocido" in capsys.readouterr().err
