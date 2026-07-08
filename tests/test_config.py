import pytest

from odoo_mcp.config import ConfigError, adjust_url_for_docker, load_settings

FULL_ENV = {
    "ODOO_URL": "https://miempresa.ejemplo.com/",
    "ODOO_DB": "produccion",
    "ODOO_USERNAME": "admin@ejemplo.com",
    "ODOO_API_KEY": "clave-secreta",
}


def test_load_settings_completo():
    settings = load_settings(FULL_ENV)
    assert settings.url == "https://miempresa.ejemplo.com"
    assert settings.db == "produccion"
    assert settings.username == "admin@ejemplo.com"
    assert settings.api_key == "clave-secreta"


def test_load_settings_acepta_password_como_alternativa():
    env = dict(FULL_ENV)
    del env["ODOO_API_KEY"]
    env["ODOO_PASSWORD"] = "otra-clave"
    assert load_settings(env).api_key == "otra-clave"


def test_load_settings_faltantes():
    with pytest.raises(ConfigError) as exc:
        load_settings({"ODOO_URL": "http://x"})
    message = str(exc.value)
    assert "ODOO_DB" in message
    assert "ODOO_USERNAME" in message
    assert "ODOO_API_KEY" in message


def test_adjust_url_reescribe_localhost_en_docker():
    assert (
        adjust_url_for_docker("http://localhost:8069", in_docker=True)
        == "http://host.docker.internal:8069"
    )
    assert (
        adjust_url_for_docker("http://127.0.0.1:8069", in_docker=True)
        == "http://host.docker.internal:8069"
    )


def test_adjust_url_reescribe_0_0_0_0_en_docker():
    assert (
        adjust_url_for_docker("http://0.0.0.0:8069", in_docker=True)
        == "http://host.docker.internal:8069"
    )


def test_load_settings_timeout():
    assert load_settings(FULL_ENV).timeout == 60.0
    env = dict(FULL_ENV)
    env["ODOO_TIMEOUT"] = "30"
    assert load_settings(env).timeout == 30.0
    env["ODOO_TIMEOUT"] = "abc"
    with pytest.raises(ConfigError, match="ODOO_TIMEOUT"):
        load_settings(env)


def test_adjust_url_no_toca_otros_hosts_ni_fuera_de_docker():
    assert (
        adjust_url_for_docker("https://odoo.miempresa.com", in_docker=True)
        == "https://odoo.miempresa.com"
    )
    assert (
        adjust_url_for_docker("http://localhost:8069", in_docker=False)
        == "http://localhost:8069"
    )
