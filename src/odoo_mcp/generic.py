"""Operaciones genéricas sobre cualquier modelo de Odoo."""

from __future__ import annotations

from typing import Any

from .client import OdooClient, paginar


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


def get_model_fields(client: OdooClient, model: str, pattern: str | None = None) -> dict[str, dict]:
    info = client.execute(
        model,
        "fields_get",
        [],
        {"attributes": ["string", "type", "required", "readonly", "relation", "selection", "help"]},
    )
    compact: dict[str, dict] = {}
    for name, attrs in info.items():
        if pattern and pattern.lower() not in f"{name} {attrs.get('string', '')}".lower():
            continue
        entry = {"type": attrs.get("type"), "label": attrs.get("string")}
        if attrs.get("required"):
            entry["required"] = True
        if attrs.get("readonly"):
            entry["readonly"] = True
        if attrs.get("relation"):
            entry["relation"] = attrs["relation"]
        if attrs.get("selection"):
            # {valor: etiqueta}: menos tokens que la lista de pares
            entry["selection"] = dict(attrs["selection"])
        if attrs.get("help"):
            entry["help"] = attrs["help"][:100]
        compact[name] = entry
    return compact


def search_records(
    client: OdooClient,
    model: str,
    domain: list | None = None,
    fields: list[str] | None = None,
    limit: int = 20,
    offset: int = 0,
    order: str | None = None,
) -> dict:
    kwargs: dict[str, Any] = {
        "fields": fields or _campos_simples(client, model),
        "limit": limit + 1,
        "offset": offset,
    }
    if order:
        kwargs["order"] = order
    rows = client.execute(model, "search_read", [_as_domain(domain)], kwargs)
    return {"records": rows[:limit], **paginar(rows, limit)}


def count_records(client: OdooClient, model: str, domain: list | None = None) -> int:
    return client.execute(model, "search_count", [_as_domain(domain)])


def read_records(
    client: OdooClient, model: str, ids: list[int], fields: list[str] | None = None
) -> list[dict]:
    return client.execute(
        model, "read", [ids], {"fields": fields or _campos_simples(client, model)}
    )


_TIPOS_PESADOS = ("binary", "html", "one2many", "many2many")


def _campos_simples(client: OdooClient, model: str) -> list[str]:
    """Sin lista de campos, Odoo devuelve también imágenes en base64, html y
    listas de ids sin nombre (medido, el 40 % de los tokens) y calcula campos
    que exigen permisos de otros modelos: el saldo de un contacto falla para
    quien no sea de contabilidad. Solo los almacenados y simples."""
    return [
        n
        for n, a in client.fields_info(model).items()
        if a.get("store") and a.get("type") not in _TIPOS_PESADOS
    ]


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
