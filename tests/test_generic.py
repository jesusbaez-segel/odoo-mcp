from odoo_mcp import generic

from fakes import FakeClient


def test_search_records_pasa_dominio_y_kwargs():
    client = FakeClient({("res.partner", "search_read"): [{"id": 1, "name": "ACME"}]})
    result = generic.search_records(
        client,
        "res.partner",
        domain=[["is_company", "=", True]],
        fields=["name"],
        limit=5,
        offset=10,
        order="name desc",
    )
    assert result == [{"id": 1, "name": "ACME"}]
    args, kwargs = client.last_call("res.partner", "search_read")
    assert args == [[["is_company", "=", True]]]
    assert kwargs == {"fields": ["name"], "limit": 5, "offset": 10, "order": "name desc"}


PARTNER_FIELDS = {
    "res.partner": {
        "name": {"type": "char"},
        "image_1920": {"type": "binary"},
        "email": {"type": "char"},
    }
}


def test_search_records_sin_dominio_ni_fields_excluye_binarios():
    client = FakeClient({("res.partner", "search_read"): []}, fields=PARTNER_FIELDS)
    generic.search_records(client, "res.partner")
    args, kwargs = client.last_call("res.partner", "search_read")
    assert args == [[]]
    assert kwargs["fields"] == ["name", "email"]


def test_count_records():
    client = FakeClient({("res.partner", "search_count"): 42})
    assert generic.count_records(client, "res.partner", [["x", "=", 1]]) == 42
    args, kwargs = client.last_call("res.partner", "search_count")
    assert args == [[["x", "=", 1]]]
    assert kwargs == {}


def test_count_records_sin_dominio():
    client = FakeClient({("res.partner", "search_count"): 0})
    generic.count_records(client, "res.partner")
    args, _ = client.last_call("res.partner", "search_count")
    assert args == [[]]


def test_read_records_sin_fields_excluye_binarios():
    client = FakeClient({("res.partner", "read"): [{"id": 3}]}, fields=PARTNER_FIELDS)
    generic.read_records(client, "res.partner", [3])
    args, kwargs = client.last_call("res.partner", "read")
    assert args == [[3]]
    assert kwargs == {"fields": ["name", "email"]}


def test_create_update_delete():
    client = FakeClient(
        {
            ("res.partner", "create"): 99,
            ("res.partner", "write"): True,
            ("res.partner", "unlink"): True,
        }
    )
    assert generic.create_record(client, "res.partner", {"name": "Nuevo"}) == 99
    assert generic.update_records(client, "res.partner", [99], {"name": "Otro"}) is True
    assert generic.delete_records(client, "res.partner", [99]) is True
    args, _ = client.last_call("res.partner", "write")
    assert args == [[99], {"name": "Otro"}]


def test_call_method():
    client = FakeClient({("sale.order", "action_confirm"): True})
    assert generic.call_method(client, "sale.order", "action_confirm", [[42]]) is True
    args, kwargs = client.last_call("sale.order", "action_confirm")
    assert args == [[42]]
    assert kwargs == {}


def test_get_model_fields_compacta():
    client = FakeClient(
        {
            ("res.partner", "fields_get"): {
                "name": {"string": "Nombre", "type": "char", "required": True},
                "company_id": {
                    "string": "Compañía",
                    "type": "many2one",
                    "relation": "res.company",
                    "readonly": False,
                },
            }
        }
    )
    fields = generic.get_model_fields(client, "res.partner")
    assert fields["name"] == {"type": "char", "label": "Nombre", "required": True}
    assert fields["company_id"]["relation"] == "res.company"
    assert "readonly" not in fields["company_id"]


def test_list_models_con_patron():
    client = FakeClient({("ir.model", "search_read"): [{"model": "sale.order"}]})
    generic.list_models(client, pattern="sale")
    args, _ = client.last_call("ir.model", "search_read")
    assert args == [["|", ("model", "ilike", "sale"), ("name", "ilike", "sale")]]
