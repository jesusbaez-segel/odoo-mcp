import pytest

from odoo_mcp.config import (
    ConfigError,
    config_search_paths,
    load_settings,
    parse_env_file,
    user_config_path,
)

FULL_ENV = {
    "ODOO_URL": "https://miempresa.ejemplo.com/",
    "ODOO_DB": "produccion",
    "ODOO_USERNAME": "admin@ejemplo.com",
    "ODOO_API_KEY": "clave-secreta",
}

CONFIG_FILE = """# Configuracion escrita por el asistente
ODOO_URL=https://desde-archivo.ejemplo.com/
ODOO_DB=archivo_db
ODOO_USERNAME=archivo@ejemplo.com
ODOO_PASSWORD=clave-del-archivo
"""


def write_config(tmp_path, text=CONFIG_FILE, name="config.env"):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


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
    assert "instalar.bat" in message


def test_load_settings_timeout():
    assert load_settings(FULL_ENV).timeout == 60.0
    env = dict(FULL_ENV)
    env["ODOO_TIMEOUT"] = "30"
    assert load_settings(env).timeout == 30.0
    env["ODOO_TIMEOUT"] = "abc"
    with pytest.raises(ConfigError, match="ODOO_TIMEOUT"):
        load_settings(env)


def test_localhost_se_queda_tal_cual():
    """Sin Docker de por medio, localhost es alcanzable y no se reescribe."""
    env = dict(FULL_ENV, ODOO_URL="http://localhost:8069")
    assert load_settings(env).url == "http://localhost:8069"


# --- Archivo de configuración -------------------------------------------------


def test_lee_el_archivo_cuando_no_hay_entorno(tmp_path):
    settings = load_settings({}, config_path=write_config(tmp_path))
    assert settings.url == "https://desde-archivo.ejemplo.com"
    assert settings.db == "archivo_db"
    assert settings.username == "archivo@ejemplo.com"
    assert settings.api_key == "clave-del-archivo"


def test_el_entorno_gana_al_archivo(tmp_path):
    settings = load_settings({"ODOO_DB": "del_entorno"}, config_path=write_config(tmp_path))
    assert settings.db == "del_entorno"
    assert settings.username == "archivo@ejemplo.com"


def test_un_valor_vacio_del_entorno_no_pisa_al_archivo(tmp_path):
    settings = load_settings({"ODOO_DB": "   "}, config_path=write_config(tmp_path))
    assert settings.db == "archivo_db"


def test_archivo_inexistente_no_revienta(tmp_path):
    with pytest.raises(ConfigError):
        load_settings({}, config_path=tmp_path / "no-existe.env")


def test_entorno_explicito_no_lee_archivos_del_sistema():
    """Sin config_path, un environ explícito no debe tocar el disco."""
    settings = load_settings(FULL_ENV)
    assert settings.db == "produccion"


def test_parse_env_file_formatos():
    values = parse_env_file(
        '\n'.join(
            [
                "# comentario",
                "",
                "ODOO_URL=https://x.com",
                'ODOO_DB="mi base"',
                "export ODOO_USERNAME='ana@x.com'",
                "linea sin igual",
                "ODOO_API_KEY=  clave con espacios  ",
            ]
        )
    )
    assert values == {
        "ODOO_URL": "https://x.com",
        "ODOO_DB": "mi base",
        "ODOO_USERNAME": "ana@x.com",
        "ODOO_API_KEY": "clave con espacios",
    }


def test_parse_env_file_conserva_el_signo_igual_del_valor():
    assert parse_env_file("ODOO_API_KEY=abc=def==")["ODOO_API_KEY"] == "abc=def=="


def test_archivo_con_bom(tmp_path):
    path = tmp_path / "config.env"
    path.write_text(CONFIG_FILE, encoding="utf-8-sig")
    assert load_settings({}, config_path=path).url == "https://desde-archivo.ejemplo.com"


def test_orden_de_busqueda(tmp_path):
    explicito = str(tmp_path / "mio.env")
    paths = config_search_paths({"ODOO_MCP_CONFIG": explicito, "APPDATA": str(tmp_path)})
    assert str(paths[0]) == explicito
    assert paths[1].name == "config.env"
    assert paths[-1].name == ".env"


def test_user_config_path_usa_appdata(monkeypatch, tmp_path):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    path = user_config_path()
    assert path.parent.name == "odoo-mcp"
    assert path.name == "config.env"
