"""Configuración del servidor a partir de variables de entorno."""

from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass


class ConfigError(Exception):
    """Configuración inválida o incompleta."""


@dataclass(frozen=True)
class Settings:
    url: str
    db: str
    username: str
    api_key: str


_ENV_VARS = {
    "url": "ODOO_URL",
    "db": "ODOO_DB",
    "username": "ODOO_USERNAME",
    "api_key": "ODOO_API_KEY",
}


def _running_in_docker() -> bool:
    return os.path.exists("/.dockerenv")


def adjust_url_for_docker(url: str, in_docker: bool) -> str:
    """Dentro del contenedor, localhost apunta al propio contenedor y no al host
    donde corre Odoo; Docker Desktop expone el host como host.docker.internal."""
    if not in_docker:
        return url
    adjusted = re.sub(r"(?<=://)(localhost|127\.0\.0\.1)", "host.docker.internal", url, count=1)
    if adjusted != url:
        print(
            f"odoo-mcp: ODOO_URL reescrita {url!r} -> {adjusted!r} (localhost no es "
            "alcanzable desde dentro del contenedor)",
            file=sys.stderr,
        )
    return adjusted


def load_settings(environ: dict[str, str] | None = None) -> Settings:
    env = os.environ if environ is None else environ
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
            "Faltan variables de entorno: "
            + ", ".join(missing)
            + ". Configura ODOO_URL, ODOO_DB, ODOO_USERNAME y ODOO_API_KEY (o "
            "ODOO_PASSWORD) en el archivo .env. La API key se genera en Odoo: "
            "Preferencias -> Seguridad de la cuenta -> Claves API."
        )
    values["url"] = adjust_url_for_docker(values["url"].rstrip("/"), _running_in_docker())
    return Settings(**values)
