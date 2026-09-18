"""El transporte del SDK valida como JSON cada linea que lee, incluidas las
vacias. Estas pruebas cubren el filtro que las descarta antes de llegar ahi."""

import io

from odoo_mcp.stdio_filter import SkipBlankLines

BARRA = bytes([92])  # '\' sin ambiguedades de escapado en este archivo


def leer_lineas(datos: bytes, chunk: int = 8192) -> list[str]:
    """Lee igual que el SDK: TextIOWrapper sobre el buffer, iterando lineas."""
    envuelto = SkipBlankLines(io.BufferedReader(io.BytesIO(datos)))
    return list(io.TextIOWrapper(envuelto, encoding="utf-8", errors="replace"))


def test_descarta_lineas_en_blanco():
    assert leer_lineas(b'{"a":1}\n\n{"b":2}\n') == ['{"a":1}\n', '{"b":2}\n']


def test_descarta_varias_seguidas():
    assert leer_lineas(b'\n\n\n{"a":1}\n\n\n\n{"b":2}\n\n') == ['{"a":1}\n', '{"b":2}\n']


def test_normaliza_crlf():
    assert leer_lineas(b'{"a":1}\r\n{"b":2}\r\n') == ['{"a":1}\n', '{"b":2}\n']


def test_solo_cr():
    assert leer_lineas(b'{"a":1}\r{"b":2}\r') == ['{"a":1}\n', '{"b":2}\n']


def test_sin_salto_final():
    assert leer_lineas(b'{"a":1}') == ['{"a":1}']


def test_entrada_vacia():
    assert leer_lineas(b"") == []


def test_todo_lineas_en_blanco_es_fin_de_fichero():
    """Si solo llegan lineas vacias hay que llegar al EOF real, no colgarse."""
    assert leer_lineas(b"\n\n\n\n") == []


def test_mensaje_partido_entre_bloques():
    """El estado del filtro tiene que sobrevivir al corte de un bloque."""
    envuelto = SkipBlankLines(io.BufferedReader(io.BytesIO(b'{"largo":123}\n\n{"otro":4}\n')))
    trozos = []
    while True:
        t = envuelto.read1(5)  # bloques minusculos: cortes en sitios raros
        if not t:
            break
        trozos.append(t)
    assert b"".join(trozos) == b'{"largo":123}\n{"otro":4}\n'


def test_no_toca_saltos_escapados_dentro_del_json():
    """Un salto de linea dentro de una cadena JSON viaja escapado como \\n (dos
    bytes), nunca como 0x0A: el filtro no debe partir el mensaje por ahi."""
    mensaje = b'{"texto":"linea1' + BARRA + b'nlinea2"}'
    lineas = leer_lineas(mensaje + b"\n\n" + b'{"b":2}' + b"\n")
    assert lineas == [mensaje.decode() + "\n", '{"b":2}\n']
    # y sigue siendo JSON valido con el salto de linea dentro de la cadena
    import json

    assert json.loads(lineas[0])["texto"] == "linea1\nlinea2"
