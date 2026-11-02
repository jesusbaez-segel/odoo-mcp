"""Cliente XML-RPC para la API externa de Odoo."""

from __future__ import annotations

import threading
import xmlrpc.client
from typing import Any

from .config import Settings


class OdooError(Exception):
    """Error devuelto por Odoo o por la conexión, con mensaje legible."""


def _fault_message(fault: xmlrpc.client.Fault) -> str:
    text = str(fault.faultString or "").strip()
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) > 1 and "Traceback" in text:
        return f"Odoo: {lines[-1]}"
    return f"Odoo: {text or fault.faultCode}"


class _TimeoutTransport(xmlrpc.client.Transport):
    """Sin timeout, una llamada colgada bloquearía la tool para siempre."""

    def __init__(self, timeout: float):
        super().__init__()
        self._timeout = timeout

    def make_connection(self, host):
        connection = super().make_connection(host)
        connection.timeout = self._timeout
        return connection


class _TimeoutSafeTransport(xmlrpc.client.SafeTransport):
    def __init__(self, timeout: float):
        super().__init__()
        self._timeout = timeout

    def make_connection(self, host):
        connection = super().make_connection(host)
        connection.timeout = self._timeout
        return connection


def _make_proxy(base: str, path: str, timeout: float) -> xmlrpc.client.ServerProxy:
    transport_cls = _TimeoutSafeTransport if base.startswith("https") else _TimeoutTransport
    return xmlrpc.client.ServerProxy(
        f"{base}{path}", allow_none=True, transport=transport_cls(timeout)
    )


class OdooClient:
    def __init__(self, settings: Settings):
        self._settings = settings
        base = settings.url.rstrip("/")
        self._common = _make_proxy(base, "/xmlrpc/2/common", settings.timeout)
        self._object = _make_proxy(base, "/xmlrpc/2/object", settings.timeout)
        self._uid: int | None = None
        self._server_major: int | None = None
        self._fields_cache: dict[str, dict[str, dict[str, Any]]] = {}
        # xmlrpc.client no es thread-safe y las tools async pueden solaparse
        self._lock = threading.Lock()

    @property
    def base_url(self) -> str:
        return self._settings.url.rstrip("/")

    @property
    def database(self) -> str:
        return self._settings.db

    def uid(self) -> int:
        """Id del usuario autenticado; autentica en la primera llamada."""
        with self._lock:
            return self._authenticate()

    def _authenticate(self) -> int:
        if self._uid is None:
            try:
                uid = self._common.authenticate(
                    self._settings.db, self._settings.username, self._settings.api_key, {}
                )
            except xmlrpc.client.Fault as fault:
                raise OdooError(_fault_message(fault)) from fault
            except (OSError, xmlrpc.client.Error) as exc:
                raise OdooError(
                    f"No se pudo conectar con Odoo en {self.base_url}: {exc}"
                ) from exc
            if not uid:
                # Claude repite este texto al usuario: debe decir qué datos se usaron y
                # cómo corregirlos (pedir "una clave API" no sirve en Odoo 13).
                raise OdooError(
                    f"Autenticación fallida: Odoo rechaza el usuario "
                    f"'{self._settings.username}' o su contraseña en la base "
                    f"'{self._settings.db}' ({self.base_url}). Usa la contraseña con la que "
                    "entras a Odoo, o una clave API (solo existen desde Odoo 14). Para cambiar "
                    "los datos guardados, abre de nuevo el instalador de odoo-mcp y elige "
                    "'Cambiar mis datos de Odoo'."
                )
            self._uid = uid
        return self._uid

    def execute(
        self,
        model: str,
        method: str,
        args: list | None = None,
        kwargs: dict | None = None,
    ) -> Any:
        with self._lock:
            uid = self._authenticate()
            try:
                return self._object.execute_kw(
                    self._settings.db,
                    uid,
                    self._settings.api_key,
                    model,
                    method,
                    args or [],
                    kwargs or {},
                )
            except xmlrpc.client.Fault as fault:
                raise OdooError(_fault_message(fault)) from fault
            except (OSError, xmlrpc.client.Error) as exc:
                raise OdooError(f"Error de conexión con Odoo: {exc}") from exc

    def server_major(self) -> int:
        """Versión mayor del servidor Odoo (13, 14, ... ); 0 si no se pudo saber."""
        if self._server_major is None:
            try:
                info = self._common.version()
                self._server_major = int(info["server_version_info"][0])
            except (OSError, xmlrpc.client.Error, KeyError, ValueError, TypeError):
                self._server_major = 0
        return self._server_major

    def fields_info(self, model: str) -> dict[str, dict[str, Any]]:
        """fields_get cacheado con los atributos mínimos para adaptar el código
        a la versión de Odoo (p. ej. user_ids vs user_id)."""
        if model not in self._fields_cache:
            self._fields_cache[model] = self.execute(
                model, "fields_get", [], {"attributes": ["type", "string", "relation"]}
            )
        return self._fields_cache[model]
