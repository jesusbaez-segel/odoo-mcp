import xmlrpc.client

import pytest

from odoo_mcp import client as client_module
from odoo_mcp.client import OdooClient, OdooError, _fault_message
from odoo_mcp.config import Settings

SETTINGS = Settings(
    url="http://odoo.test", db="db", username="user@test.com", api_key="key"
)


class StubProxy:
    """Sustituto de xmlrpc.client.ServerProxy programable por método."""

    instances: dict[str, "StubProxy"] = {}

    def __init__(self, uri, allow_none=False, transport=None):
        self.uri = uri
        self.transport = transport
        self.calls = []
        StubProxy.instances[uri] = self

    def __getattr__(self, name):
        def call(*args):
            self.calls.append((name, args))
            handler = getattr(self, f"handle_{name}", None)
            if handler is None:
                raise AssertionError(f"Llamada inesperada: {name}")
            return handler(*args)

        return call


@pytest.fixture
def stubbed_client(monkeypatch):
    StubProxy.instances = {}
    monkeypatch.setattr(client_module.xmlrpc.client, "ServerProxy", StubProxy)
    odoo = OdooClient(SETTINGS)
    common = StubProxy.instances["http://odoo.test/xmlrpc/2/common"]
    obj = StubProxy.instances["http://odoo.test/xmlrpc/2/object"]
    return odoo, common, obj


def test_autentica_una_sola_vez_y_pasa_credenciales(stubbed_client):
    odoo, common, obj = stubbed_client
    common.handle_authenticate = lambda *args: 7
    obj.handle_execute_kw = lambda *args: [{"id": 1}]

    odoo.execute("res.partner", "search_read", [[]], {"limit": 1})
    odoo.execute("res.partner", "search_read", [[]], {"limit": 1})

    assert len([c for c in common.calls if c[0] == "authenticate"]) == 1
    name, args = obj.calls[0]
    assert name == "execute_kw"
    assert args == ("db", 7, "key", "res.partner", "search_read", [[]], {"limit": 1})


def test_execute_sin_args_ni_kwargs_envia_contenedores_vacios(stubbed_client):
    odoo, common, obj = stubbed_client
    common.handle_authenticate = lambda *args: 7
    obj.handle_execute_kw = lambda *args: []

    odoo.execute("res.partner", "read")

    _, args = obj.calls[0]
    assert args == ("db", 7, "key", "res.partner", "read", [], {})


def test_autenticacion_fallida(stubbed_client):
    odoo, common, _ = stubbed_client
    common.handle_authenticate = lambda *args: False
    with pytest.raises(OdooError, match="Autenticación fallida"):
        odoo.execute("res.partner", "read", [[1]])


def test_error_de_conexion(stubbed_client):
    odoo, common, _ = stubbed_client

    def boom(*args):
        raise ConnectionRefusedError("connection refused")

    common.handle_authenticate = boom
    with pytest.raises(OdooError, match="No se pudo conectar"):
        odoo.execute("res.partner", "read", [[1]])


def test_fault_se_convierte_en_mensaje_legible(stubbed_client):
    odoo, common, obj = stubbed_client
    common.handle_authenticate = lambda *args: 7

    def fault(*args):
        raise xmlrpc.client.Fault(
            1,
            "Traceback (most recent call last):\n"
            '  File "x.py", line 1, in f\n'
            "odoo.exceptions.ValidationError: El campo nombre es obligatorio",
        )

    obj.handle_execute_kw = fault
    with pytest.raises(OdooError, match="El campo nombre es obligatorio"):
        odoo.execute("res.partner", "create", [{}])


def test_fault_message_sin_traceback():
    fault = xmlrpc.client.Fault(2, "Access Denied")
    assert _fault_message(fault) == "Odoo: Access Denied"


def test_fields_info_cachea(stubbed_client):
    odoo, common, obj = stubbed_client
    common.handle_authenticate = lambda *args: 7
    obj.handle_execute_kw = lambda *args: {"name": {"type": "char"}}

    assert odoo.fields_info("project.task") == {"name": {"type": "char"}}
    assert odoo.fields_info("project.task") == {"name": {"type": "char"}}
    assert len(obj.calls) == 1
