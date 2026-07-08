"""Operaciones genéricas sobre cualquier modelo de Odoo."""

from __future__ import annotations

from typing import Any

from .client import OdooClient


def list_models(client: OdooClient, pattern: str | None = None, limit: int = 100) -> list[dict]:
    domain: list = []
    if pattern:
        domain = ["|", ("model", "ilike", pattern), ("name", "ilike", pattern)]
    return client.execute(
        "ir.model",
        "search_read",
        [domain],
        {"fields": ["model", "name"], "limit": limit, "order": "model"},
    )


def get_model_fields(client: OdooClient, model: str) -> dict[str, dict]:
    info = client.execute(
        model,
        "fields_get",
        [],
        {"attributes": ["string", "type", "required", "readonly", "relation", "selection", "help"]},
    )
    compact: dict[str, dict] = {}
    for name, attrs in info.items():
        entry = {"type": attrs.get("type"), "label": attrs.get("string")}
        if attrs.get("required"):
            entry["required"] = True
        if attrs.get("readonly"):
            entry["readonly"] = True
        if attrs.get("relation"):
            entry["relation"] = attrs["relation"]
        if attrs.get("selection"):
            entry["selection"] = attrs["selection"]
        if attrs.get("help"):
            entry["help"] = attrs["help"]
        compact[name] = entry
    return compact


def search_records(
    client: OdooClient,
    model: str,
    domain: list | None = None,
    fields: list[str] | None = None,
    limit: int = 80,
    offset: int = 0,
    order: str | None = None,
) -> list[dict]:
    kwargs: dict[str, Any] = {"limit": limit, "offset": offset}
    if fields:
        kwargs["fields"] = fields
    if order:
        kwargs["order"] = order
    return client.execute(model, "search_read", [_as_domain(domain)], kwargs)


def count_records(client: OdooClient, model: str, domain: list | None = None) -> int:
    return client.execute(model, "search_count", [_as_domain(domain)])


def read_records(
    client: OdooClient, model: str, ids: list[int], fields: list[str] | None = None
) -> list[dict]:
    kwargs = {"fields": fields} if fields else {}
    return client.execute(model, "read", [ids], kwargs)


def create_record(client: OdooClient, model: str, values: dict[str, Any]) -> int:
    return client.execute(model, "create", [values])


def update_records(client: OdooClient, model: str, ids: list[int], values: dict[str, Any]) -> bool:
    return client.execute(model, "write", [ids, values])


def delete_records(client: OdooClient, model: str, ids: list[int]) -> bool:
    return client.execute(model, "unlink", [ids])


def call_method(
    client: OdooClient,
    model: str,
    method: str,
    args: list | None = None,
    kwargs: dict[str, Any] | None = None,
) -> Any:
    return client.execute(model, method, args or [], kwargs or {})


def _as_domain(domain: list | None) -> list:
    """Los dominios llegan por JSON como listas de listas; Odoo espera tuplas o
    listas indistintamente, pero sí exige que el conjunto sea una lista."""
    return list(domain) if domain else []
