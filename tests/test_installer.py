"""Pruebas del asistente que va dentro del .exe."""

import json
from pathlib import Path

import pytest

from odoo_mcp import installer
from odoo_mcp.installer import (
    InstallerError,
    configs_claude_desktop,
    fusionar_mcp,
    normalizar_url,
    parsear_bases,
    quitar_mcp,
)

EXE = Path(r"C:\Users\x\AppData\Local\Programs\odoo-mcp\odoo-mcp.exe")


@pytest.fixture
def windows(monkeypatch):
    """Las rutas de Claude Desktop dependen de la plataforma: en macOS el codigo
    ignora APPDATA (correctamente) y estos tests fallarian alli, como paso en el
    runner de GitHub. Se simula win32, igual que test_macos.py simula darwin.
    No se toca os.name: pathlib lo usa para elegir el tipo de ruta y romperia
    a pytest entero."""
    monkeypatch.setattr(installer.sys, "platform", "win32")


# --- URL y bases de datos -----------------------------------------------------


def test_normalizar_url_anade_https_y_quita_barra():
    assert normalizar_url("miempresa.odoo.com") == "https://miempresa.odoo.com"
    assert normalizar_url("  https://x.com/  ") == "https://x.com"
    assert normalizar_url("http://localhost:8069") == "http://localhost:8069"


def test_normalizar_url_vacia():
    with pytest.raises(InstallerError):
        normalizar_url("   ")


def test_parsear_bases():
    assert parsear_bases(b'{"result":["produccion","pruebas"]}') == ["produccion", "pruebas"]
    assert parsear_bases(b'{"result":[]}') == []
    assert parsear_bases(b"no es json") == []
    assert parsear_bases(b'{"error":{"code":1}}') == []


# --- Deteccion de Claude Desktop ----------------------------------------------


def test_encuentra_claude_desktop_clasico(windows, tmp_path, monkeypatch):
    (tmp_path / "Claude").mkdir()
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "vacio"))

    rutas = configs_claude_desktop()

    assert [r.name for r in rutas] == ["claude_desktop_config.json"]
    assert rutas[0].parent == tmp_path / "Claude"


def test_encuentra_claude_desktop_de_la_microsoft_store(windows, tmp_path, monkeypatch):
    """La version de la Store virtualiza el AppData dentro del paquete y el hash
    del nombre cambia en cada maquina: hay que dar con ella por comodin."""
    paquete = tmp_path / "Packages" / "Claude_pzs8sxrjxfjjc" / "LocalCache" / "Roaming" / "Claude"
    paquete.mkdir(parents=True)
    monkeypatch.setenv("APPDATA", str(tmp_path / "sin-claude"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    rutas = configs_claude_desktop()

    assert len(rutas) == 1
    assert rutas[0] == paquete / "claude_desktop_config.json"


def test_encuentra_las_dos_instalaciones_a_la_vez(windows, tmp_path, monkeypatch):
    roaming = tmp_path / "roaming"
    (roaming / "Claude").mkdir(parents=True)
    local = tmp_path / "local"
    (local / "Packages" / "Claude_abc123" / "LocalCache" / "Roaming" / "Claude").mkdir(parents=True)
    monkeypatch.setenv("APPDATA", str(roaming))
    monkeypatch.setenv("LOCALAPPDATA", str(local))

    assert len(configs_claude_desktop()) == 2


def test_sin_claude_desktop_no_devuelve_nada(windows, tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "a"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "b"))
    assert configs_claude_desktop() == []


def test_ignora_carpetas_que_no_son_de_claude(windows, tmp_path, monkeypatch):
    (tmp_path / "Packages" / "Cursor_xyz" / "LocalCache" / "Roaming" / "Claude").mkdir(parents=True)
    monkeypatch.setenv("APPDATA", str(tmp_path / "a"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert configs_claude_desktop() == []


# --- Fusion del JSON ----------------------------------------------------------


def test_fusionar_conserva_los_demas_servidores_y_claves(tmp_path):
    ruta = tmp_path / "claude_desktop_config.json"
    ruta.write_text(
        json.dumps({"theme": "dark", "mcpServers": {"github": {"command": "npx"}}}),
        encoding="utf-8",
    )

    assert fusionar_mcp(ruta, EXE) == "ok"

    datos = json.loads(ruta.read_text(encoding="utf-8"))
    assert datos["theme"] == "dark"
    assert datos["mcpServers"]["github"] == {"command": "npx"}
    assert datos["mcpServers"]["odoo"]["command"] == str(EXE)
    assert datos["mcpServers"]["odoo"]["args"] == ["--mcp"]


def test_fusionar_crea_el_archivo_si_no_existe(tmp_path):
    ruta = tmp_path / "nueva" / "config.json"
    assert fusionar_mcp(ruta, EXE) == "ok"
    assert json.loads(ruta.read_text(encoding="utf-8"))["mcpServers"]["odoo"]["type"] == "stdio"


def test_fusionar_sustituye_una_entrada_anterior(tmp_path):
    ruta = tmp_path / "config.json"
    ruta.write_text(
        json.dumps({"mcpServers": {"odoo": {"command": "docker", "args": ["run"]}, "otro": {}}}),
        encoding="utf-8",
    )

    assert fusionar_mcp(ruta, EXE) == "ok"

    servidores = json.loads(ruta.read_text(encoding="utf-8"))["mcpServers"]
    assert servidores["odoo"]["command"] == str(EXE)
    assert "otro" in servidores


def test_fusionar_no_toca_un_json_corrupto(tmp_path):
    ruta = tmp_path / "config.json"
    ruta.write_text("{esto no es json", encoding="utf-8")

    assert fusionar_mcp(ruta, EXE) == "json-corrupto"
    assert ruta.read_text(encoding="utf-8") == "{esto no es json"


def test_fusionar_deja_copia_de_seguridad(tmp_path):
    ruta = tmp_path / "config.json"
    ruta.write_text('{"mcpServers":{}}', encoding="utf-8")

    fusionar_mcp(ruta, EXE)

    assert (tmp_path / "config.json.bak").read_text(encoding="utf-8") == '{"mcpServers":{}}'


def test_fusionar_escribe_sin_bom(tmp_path):
    """Con BOM, Claude no puede leer su propia configuracion."""
    ruta = tmp_path / "config.json"
    fusionar_mcp(ruta, EXE)
    assert ruta.read_bytes()[:3] != b"\xef\xbb\xbf"


def test_fusionar_lee_un_archivo_con_bom(tmp_path):
    ruta = tmp_path / "config.json"
    ruta.write_text('{"mcpServers":{"otro":{}}}', encoding="utf-8-sig")

    assert fusionar_mcp(ruta, EXE) == "ok"
    assert "otro" in json.loads(ruta.read_text(encoding="utf-8"))["mcpServers"]


def test_fusionar_sobre_un_archivo_sin_mcpservers(tmp_path):
    ruta = tmp_path / "config.json"
    ruta.write_text('{"otraCosa": 1}', encoding="utf-8")

    assert fusionar_mcp(ruta, EXE) == "ok"

    datos = json.loads(ruta.read_text(encoding="utf-8"))
    assert datos["otraCosa"] == 1
    assert "odoo" in datos["mcpServers"]


# --- Quitar -------------------------------------------------------------------


def test_quitar_deja_el_resto_intacto(tmp_path):
    ruta = tmp_path / "config.json"
    ruta.write_text(
        json.dumps({"theme": "dark", "mcpServers": {"odoo": {}, "github": {}}}), encoding="utf-8"
    )

    assert quitar_mcp(ruta) is True

    datos = json.loads(ruta.read_text(encoding="utf-8"))
    assert datos["theme"] == "dark"
    assert list(datos["mcpServers"]) == ["github"]


def test_quitar_cuando_no_estaba(tmp_path):
    ruta = tmp_path / "config.json"
    ruta.write_text('{"mcpServers":{"github":{}}}', encoding="utf-8")
    assert quitar_mcp(ruta) is False


def test_quitar_archivo_inexistente():
    assert quitar_mcp(Path("no-existe-en-ningun-sitio.json")) is False


# --- Escritura de la configuracion --------------------------------------------


def test_escribir_config(tmp_path):
    ruta = tmp_path / "odoo-mcp" / "config.env"

    installer.escribir_config(ruta, "https://x.com", "base", "ana@x.com", "clave")

    texto = ruta.read_text(encoding="utf-8")
    assert "ODOO_URL=https://x.com" in texto
    assert "ODOO_PASSWORD=clave" in texto
    assert ruta.read_bytes()[:3] != b"\xef\xbb\xbf"


def test_lo_que_escribe_el_asistente_lo_lee_el_servidor(tmp_path):
    """La prueba que importa: las dos mitades tienen que encajar."""
    from odoo_mcp.config import load_settings

    ruta = tmp_path / "config.env"
    installer.escribir_config(ruta, "https://odoo.x.com", "produccion", "ana@x.com", "s3cr3t@=#")

    ajustes = load_settings({}, config_path=ruta)

    assert ajustes.url == "https://odoo.x.com"
    assert ajustes.db == "produccion"
    assert ajustes.username == "ana@x.com"
    assert ajustes.api_key == "s3cr3t@=#"


# --- Asistente completo -------------------------------------------------------


def test_asistente_de_punta_a_punta(tmp_path, monkeypatch, capsys):
    """Recorre el asistente entero con Odoo simulado: debe dejar escritas la
    configuracion y las dos entradas en Claude."""
    exe = tmp_path / "Programs" / "odoo-mcp" / "odoo-mcp.exe"
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"binario de mentira")
    config_env = tmp_path / "odoo-mcp" / "config.env"
    json_code = tmp_path / ".claude.json"
    json_desktop = tmp_path / "Claude" / "claude_desktop_config.json"
    json_code.write_text('{"mcpServers":{"otro":{"command":"foo"}}}', encoding="utf-8")
    json_desktop.parent.mkdir()

    monkeypatch.setattr(installer, "instalar_ejecutable", lambda: exe)
    monkeypatch.setattr(
        installer, "pedir_datos", lambda: ("https://odoo.x.com", "prod", "ana@x.com", "clave")
    )
    monkeypatch.setattr(installer, "verificar", lambda *a: "Ana Ruiz")
    monkeypatch.setattr(installer, "user_config_path", lambda: config_env)
    monkeypatch.setattr(installer, "config_claude_code", lambda: json_code)
    monkeypatch.setattr(installer, "configs_claude_desktop", lambda: [json_desktop])

    assert installer.asistente() == 0

    salida = capsys.readouterr().out
    assert "Ana Ruiz" in salida
    assert "Claude Code" in salida and "Claude Desktop" in salida

    assert "ODOO_DB=prod" in config_env.read_text(encoding="utf-8")
    code = json.loads(json_code.read_text(encoding="utf-8"))["mcpServers"]
    assert code["odoo"]["command"] == str(exe)
    assert code["otro"] == {"command": "foo"}  # no se pisa lo que ya habia
    desktop = json.loads(json_desktop.read_text(encoding="utf-8"))["mcpServers"]
    assert desktop["odoo"]["args"] == ["--mcp"]


def test_asistente_se_detiene_si_odoo_rechaza_la_credencial(tmp_path, monkeypatch):
    """Si la contrasena falla no se debe escribir nada: ni config ni registro."""
    from odoo_mcp.client import OdooError

    exe = tmp_path / "odoo-mcp.exe"
    config_env = tmp_path / "odoo-mcp" / "config.env"
    json_code = tmp_path / ".claude.json"

    def revienta(*a):
        raise OdooError("Autenticación fallida: revisa ODOO_DB.")

    monkeypatch.setattr(installer, "instalar_ejecutable", lambda: exe)
    monkeypatch.setattr(
        installer, "pedir_datos", lambda: ("https://odoo.x.com", "prod", "ana@x.com", "mala")
    )
    monkeypatch.setattr(installer, "verificar", revienta)
    monkeypatch.setattr(installer, "user_config_path", lambda: config_env)
    monkeypatch.setattr(installer, "config_claude_code", lambda: json_code)
    monkeypatch.setattr(installer, "configs_claude_desktop", lambda: [])

    with pytest.raises(InstallerError, match="Autenticación fallida"):
        installer.asistente()

    assert not config_env.exists()
    assert not json_code.exists()


def test_desinstalar_limpia_los_dos_clientes(tmp_path, monkeypatch):
    json_code = tmp_path / ".claude.json"
    json_desktop = tmp_path / "claude_desktop_config.json"
    json_code.write_text('{"mcpServers":{"odoo":{},"otro":{}}}', encoding="utf-8")
    json_desktop.write_text('{"mcpServers":{"odoo":{}}}', encoding="utf-8")

    monkeypatch.setattr(installer, "config_claude_code", lambda: json_code)
    monkeypatch.setattr(installer, "configs_claude_desktop", lambda: [json_desktop])
    monkeypatch.setattr(installer, "destino_ejecutable", lambda: tmp_path / "no-existe.exe")
    monkeypatch.setattr(installer, "user_config_path", lambda: tmp_path / "no-existe.env")

    assert installer.desinstalar() == 0

    assert list(json.loads(json_code.read_text(encoding="utf-8"))["mcpServers"]) == ["otro"]
    assert json.loads(json_desktop.read_text(encoding="utf-8"))["mcpServers"] == {}


def test_pedir_clave_sin_consola_usa_la_entrada_estandar(monkeypatch):
    """getpass se cuelga si no hay consola: hay que caer a input()."""
    monkeypatch.setattr(installer.sys, "stdin", None)
    monkeypatch.setattr("builtins.input", lambda *a: "  clave-por-tuberia  ")
    assert installer.pedir_clave("Contraseña") == "clave-por-tuberia"


def test_pedir_clave_usa_getpass_si_hay_consola(monkeypatch):
    class ConsolaFalsa:
        def isatty(self):
            return True

    monkeypatch.setattr(installer.sys, "stdin", ConsolaFalsa())
    monkeypatch.setattr(installer, "getpass", lambda *a: "oculta")
    assert installer.pedir_clave("Contraseña") == "oculta"


def test_reregistrar_no_pide_datos_ni_toca_la_configuracion(tmp_path, monkeypatch, capsys):
    """Quien instala Claude Desktop despues no deberia teclear su clave otra vez."""
    exe = tmp_path / "odoo-mcp.exe"
    exe.write_bytes(b"x")
    config_env = tmp_path / "config.env"
    config_env.write_text("ODOO_URL=https://x.com\n", encoding="utf-8")
    json_desktop = tmp_path / "claude_desktop_config.json"

    monkeypatch.setattr(installer, "instalar_ejecutable", lambda: exe)
    monkeypatch.setattr(installer, "config_claude_code", lambda: tmp_path / "no-hay.json")
    monkeypatch.setattr(installer, "configs_claude_desktop", lambda: [json_desktop])
    monkeypatch.setattr(installer, "user_config_path", lambda: config_env)
    monkeypatch.setattr("builtins.input", lambda *a: pytest.fail("no debe preguntar nada"))

    assert installer.reregistrar() == 0

    assert "odoo" in json.loads(json_desktop.read_text(encoding="utf-8"))["mcpServers"]
    assert config_env.read_text(encoding="utf-8") == "ODOO_URL=https://x.com\n"
    assert "Claude Desktop" in capsys.readouterr().out


def test_no_escribe_en_claude_desktop_si_esta_abierto(tmp_path, monkeypatch, capsys):
    """Con la app abierta, ella reescribe su config y borraria nuestra entrada."""
    json_desktop = tmp_path / "claude_desktop_config.json"
    json_desktop.write_text('{"preferences":{}}', encoding="utf-8")

    monkeypatch.setattr(installer, "config_claude_code", lambda: tmp_path / "no-hay.json")
    monkeypatch.setattr(installer, "configs_claude_desktop", lambda: [json_desktop])
    monkeypatch.setattr(installer, "claude_desktop_abierto", lambda: True)
    monkeypatch.setattr(installer, "preguntar", lambda *a, **k: "")

    configurados = installer.registrar(tmp_path / "odoo-mcp.exe")

    assert "Claude Desktop" not in configurados
    assert json_desktop.read_text(encoding="utf-8") == '{"preferences":{}}'
    assert "sigue abierto" in capsys.readouterr().out


def test_escribe_cuando_claude_desktop_esta_cerrado(tmp_path, monkeypatch):
    json_desktop = tmp_path / "claude_desktop_config.json"
    json_desktop.write_text('{"preferences":{}}', encoding="utf-8")

    monkeypatch.setattr(installer, "config_claude_code", lambda: tmp_path / "no-hay.json")
    monkeypatch.setattr(installer, "configs_claude_desktop", lambda: [json_desktop])
    monkeypatch.setattr(installer, "claude_desktop_abierto", lambda: False)

    configurados = installer.registrar(tmp_path / "odoo-mcp.exe")

    assert "Claude Desktop" in configurados
    datos = json.loads(json_desktop.read_text(encoding="utf-8"))
    assert "odoo" in datos["mcpServers"]
    assert datos["preferences"] == {}  # no se pierden sus preferencias
