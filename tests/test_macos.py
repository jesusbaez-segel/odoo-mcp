"""Rutas y detecciones propias de macOS.

Se ejecutan en cualquier plataforma simulando sys.platform: el binario de Mac hay
que construirlo en un Mac, pero la lógica de rutas sí se puede comprobar aquí.
"""

import sys
from pathlib import Path

import pytest

from odoo_mcp import config, installer


def simular_mac(monkeypatch, home: Path):
    # No se toca os.name: pathlib lo usa para elegir el tipo de ruta y romperia
    # a pytest entero. sys.platform es solo informativo y basta.
    monkeypatch.setattr(installer.sys, "platform", "darwin")
    monkeypatch.setattr(config.sys, "platform", "darwin")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))


def test_config_en_application_support(monkeypatch, tmp_path):
    simular_mac(monkeypatch, tmp_path)
    ruta = config.user_config_path()
    assert ruta == tmp_path / "Library/Application Support/odoo-mcp/config.env"


def test_el_ejecutable_no_lleva_exe(monkeypatch, tmp_path):
    simular_mac(monkeypatch, tmp_path)
    assert installer.nombre_ejecutable() == "odoo-mcp"
    assert installer.destino_ejecutable() == (
        tmp_path / "Library/Application Support/odoo-mcp/odoo-mcp"
    )


def test_claude_desktop_en_application_support(monkeypatch, tmp_path):
    simular_mac(monkeypatch, tmp_path)
    carpeta = tmp_path / "Library/Application Support/Claude"
    carpeta.mkdir(parents=True)

    rutas = installer.configs_claude_desktop()

    assert rutas == [carpeta / "claude_desktop_config.json"]


def test_sin_claude_desktop_en_mac(monkeypatch, tmp_path):
    simular_mac(monkeypatch, tmp_path)
    assert installer.configs_claude_desktop() == []


def test_en_mac_no_mira_las_rutas_de_windows(monkeypatch, tmp_path):
    """APPDATA no debe colarse: en un Mac esa variable no significa nada."""
    simular_mac(monkeypatch, tmp_path)
    (tmp_path / "roaming" / "Claude").mkdir(parents=True)
    monkeypatch.setenv("APPDATA", str(tmp_path / "roaming"))

    assert installer.configs_claude_desktop() == []


def test_deteccion_de_claude_desktop_usa_pgrep(monkeypatch, tmp_path):
    simular_mac(monkeypatch, tmp_path)
    llamadas = []

    class Resultado:
        returncode = 0

    def falso_run(cmd, **kwargs):
        llamadas.append(cmd)
        return Resultado()

    monkeypatch.setattr(installer.subprocess, "run", falso_run)

    assert installer.claude_desktop_abierto() is True
    # -x (nombre exacto) es lo que evita confundirlo con "claude" de Claude Code
    assert llamadas == [["pgrep", "-x", "Claude"]]


def test_deteccion_falsa_cuando_no_corre(monkeypatch, tmp_path):
    simular_mac(monkeypatch, tmp_path)

    class Resultado:
        returncode = 1

    monkeypatch.setattr(installer.subprocess, "run", lambda cmd, **k: Resultado())
    assert installer.claude_desktop_abierto() is False


def test_quita_la_cuarentena_al_instalar(monkeypatch, tmp_path):
    """Sin esto, Gatekeeper impide que Claude arranque el servidor copiado."""
    simular_mac(monkeypatch, tmp_path)
    llamadas = []

    class Resultado:
        returncode = 0

    monkeypatch.setattr(
        installer.subprocess, "run", lambda cmd, **k: (llamadas.append(cmd), Resultado())[1]
    )

    assert installer.quitar_cuarentena(tmp_path / "odoo-mcp") is True
    assert llamadas[0][:3] == ["xattr", "-dr", "com.apple.quarantine"]


def test_en_windows_no_se_llama_a_xattr(monkeypatch, tmp_path):
    monkeypatch.setattr(installer.sys, "platform", "win32")
    assert installer.quitar_cuarentena(tmp_path / "odoo-mcp.exe") is False


@pytest.mark.skipif(sys.platform == "win32", reason="chmod no aplica bits POSIX en Windows")
def test_permisos_del_archivo_de_credenciales_en_mac(monkeypatch, tmp_path):
    """En Windows se usa icacls; en Mac, chmod 600."""
    simular_mac(monkeypatch, tmp_path)
    ruta = tmp_path / "config.env"
    ruta.write_text("ODOO_URL=https://x.com", encoding="utf-8")

    assert installer.restringir_permisos(ruta) is True
    assert ruta.stat().st_mode & 0o777 == 0o600


def test_el_guion_de_deteccion_no_tiene_caracteres_raros():
    """Regresion: el patron de rutas de Windows lleva barras invertidas y, sin
    cadena literal, Python convierte la de app en el caracter BEL; el patron
    deja entonces de coincidir con nada y la deteccion siempre dice que no."""
    from odoo_mcp.installer import GUION_DETECCION_WINDOWS as guion

    barra = chr(92)
    assert barra + "Claude" + barra + "app" + barra in guion
    assert "WindowsApps" in guion
    assert "AnthropicClaude" in guion
    assert [c for c in guion if ord(c) < 32] == []
