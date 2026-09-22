"""Prueba de humo del ejecutable empaquetado, en la plataforma donde se ejecuta.

    python packaging/smoke_test.py dist/odoo-mcp.exe

La ejecuta GitHub Actions contra cada binario recién compilado (Windows, Mac
Apple Silicon, Mac Intel), de modo que un Mac real comprueba lo que desde
Windows no se puede: que el binario arranca, habla MCP, y que el asistente
instala y registra en las rutas de macOS. Solo usa la biblioteca estándar.

Todo ocurre en un HOME/APPDATA temporal: nunca toca la configuración real.
"""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

# Puerto 9 (discard): la conexión se rechaza al instante, sin depender de DNS ni
# de tener un Odoo a mano. Sirve para provocar el camino de error del asistente.
ODOO_INALCANZABLE = "http://127.0.0.1:9"

fallos: list[str] = []


def comprobar(condicion: bool, texto: str) -> None:
    print(f"  {'OK ' if condicion else 'FALLO'}  {texto}")
    if not condicion:
        fallos.append(texto)


def limpiar(texto: bytes) -> str:
    salida = texto.decode("utf-8", "replace")
    for codigo in ("\x1b[92m", "\x1b[93m", "\x1b[91m", "\x1b[96m", "\x1b[90m", "\x1b[0m"):
        salida = salida.replace(codigo, "")
    return salida


def entorno_aislado(raiz: Path) -> dict[str, str]:
    """Redirige todo lo que el asistente consulta para decidir rutas."""
    env = dict(os.environ)
    perfil = raiz / "perfil"
    perfil.mkdir(parents=True, exist_ok=True)
    env["HOME"] = str(perfil)  # Path.home() en macOS/Linux
    env["USERPROFILE"] = str(perfil)  # Path.home() en Windows
    env["APPDATA"] = str(raiz / "roaming")
    env["LOCALAPPDATA"] = str(raiz / "local")
    env.pop("ODOO_MCP_CONFIG", None)
    return env


def rutas_esperadas(raiz: Path) -> tuple[Path, Path, Path, Path]:
    """(ejecutable instalado, config.env, .claude.json, claude_desktop_config.json)
    tal como deberían quedar en esta plataforma."""
    perfil = raiz / "perfil"
    if sys.platform == "darwin":
        soporte = perfil / "Library" / "Application Support"
        return (
            soporte / "odoo-mcp" / "odoo-mcp",
            soporte / "odoo-mcp" / "config.env",
            perfil / ".claude.json",
            soporte / "Claude" / "claude_desktop_config.json",
        )
    if sys.platform == "win32":
        return (
            raiz / "local" / "Programs" / "odoo-mcp" / "odoo-mcp.exe",
            raiz / "roaming" / "odoo-mcp" / "config.env",
            perfil / ".claude.json",
            raiz / "roaming" / "Claude" / "claude_desktop_config.json",
        )
    return (
        perfil / ".local" / "share" / "odoo-mcp" / "odoo-mcp",
        perfil / ".config" / "odoo-mcp" / "config.env",
        perfil / ".claude.json",
        perfil / ".config" / "Claude" / "claude_desktop_config.json",  # no aplica
    )


def ejecutar(exe: Path, args: list[str], env: dict[str, str], entrada: bytes = b"") -> subprocess.CompletedProcess:
    # cwd=HOME del sandbox: el servidor lee ./.env como comodidad de desarrollo y
    # el repositorio tiene uno de verdad que contaminaria la prueba.
    return subprocess.run(
        [str(exe), *args], input=entrada, capture_output=True, env=env, cwd=env["HOME"], timeout=180
    )


# --- 1. Arranque ----------------------------------------------------------------


def prueba_arranque(exe: Path, env: dict[str, str]) -> None:
    print("\n[1] Arranque")
    r = ejecutar(exe, ["--version"], env)
    comprobar(r.returncode == 0 and b"odoo-mcp" in r.stdout, f"--version -> {r.stdout.decode().strip()}")
    r = ejecutar(exe, ["--help"], env)
    comprobar(r.returncode == 0 and b"--mcp" in r.stdout, "--help lista los argumentos")
    r = ejecutar(exe, ["--argumento-inventado"], env)
    comprobar(r.returncode == 2, "argumento desconocido devuelve 2")


# --- 2. Protocolo MCP -----------------------------------------------------------


def prueba_mcp(exe: Path, env: dict[str, str], args: list[str]) -> None:
    etiqueta = " ".join(args) or "(sin argumentos, stdin es tubería)"
    print(f"\n[2] Servidor MCP por stdio: {etiqueta}")
    p = subprocess.Popen(
        [str(exe), *args],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        cwd=env["HOME"],
    )

    def enviar(obj: dict) -> None:
        assert p.stdin is not None
        p.stdin.write((json.dumps(obj) + "\n").encode())
        p.stdin.flush()

    def leer(id_esperado: int | None = None) -> dict | None:
        assert p.stdout is not None
        for _ in range(6):  # saltar notificaciones intermedias
            linea = p.stdout.readline()
            if not linea:
                return None
            mensaje = json.loads(linea)
            if id_esperado is None or mensaje.get("id") == id_esperado:
                return mensaje
        return None

    try:
        enviar(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "smoke", "version": "1"},
                },
            }
        )
        init = leer(1)
        comprobar(
            bool(init and init.get("result", {}).get("serverInfo", {}).get("name") == "odoo"),
            "initialize responde con serverInfo.name = odoo",
        )
        enviar({"jsonrpc": "2.0", "method": "notifications/initialized"})

        # Líneas en blanco y \r\n: no deben producir errores ni tumbar la sesión
        assert p.stdin is not None
        p.stdin.write(b"\n\r\n\n")
        p.stdin.flush()

        enviar({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        tools = leer(2)
        nombres = sorted(t["name"] for t in (tools or {}).get("result", {}).get("tools", []))
        comprobar(len(nombres) == 21, f"tools/list devuelve 21 herramientas (hay {len(nombres)})")
        comprobar("list_projects" in nombres and "call_method" in nombres, "incluye list_projects y call_method")

        enviar({"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "list_projects", "arguments": {}}})
        llamada = leer(3)
        texto = json.dumps(llamada or {}, ensure_ascii=False)
        comprobar(
            "Faltan datos de conexi" in texto,
            f"sin configuración, una tool devuelve el error legible (no una traza): {texto[:90]}",
        )
    finally:
        assert p.stdin is not None
        p.stdin.close()
        try:
            codigo = p.wait(timeout=15)
            comprobar(codigo == 0, f"termina solo al cerrar stdin (código {codigo})")
        except subprocess.TimeoutExpired:
            p.kill()
            comprobar(False, "NO termina al cerrar stdin: dejaría un proceso huérfano")
        err = limpiar(p.stderr.read() if p.stderr else b"")
        comprobar("Received exception" not in err, "stderr sin errores de validación por líneas en blanco")


# --- 3. Asistente: credencial rechazada ---------------------------------------


def prueba_asistente_rechaza(exe: Path, env: dict[str, str], raiz: Path) -> None:
    print("\n[3] Asistente con Odoo inalcanzable: debe pararse sin escribir nada")
    instalado, config_env, json_code, json_desktop = rutas_esperadas(raiz)
    json_code.parent.mkdir(parents=True, exist_ok=True)
    json_code.write_text('{"mcpServers":{"otro":{"command":"x"}}}', encoding="utf-8")

    respuestas = f"{ODOO_INALCANZABLE}\nbase\nana@x.com\nclave\n\n".encode()
    r = ejecutar(exe, ["--instalar"], env, respuestas)
    salida = limpiar(r.stdout)
    comprobar(r.returncode == 1, f"sale con código 1 (salió {r.returncode})")
    comprobar("No se pudo conectar" in salida or "conectar" in salida, "explica que no pudo conectar")
    comprobar(instalado.exists(), "el ejecutable sí se copió a su carpeta fija (paso 1)")
    comprobar(not config_env.exists(), "config.env NO se escribió")
    comprobar(
        json.loads(json_code.read_text(encoding="utf-8"))["mcpServers"] == {"otro": {"command": "x"}},
        ".claude.json quedó intacto",
    )
    if sys.platform != "win32":
        comprobar(bool(instalado.stat().st_mode & stat.S_IXUSR), "el binario instalado es ejecutable (chmod +x)")


# --- 4. --registrar --------------------------------------------------------------


def prueba_registrar(exe: Path, env: dict[str, str], raiz: Path) -> None:
    print("\n[4] --registrar: registra en Claude Code y Claude Desktop sin pedir datos")
    instalado, config_env, json_code, json_desktop = rutas_esperadas(raiz)
    if sys.platform == "linux":
        print("  (Linux no tiene Claude Desktop; se comprueba solo Claude Code)")
    else:
        json_desktop.parent.mkdir(parents=True, exist_ok=True)
        json_desktop.write_text('{"preferences":{"tema":"oscuro"}}', encoding="utf-8")

    r = ejecutar(exe, ["--registrar"], env, b"\n")
    salida = limpiar(r.stdout)
    comprobar(r.returncode == 0, f"sale con código 0 (salió {r.returncode})")
    comprobar("Claude Code: configurado" in salida, "informa Claude Code configurado")

    code = json.loads(json_code.read_text(encoding="utf-8"))["mcpServers"]
    comprobar(code.get("odoo", {}).get("command") == str(instalado), f"Claude Code apunta a {instalado}")
    comprobar(code.get("odoo", {}).get("args") == ["--mcp"], "con args ['--mcp']")
    comprobar("otro" in code, "conserva el otro servidor MCP que ya había")

    if sys.platform != "linux":
        comprobar("Claude Desktop: configurado" in salida, "informa Claude Desktop configurado")
        desktop = json.loads(json_desktop.read_text(encoding="utf-8"))
        comprobar(desktop.get("mcpServers", {}).get("odoo", {}).get("command") == str(instalado), "Claude Desktop apunta al instalado")
        comprobar(desktop.get("preferences") == {"tema": "oscuro"}, "conserva las preferencias de Claude Desktop")
        comprobar(json_desktop.with_suffix(".json.bak").exists(), "dejó copia .bak")

    r = ejecutar(instalado, ["--version"], env)
    comprobar(r.returncode == 0, "el binario INSTALADO arranca (--version)")


# --- 5. --check con configuración escrita ---------------------------------------


def prueba_check(exe: Path, env: dict[str, str], raiz: Path) -> None:
    print("\n[5] --check lee el config.env de esta plataforma")
    _, config_env, _, _ = rutas_esperadas(raiz)
    config_env.parent.mkdir(parents=True, exist_ok=True)
    config_env.write_text(
        f"ODOO_URL={ODOO_INALCANZABLE}\nODOO_DB=base\nODOO_USERNAME=ana@x.com\nODOO_PASSWORD=x\n",
        encoding="utf-8",
    )
    r = ejecutar(exe, ["--check"], env)
    err = limpiar(r.stderr)
    comprobar(r.returncode == 1, f"código 1 con Odoo inalcanzable (salió {r.returncode})")
    comprobar("127.0.0.1:9" in err, "el error menciona la URL leída del config.env (lo leyó de la ruta correcta)")
    comprobar("Traceback" not in err, "sin traza cruda")


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    exe = Path(sys.argv[1]).resolve()
    if not exe.exists():
        print(f"No existe {exe}")
        return 2
    print(f"Ejecutable: {exe} ({exe.stat().st_size // (1024 * 1024)} MB) en {sys.platform}")

    with tempfile.TemporaryDirectory(prefix="odoo-mcp-smoke-") as tmp:
        raiz = Path(tmp)
        env = entorno_aislado(raiz)
        prueba_arranque(exe, env)
        prueba_mcp(exe, env, [])
        prueba_mcp(exe, env, ["--mcp"])
        prueba_asistente_rechaza(exe, env, raiz)
        prueba_registrar(exe, env, raiz)
        prueba_check(exe, env, raiz)

    print()
    if fallos:
        print(f"{len(fallos)} FALLO(S):")
        for f in fallos:
            print(f"  - {f}")
        return 1
    print("Todo correcto.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
