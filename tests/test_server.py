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
