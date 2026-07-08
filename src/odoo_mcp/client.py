"""Cliente XML-RPC para la API externa de Odoo."""

from __future__ import annotations

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


class OdooClient:
    def __init__(self, settings: Settings):
        self._settings = settings
        base = settings.url.rstrip("/")
        self._common = xmlrpc.client.ServerProxy(f"{base}/xmlrpc/2/common", allow_none=True)
        self._object = xmlrpc.client.ServerProxy(f"{base}/xmlrpc/2/object", allow_none=True)
        self._uid: int | None = None
        self._fields_cache: dict[str, dict[str, dict[str, Any]]] = {}

    @property
    def base_url(self) -> str:
        return self._settings.url.rstrip("/")

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
                raise OdooError(
                    "Autenticación fallida: revisa ODOO_DB, ODOO_USERNAME y ODOO_API_KEY."
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

    def fields_info(self, model: str) -> dict[str, dict[str, Any]]:
        """fields_get cacheado con los atributos mínimos para adaptar el código
        a la versión de Odoo (p. ej. user_ids vs user_id)."""
        if model not in self._fields_cache:
            self._fields_cache[model] = self.execute(
                model, "fields_get", [], {"attributes": ["type", "string", "relation"]}
            )
        return self._fields_cache[model]
