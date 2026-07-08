from __future__ import annotations

from typing import Any

import pytest


class FakeClient:
    """Doble del OdooClient: respuestas programadas por (modelo, método)."""

    base_url = "http://odoo.test"

    def __init__(
        self,
        responses: dict[tuple[str, str], Any] | None = None,
        fields: dict[str, dict[str, dict]] | None = None,
    ):
        self.calls: list[tuple[str, str, list, dict]] = []
        self.responses = dict(responses or {})
        self.fields = dict(fields or {})

    def fields_info(self, model: str) -> dict[str, dict]:
        return self.fields.get(model, {})

    def execute(self, model, method, args=None, kwargs=None):
        args = args or []
        kwargs = kwargs or {}
        self.calls.append((model, method, args, kwargs))
        response = self.responses[(model, method)]
        if callable(response):
            return response(args, kwargs)
        return response

    def last_call(self, model: str, method: str) -> tuple[list, dict]:
        for m, meth, args, kwargs in reversed(self.calls):
            if (m, meth) == (model, method):
                return args, kwargs
        raise AssertionError(f"No se llamó a {model}.{method}")


MODERN_TASK_FIELDS = {
    "project.task": {
        name: {"type": "char"}
        for name in [
            "name",
            "stage_id",
            "project_id",
            "date_deadline",
            "priority",
            "sequence",
            "state",
            "user_ids",
            "description",
            "tag_ids",
            "partner_id",
            "parent_id",
            "create_date",
            "write_date",
        ]
    },
    "project.project": {
        name: {"type": "char"} for name in ["name", "task_count", "user_id"]
    },
}

LEGACY_TASK_FIELDS = {
    "project.task": {
        name: {"type": "char"}
        for name in [
            "name",
            "stage_id",
            "project_id",
            "date_deadline",
            "priority",
            "sequence",
            "kanban_state",
            "user_id",
            "description",
            "tag_ids",
        ]
    },
    "project.project": {name: {"type": "char"} for name in ["name", "user_id"]},
}


@pytest.fixture
def fake_client():
    return FakeClient(fields=MODERN_TASK_FIELDS)
