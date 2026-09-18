"""Asistente de instalación: lo que ocurre al abrir odoo-mcp.exe con doble clic.

El mismo ejecutable es el servidor MCP y su propio instalador, así que se reparte
un único archivo. server.py decide el modo según cómo se haya arrancado.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import urllib.request
from getpass import getpass
from pathlib import Path

from .client import OdooClient, OdooError
from .config import Settings, user_config_path

NOMBRE_EXE = "odoo-mcp.exe"
CARPETA_INSTALACION = "Programs/odoo-mcp"
ARG_SERVIDOR = "--mcp"

VERDE, AMARILLO, ROJO, CIAN, GRIS, FIN = (
    "\033[92m",
    "\033[93m",
    "\033[91m",
    "\033[96m",
    "\033[90m",
    "\033[0m",
)


class InstallerError(Exception):
    """Error que corta el asistente con un mensaje legible."""


# --- Consola -----------------------------------------------------------------


def preparar_consola() -> None:
    """La consola de Windows es cp850/cp1252 y rompe los acentos; y sin modo VT
    los colores saldrían como basura."""
    if os.name != "nt":
        return
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        kernel32.SetConsoleOutputCP(65001)
        kernel32.SetConsoleCP(65001)
        # ENABLE_VIRTUAL_TERMINAL_PROCESSING sobre el handle de salida (-11)
        handle = kernel32.GetStdHandle(-11)
        modo = ctypes.c_uint32()
        if kernel32.GetConsoleMode(handle, ctypes.byref(modo)):
            kernel32.SetConsoleMode(handle, modo.value | 0x0004)
    except Exception:
        pass
    for flujo in (sys.stdout, sys.stderr):
        try:
            flujo.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            pass


def titulo(texto: str) -> None:
    print()
    print(f"{VERDE}  {texto}{FIN}")
    print(f"  {'-' * len(texto)}")


def paso(texto: str) -> None:
    print(f"{CIAN}{texto}{FIN}")


def aviso(texto: str) -> None:
    print(f"{AMARILLO}{texto}{FIN}")


def error(texto: str) -> None:
    print(f"{ROJO}{texto}{FIN}")


def pausa(texto: str = "Pulsa Enter para salir") -> None:
    try:
        input(f"\n{GRIS}{texto}{FIN}")
    except (EOFError, KeyboardInterrupt):
        pass


# --- Rutas --------------------------------------------------------------------


def destino_ejecutable() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    raiz = Path(base) if base else Path.home() / ".local"
    return raiz / CARPETA_INSTALACION / NOMBRE_EXE


def config_claude_code() -> Path:
    return Path.home() / ".claude.json"


def configs_claude_desktop() -> list[Path]:
    """Rutas de configuración de Claude Desktop presentes en la máquina.

    Hay dos instalaciones posibles y la gente tiene una u otra:
    - la clásica (instalador .exe), en %APPDATA%\\Claude
    - la de la Microsoft Store, con el AppData virtualizado dentro del paquete:
      %LOCALAPPDATA%\\Packages\\Claude_<hash>\\LocalCache\\Roaming\\Claude
      El <hash> cambia según el editor, por eso se busca con comodín.
    """
    carpetas: list[Path] = []
    appdata = os.environ.get("APPDATA")
    if appdata:
        carpetas.append(Path(appdata) / "Claude")
    local = os.environ.get("LOCALAPPDATA")
    if local:
        paquetes = Path(local) / "Packages"
        if paquetes.is_dir():
            try:
                carpetas.extend(sorted(paquetes.glob("Claude_*/LocalCache/Roaming/Claude")))
            except OSError:
                pass
    return [c / "claude_desktop_config.json" for c in carpetas if c.is_dir()]


# --- Entrada de datos ---------------------------------------------------------


def normalizar_url(bruta: str) -> str:
    url = bruta.strip().rstrip("/")
    if not url:
        raise InstallerError("No escribiste ninguna URL.")
    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"
    return url


def parsear_bases(payload: bytes) -> list[str]:
    try:
        datos = json.loads(payload)
    except (ValueError, TypeError):
        return []
    resultado = datos.get("result") if isinstance(datos, dict) else None
    if not isinstance(resultado, list):
        return []
    return [str(x) for x in resultado if isinstance(x, (str, int))]


def detectar_bases(url: str, timeout: float = 10.0) -> list[str]:
    """Pregunta a Odoo qué bases de datos tiene. Si no contesta, devuelve []."""
    peticion = urllib.request.Request(
        f"{url}/web/database/list",
        data=json.dumps({"jsonrpc": "2.0", "method": "call", "params": {}}).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(peticion, timeout=timeout) as respuesta:
            return parsear_bases(respuesta.read())
    except Exception:
        return []


def preguntar(texto: str, obligatorio: str | None = None) -> str:
    try:
        valor = input(f"      {texto}: ").strip()
    except (EOFError, KeyboardInterrupt):
        raise InstallerError("Instalación cancelada.")
    if not valor and obligatorio:
        raise InstallerError(obligatorio)
    return valor


def pedir_clave(texto: str) -> str:
    """getpass lee del dispositivo de consola, no de stdin: si no hay consola
    (ejecucion automatizada, entrada redirigida) se queda colgado para siempre."""
    try:
        if sys.stdin is not None and sys.stdin.isatty():
            return getpass(f"      {texto}: ").strip()
    except (OSError, ValueError, AttributeError):
        pass
    try:
        return input(f"      {texto}: ").strip()
    except (EOFError, KeyboardInterrupt):
        raise InstallerError("Instalación cancelada.")


def pedir_datos() -> tuple[str, str, str, str]:
    paso("[2/5] Datos de tu Odoo")
    url = normalizar_url(preguntar("URL de tu Odoo (ej. https://miempresa.odoo.com)"))

    bases = detectar_bases(url)
    if len(bases) == 1:
        db = bases[0]
        print(f"      Base de datos detectada: {db}")
    elif len(bases) > 1:
        print(f"      Bases disponibles: {', '.join(bases)}")
        db = preguntar("Cuál usar", "Hace falta el nombre de la base de datos.")
    else:
        db = preguntar("Nombre de la base de datos", "Hace falta el nombre de la base de datos.")

    usuario = preguntar("Email con el que entras a Odoo", "Hace falta tu email de Odoo.")
    clave = pedir_clave("Contraseña (o API key; no se muestra al escribir)")
    if not clave:
        raise InstallerError("Hace falta la contraseña o la API key.")
    return url, db, usuario, clave


def verificar(url: str, db: str, usuario: str, clave: str) -> str:
    """Autentica contra Odoo antes de guardar nada. Devuelve a quién reconoció."""
    cliente = OdooClient(Settings(url=url, db=db, username=usuario, api_key=clave, timeout=30.0))
    uid = cliente.uid()
    datos = cliente.execute("res.users", "read", [[uid], ["name"]])
    return datos[0].get("name", usuario) if datos else usuario


# --- Escritura ----------------------------------------------------------------


def escribir_config(ruta: Path, url: str, db: str, usuario: str, clave: str) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    contenido = "\r\n".join(
        [
            "# Datos de conexión a Odoo. Generado por el asistente de instalación.",
            f"ODOO_URL={url}",
            f"ODOO_DB={db}",
            f"ODOO_USERNAME={usuario}",
            f"ODOO_PASSWORD={clave}",
            "",
        ]
    )
    ruta.write_text(contenido, encoding="utf-8")  # sin BOM
    restringir_permisos(ruta)


def restringir_permisos(ruta: Path) -> bool:
    """Solo el usuario actual puede leer el archivo: contiene la contraseña."""
    if os.name != "nt":
        try:
            ruta.chmod(0o600)
            return True
        except OSError:
            return False
    usuario = os.environ.get("USERNAME", "")
    dominio = os.environ.get("USERDOMAIN", "")
    cuenta = f"{dominio}\\{usuario}" if dominio and usuario else usuario
    if not cuenta:
        return False
    try:
        resultado = subprocess.run(
            ["icacls", str(ruta), "/inheritance:r", "/grant:r", f"{cuenta}:F"],
            capture_output=True,
            timeout=20,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return resultado.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def fusionar_mcp(ruta_json: Path, ejecutable: Path) -> str:
    """Añade el servidor 'odoo' conservando todo lo demás del archivo.

    Devuelve 'ok', 'json-corrupto' o el texto del error. Nunca reescribe el
    archivo entero: quien tenga otros MCP configurados los conserva.
    """
    try:
        configuracion: dict = {}
        if ruta_json.exists():
            texto = ruta_json.read_text(encoding="utf-8-sig")
            if texto.strip():
                try:
                    configuracion = json.loads(texto)
                except ValueError:
                    return "json-corrupto"
                if not isinstance(configuracion, dict):
                    return "json-corrupto"
            shutil.copy2(ruta_json, ruta_json.with_suffix(ruta_json.suffix + ".bak"))
        servidores = configuracion.get("mcpServers")
        if not isinstance(servidores, dict):
            servidores = {}
        servidores["odoo"] = {
            "type": "stdio",
            "command": str(ejecutable),
            "args": [ARG_SERVIDOR],
            "env": {},
        }
        configuracion["mcpServers"] = servidores
        ruta_json.parent.mkdir(parents=True, exist_ok=True)
        ruta_json.write_text(
            json.dumps(configuracion, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        return "ok"
    except OSError as exc:
        return str(exc)


def quitar_mcp(ruta_json: Path) -> bool:
    """Quita el servidor 'odoo'; True si estaba y se ha quitado."""
    try:
        if not ruta_json.exists():
            return False
        texto = ruta_json.read_text(encoding="utf-8-sig")
        if not texto.strip():
            return False
        configuracion = json.loads(texto)
        servidores = configuracion.get("mcpServers")
        if not isinstance(servidores, dict) or "odoo" not in servidores:
            return False
        shutil.copy2(ruta_json, ruta_json.with_suffix(ruta_json.suffix + ".bak"))
        del servidores["odoo"]
        ruta_json.write_text(
            json.dumps(configuracion, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        return True
    except (OSError, ValueError, TypeError):
        return False


def instalar_ejecutable() -> Path:
    """Copia el .exe a una carpeta fija: si borran la carpeta de Descargas, el
    servidor registrado en Claude tiene que seguir existiendo."""
    destino = destino_ejecutable()
    if not getattr(sys, "frozen", False):
        raise InstallerError(
            "El asistente solo funciona desde odoo-mcp.exe. En desarrollo usa "
            "'uv run odoo-mcp --check'."
        )
    origen = Path(sys.executable).resolve()
    if origen == destino.resolve():
        return destino  # ya se está ejecutando el instalado: reconfiguración
    destino.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copy2(origen, destino)
    except (OSError, shutil.Error) as exc:
        if destino.exists():
            aviso(f"      No pude actualizar el ejecutable ({exc}).")
            aviso("      Sigo con el que ya estaba instalado; cierra Claude para actualizarlo.")
            return destino
        raise InstallerError(f"No pude copiar el servidor a {destino.parent}: {exc}")
    return destino


# --- Registro en los clientes -------------------------------------------------


def registrar(ejecutable: Path) -> list[str]:
    """Registra el servidor en todos los Claude que haya. Devuelve cuáles."""
    configurados: list[str] = []

    ruta_code = config_claude_code()
    if ruta_code.exists() or shutil.which("claude"):
        resultado = fusionar_mcp(ruta_code, ejecutable)
        if resultado == "ok":
            print(f"      Claude Code: {VERDE}configurado{FIN}")
            configurados.append("Claude Code")
        elif resultado == "json-corrupto":
            aviso("      Claude Code: su configuración tiene un error de formato; no la he tocado.")
        else:
            aviso(f"      Claude Code: no pude configurarlo ({resultado})")
    else:
        print(f"      Claude Code: {GRIS}no está instalado, lo omito{FIN}")

    rutas_desktop = configs_claude_desktop()
    if not rutas_desktop:
        print(f"      Claude Desktop: {GRIS}no está instalado, lo omito{FIN}")
    for ruta in rutas_desktop:
        resultado = fusionar_mcp(ruta, ejecutable)
        if resultado == "ok":
            print(f"      Claude Desktop: {VERDE}configurado{FIN}")
            if "Claude Desktop" not in configurados:
                configurados.append("Claude Desktop")
        elif resultado == "json-corrupto":
            aviso("      Claude Desktop: su configuración tiene un error de formato.")
            aviso(f"      No la he tocado. Añade a mano en {ruta}:")
            aviso(f'        "odoo": {{ "command": "{ejecutable}", "args": ["{ARG_SERVIDOR}"] }}')
        else:
            aviso(f"      Claude Desktop: no pude configurarlo ({resultado})")
    return configurados


# --- Asistente ----------------------------------------------------------------


def asistente() -> int:
    titulo("Instalación del MCP de Odoo para Claude")

    paso("[1/5] Instalando el servidor...")
    ejecutable = instalar_ejecutable()
    print(f"      Instalado en {ejecutable}")

    url, db, usuario, clave = pedir_datos()

    paso(f"[3/5] Comprobando el acceso a {url} ...")
    try:
        nombre = verificar(url, db, usuario, clave)
    except OdooError as exc:
        raise InstallerError(
            f"{exc}\n      Revisa el email, la contraseña y que la base '{db}' sea la correcta."
        )
    print(f"      {VERDE}Acceso verificado: eres {nombre}.{FIN}")

    paso("[4/5] Guardando tu configuración...")
    ruta_config = user_config_path()
    escribir_config(ruta_config, url, db, usuario, clave)
    print(f"      Guardada en {ruta_config} (solo en esta máquina)")

    paso("[5/5] Configurando Claude...")
    configurados = registrar(ejecutable)

    print()
    if configurados:
        print(f"{VERDE}  Listo. Configurado en: {' y '.join(configurados)}.{FIN}")
        if "Claude Desktop" in configurados:
            print(f"{VERDE}  Cierra Claude Desktop del todo (icono junto al reloj) y ábrelo.{FIN}")
        if "Claude Code" in configurados:
            print(f"{VERDE}  Si tenías Claude Code abierto, ciérralo y vuelve a abrirlo.{FIN}")
        print()
        print(f'{VERDE}  Luego pídele:  "muéstrame mis proyectos de Odoo"{FIN}')
    else:
        aviso("  No encontré ningún Claude instalado en esta máquina.")
        aviso("  Instala Claude (claude.com) y vuelve a abrir este archivo.")
    return 0


def desinstalar() -> int:
    titulo("Desinstalar el MCP de Odoo")
    print()

    if quitar_mcp(config_claude_code()):
        print("  Quitado de Claude Code")
    else:
        print(f"  Claude Code: {GRIS}no estaba configurado{FIN}")

    quitado = [r for r in configs_claude_desktop() if quitar_mcp(r)]
    if quitado:
        print("  Quitado de Claude Desktop")
    else:
        print(f"  Claude Desktop: {GRIS}no estaba configurado{FIN}")

    destino = destino_ejecutable()
    if destino.exists() and Path(sys.executable).resolve() != destino.resolve():
        try:
            shutil.rmtree(destino.parent)
            print(f"  Borrado {destino.parent}")
        except OSError:
            aviso(f"  No pude borrar {destino.parent} (cierra Claude y reintenta)")
    elif destino.exists():
        aviso(f"  {destino.parent} se borra al cerrar este programa: bórralo a mano si queda.")

    ruta_config = user_config_path()
    if ruta_config.exists():
        print()
        respuesta = preguntar("¿Borrar también tus datos de conexión a Odoo? (s/N)")
        if respuesta[:1].lower() in ("s", "y"):
            try:
                shutil.rmtree(ruta_config.parent)
                print("  Datos borrados")
            except OSError:
                aviso(f"  No pude borrar {ruta_config.parent}")
        else:
            print(f"  Datos conservados en {ruta_config}")

    print()
    print(f"{VERDE}  Listo. Reinicia Claude para que deje de verlo.{FIN}")
    return 0


def reregistrar() -> int:
    """Vuelve a registrar el servidor sin tocar los datos de Odoo.

    Es el caso de quien instala Claude Desktop después, o de quien lo tenía y no
    se detectó: no hay motivo para hacerle teclear la contraseña otra vez.
    """
    titulo("Volver a registrar el MCP de Odoo en Claude")
    paso("[1/2] Comprobando la instalación...")
    ejecutable = instalar_ejecutable()
    print(f"      Servidor en {ejecutable}")

    paso("[2/2] Configurando Claude...")
    configurados = registrar(ejecutable)

    print()
    if configurados:
        print(f"{VERDE}  Listo. Configurado en: {' y '.join(configurados)}.{FIN}")
        print(f"{VERDE}  Cierra Claude del todo y vuelve a abrirlo.{FIN}")
    else:
        aviso("  No encontré ningún Claude instalado en esta máquina.")
    return 0


def menu() -> int:
    """Si ya está instalado, no tiene sentido repetir el asistente a ciegas."""
    titulo("MCP de Odoo para Claude")
    print("  Ya está instalado en esta máquina.")
    print()
    print("    1) Volver a registrarlo en Claude (sin cambiar mis datos)")
    print("    2) Cambiar mis datos de Odoo (reconfigurar)")
    print("    3) Comprobar la conexión")
    print("    4) Desinstalar")
    print("    5) Salir")
    print()
    opcion = preguntar("Qué quieres hacer (1-5)")
    if opcion == "1":
        return reregistrar()
    if opcion == "2":
        return asistente()
    if opcion == "3":
        from .server import comprobar_conexion_cli

        return comprobar_conexion_cli()
    if opcion == "4":
        return desinstalar()
    return 0


def ejecutar(accion: str = "auto") -> int:
    """Punto de entrada del modo interactivo. Siempre deja la ventana abierta:
    con doble clic, una consola que se cierra sola no deja leer nada."""
    preparar_consola()
    try:
        if accion == "desinstalar":
            codigo = desinstalar()
        elif accion == "registrar":
            codigo = reregistrar()
        elif accion == "menu":
            codigo = menu()
        elif accion == "instalar":
            codigo = asistente()
        elif destino_ejecutable().exists() and user_config_path().exists():
            codigo = menu()
        else:
            codigo = asistente()
    except InstallerError as exc:
        print()
        error(f"  {exc}")
        pausa()
        return 1
    except OdooError as exc:
        print()
        error(f"  {exc}")
        pausa()
        return 1
    except Exception as exc:  # una traza cruda no ayuda a quien instala
        print()
        error(f"  Error inesperado: {exc}")
        pausa()
        return 1
    pausa("Pulsa Enter para terminar")
    return codigo
