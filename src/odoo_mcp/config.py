"""Configuración del servidor: variables de entorno y archivo de configuración.

El ejecutable lo arranca Claude sin argumentos ni variables, así que los datos de
conexión se leen de un archivo que escribe el asistente de instalación. Las
variables del entorno siguen teniendo prioridad (útil en desarrollo y en CI).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

CONFIG_ENV_VAR = "ODOO_MCP_CONFIG"
CONFIG_DIRNAME = "odoo-mcp"
CONFIG_FILENAME = "config.env"


class ConfigError(Exception):
    """Configuración inválida o incompleta."""


@dataclass(frozen=True)
class Settings:
    url: str
    db: str
    username: str
    api_key: str
    timeout: float = 60.0


_ENV_VARS = {
    "url": "ODOO_URL",
    "db": "ODOO_DB",
    "username": "ODOO_USERNAME",
    "api_key": "ODOO_API_KEY",
}


def user_config_path() -> Path:
    """Archivo donde el asistente de instalación guarda los datos de Odoo."""
    base = os.environ.get("APPDATA")  # Windows
    if base:
        return Path(base) / CONFIG_DIRNAME / CONFIG_FILENAME
    return Path.home() / ".config" / CONFIG_DIRNAME / CONFIG_FILENAME


def config_search_paths(environ: dict[str, str] | None = None) -> list[Path]:
    """Rutas candidatas, de mayor a menor prioridad."""
    env = os.environ if environ is None else environ
    paths: list[Path] = []
    explicit = env.get(CONFIG_ENV_VAR, "").strip()
    if explicit:
        paths.append(Path(explicit))
    paths.append(user_config_path())
    paths.append(Path.cwd() / ".env")  # comodidad al desarrollar en el repositorio
    return paths


def parse_env_file(text: str) -> dict[str, str]:
    """CLAVE=valor por línea. Admite comentarios con '#', 'export' al principio y
    comillas envolventes. Las líneas que no encajan se ignoran: un archivo algo
    sucio no debe impedir que el servidor arranque."""
    values: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        key, sep, value = line.partition("=")
        key = key.strip()
        if not sep or not key:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key] = value
    return values


def read_env_file(path: Path) -> dict[str, str]:
    """Valores del archivo indicado; {} si no existe o no se puede leer."""
    try:
        text = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError):
        return {}
    return parse_env_file(text)


def _first_existing_config(paths: list[Path]) -> dict[str, str]:
    for path in paths:
        values = read_env_file(path)
        if values:
            return values
    return {}


def load_settings(
    environ: dict[str, str] | None = None,
    config_path: Path | str | None = None,
) -> Settings:
    """Con `environ` explícito no se busca ningún archivo salvo que se pase
    `config_path`; así las pruebas no dependen de la máquina que las ejecuta."""
    if environ is None:
        env_source = dict(os.environ)
        file_values = (
            read_env_file(Path(config_path))
            if config_path is not None
            else _first_existing_config(config_search_paths(env_source))
        )
    else:
        env_source = dict(environ)
        file_values = read_env_file(Path(config_path)) if config_path is not None else {}

    env = dict(file_values)
    # El entorno del proceso gana, pero un valor vacío no debe pisar al archivo.
    env.update({k: v for k, v in env_source.items() if str(v).strip()})

    values: dict[str, str] = {}
    missing: list[str] = []
    for field, var in _ENV_VARS.items():
        value = env.get(var, "").strip()
        if field == "api_key" and not value:
            value = env.get("ODOO_PASSWORD", "").strip()
        if not value:
            missing.append(var)
        values[field] = value
    if missing:
        raise ConfigError(
            "Faltan datos de conexión: "
            + ", ".join(missing)
            + f". Vuelve a ejecutar el asistente (instalar.bat) o edita {user_config_path()} "
            "con ODOO_URL, ODOO_DB, ODOO_USERNAME y ODOO_API_KEY (o ODOO_PASSWORD). "
            "La API key se genera en Odoo: Preferencias -> Seguridad de la cuenta -> Claves API."
        )
    values["url"] = values["url"].rstrip("/")
    raw_timeout = env.get("ODOO_TIMEOUT", "").strip()
    try:
        timeout = float(raw_timeout) if raw_timeout else 60.0
    except ValueError:
        raise ConfigError(f"ODOO_TIMEOUT debe ser un número de segundos, no {raw_timeout!r}.")
    return Settings(timeout=timeout, **values)
