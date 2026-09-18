"""Filtro de stdin que descarta las líneas en blanco.

El transporte stdio del SDK (mcp/server/stdio.py) pasa *todas* las líneas que lee
a `JSONRPCMessage.model_validate_json`, incluidas las vacías. Una línea en blanco
del cliente provoca un error ruidoso ("Invalid JSON: EOF while parsing a value")
y una notificación de "Internal Server Error", aunque la sesión sigue viva.

Como el SDK solo lee `sys.stdin.buffer`, basta con envolver ese buffer: no se
tocan sus interioridades. De paso normaliza los finales de línea \\r\\n a \\n.

Es seguro colapsar saltos de línea consecutivos: en JSON-RPC los mensajes van
delimitados por saltos de línea y un salto dentro de una cadena JSON siempre
viaja escapado como \\n, nunca como byte 0x0A.
"""

from __future__ import annotations

import io
import sys

_LF = 10
_CR = 13


class SkipBlankLines(io.BufferedIOBase):
    """Envoltorio binario de solo lectura que elimina las líneas vacías."""

    def __init__(self, raw: io.BufferedIOBase):
        self._raw = raw
        # True mientras no se haya emitido ningún byte de la línea en curso: un
        # salto de línea en ese estado cierra una línea vacía y se descarta.
        self._at_line_start = True

    def readable(self) -> bool:
        return True

    def _filter(self, chunk: bytes) -> bytes:
        out = bytearray()
        for byte in chunk:
            if byte in (_LF, _CR):
                if self._at_line_start:
                    continue
                out.append(_LF)
                self._at_line_start = True
            else:
                out.append(byte)
                self._at_line_start = False
        return bytes(out)

    def _pull(self, size: int) -> bytes:
        # Si un bloque entero eran lineas vacias no se puede devolver b"": el
        # lector lo interpretaria como fin de fichero. Se sigue leyendo.
        while True:
            chunk = self._raw.read1(size) if hasattr(self._raw, "read1") else self._raw.read(size)
            if not chunk:
                return b""  # EOF real
            filtered = self._filter(chunk)
            if filtered:
                return filtered

    def read(self, size: int | None = -1) -> bytes:
        return self._pull(-1 if size is None else size)

    def read1(self, size: int = -1) -> bytes:
        return self._pull(size)


def install() -> None:
    """Reemplaza sys.stdin por uno que ignora las líneas en blanco."""
    if sys.stdin is None:  # sin consola (p. ej. arrancado sin stdin)
        return
    try:
        buffer = sys.stdin.buffer
    except (AttributeError, ValueError):
        return
    sys.stdin = io.TextIOWrapper(SkipBlankLines(buffer), encoding="utf-8", errors="replace")
