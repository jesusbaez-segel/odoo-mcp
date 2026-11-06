"""Smoke test del contrato MCP: registro de tools y una llamada de punta a punta."""

import asyncio
import logging

import pytest

from odoo_mcp import server
from odoo_mcp.client import OdooError
from odoo_mcp.config import Settings

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


def test_el_log_guarda_la_config_y_los_errores_de_las_tools(monkeypatch, tmp_path):
    monkeypatch.setattr(server, "user_config_path", lambda: tmp_path / "config.env")
    monkeypatch.setattr(server, "_client", None)
    monkeypatch.setattr(
        server,
        "load_settings",
        lambda: Settings(url="http://odoo.test", db="db", username="ana@x.com", api_key="k"),
    )
    handler = server.activar_log()
    try:
        server.get_client()

        def rompe():
            raise OdooError("Autenticación fallida")

        with pytest.raises(OdooError):
            asyncio.run(server._run(rompe))
    finally:
        logging.getLogger().removeHandler(handler)
        handler.close()
    texto = (tmp_path / "odoo-mcp.log").read_text(encoding="utf-8")
    assert "arrancado" in texto
    assert "config:" in texto
    assert "rompe: Autenticación fallida" in texto


def test_las_tools_devuelven_json_compacto_sin_vacios():
    assert server._compactar(
        {"a": None, "b": False, "c": [], "d": "", "e": 0, "f": {"g": None, "h": 1}, "i": [{"j": False}]}
    ) == {"e": 0, "f": {"h": 1}, "i": [{}]}
    texto = asyncio.run(server._run(lambda: {"x": 1, "y": None, "z": "ñ"}))
    assert texto == '{"x":1,"z":"ñ"}'
