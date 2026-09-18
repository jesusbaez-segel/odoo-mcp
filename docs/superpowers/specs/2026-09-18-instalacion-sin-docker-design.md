# Instalación sin Docker: ejecutable único y autoconfiguración de Claude

Fecha: 2026-09-18
Estado: aprobado

## Problema

Instalar el MCP exige hoy Docker Desktop (~700 MB, WSL2, reinicio) y cargar una
imagen de 53 MB que viaja dentro del propio repositorio (`odoo-mcp.tar.gz`). Para
alguien no técnico ese es el 90 % del esfuerzo y del riesgo de fallo. Además el
asistente solo registra el servidor en Claude Code; quien use Claude Desktop tiene
que editar un JSON a mano.

## Objetivo

Que recibir el MCP sea: descomprimir un ZIP, doble clic, responder tres preguntas.
Sin instalar Docker, ni Node, ni Python. Y que al terminar queden configurados
**Claude Code y Claude Desktop** a la vez.

## Decisiones

| Decisión | Elección | Motivo |
|---|---|---|
| Runtime | Python empaquetado con PyInstaller `--onefile` | El usuario final no instala nada. No hay que reescribir las ~2 150 líneas ya probadas. |
| Plataformas | Solo Windows | Es el parque real del equipo; PyInstaller solo compila para el SO anfitrión y así no hace falta CI. |
| Credenciales | Archivo único `%APPDATA%\odoo-mcp\config.env` | Una sola fuente para los dos clientes; el registro MCP queda sin `args` ni `env`; cambiar la contraseña no toca ningún JSON. |
| Ubicación | `%LOCALAPPDATA%\Programs\odoo-mcp\` | Ruta estable: si borra la carpeta de Descargas, Claude sigue encontrando el servidor. |

Contrapartida aceptada de `--onefile`: cada arranque descomprime a `%TEMP%`
(~0,5-1,5 s). Claude lanza el servidor una vez por sesión, así que no se percibe.

## Cambios en el código

`client.py`, `projects.py` y `generic.py` no cambian su lógica de negocio.

### `config.py`

- Se elimina `_running_in_docker()` y `adjust_url_for_docker()`. Fuera del
  contenedor, `http://localhost:8069` resuelve correctamente y la reescritura a
  `host.docker.internal` deja de tener sentido.
- Se añade carga de un archivo de configuración con este orden de búsqueda:
  1. Ruta explícita en `ODOO_MCP_CONFIG`.
  2. `%APPDATA%\odoo-mcp\config.env` (lo que escribe el asistente).
  3. `.env` en el directorio de trabajo (comodidad en desarrollo).
- Precedencia: **las variables de entorno del proceso ganan al archivo**. Un valor
  vacío en el entorno no pisa al archivo.
- Formato del archivo: `CLAVE=valor` por línea, `#` para comentarios, comillas
  externas opcionales. Se ignoran líneas mal formadas en vez de abortar.
- `load_settings(environ=...)` con un diccionario explícito **no** lee ningún
  archivo salvo que se le pase `config_path`, para que los tests sean herméticos.

### `client.py`

- Nuevo método público `uid()`: autentica (perezosamente, con la caché que ya
  existe) y devuelve el id de usuario. Lo necesita la verificación del instalador.

### `server.py`

- `main()` acepta argumentos:
  - `--check`: autentica contra Odoo, imprime `OK: conectado a <db> como <nombre>
    (<login>), Odoo <versión>` y sale con código 0; ante cualquier fallo imprime el
    error en stderr y sale con 1.
  - `--version`: imprime la versión y sale.
  - Sin argumentos: arranca el servidor MCP por stdio, como hasta ahora.
- La lógica de `--check` vive en una función `check_connection(client)` separada de
  `main()` para poder probarla con el doble de `tests/fakes.py`.

### Archivos que se eliminan

`Dockerfile`, `.dockerignore`, `odoo-mcp.tar.gz` (53 MB). `.mcp.json` pasa a
`uv run odoo-mcp` (este repositorio es el entorno de desarrollo, no el de reparto).

## Empaquetado

`build.ps1` sincroniza dependencias, pasa las pruebas, ejecuta PyInstaller y
verifica el binario con `odoo-mcp.exe --version` antes de darlo por bueno. Deja
`dist\odoo-mcp.exe` (19,6 MB medidos). `pyinstaller` se declara en el grupo `dev`
de `pyproject.toml`, nunca en las dependencias del servidor.

Dos detalles que el empaquetado obligó a resolver:

- El punto de entrada es `packaging/entry.py`, no `src/odoo_mcp/__main__.py`:
  PyInstaller ejecuta el script suelto, sin contexto de paquete, y sus imports
  relativos fallan.
- No se puede usar `--collect-all mcp`: al recorrer el paquete importa `mcp.cli`,
  que exige `typer` (un extra que no instalamos) y aborta el análisis. Se recogen
  `mcp.server` y `mcp.shared` y se excluye `mcp.cli`.
- La salida de la CLI se fuerza a UTF-8 (`--check`, `--version`, `--help`): la
  consola de Windows es cp850/cp1252 y rompía los acentos de los mensajes de
  error. El instalador fija además `[Console]::OutputEncoding` al capturarlos.

## El asistente de instalación (revisado: un único .exe)

Repartir cuatro archivos y explicar «abre instalar.bat, no el .exe» resultó poco
práctico. El mismo ejecutable es ahora el servidor **y** su instalador: se comparte
un solo archivo y se abre con doble clic, como cualquier instalador.

`server.py` elige el modo: si `sys.stdin.isatty()` hay una consola detrás (doble
clic) y arranca el asistente; si es una tubería, lo ha lanzado Claude y arranca el
servidor MCP. El registro en Claude añade `--mcp` para que el modo servidor sea
explícito, pero sin argumentos también funciona: los registros antiguos siguen
valiendo.

El asistente vive en `installer.py`, en Python, dentro del ejecutable. Desaparecen
`instalar.bat`, `configurar.ps1`, `desinstalar.bat`, `desinstalar.ps1` y `LEEME.txt`.
Si ya está instalado, el doble clic abre un menú: volver a registrar, reconfigurar,
comprobar la conexión, desinstalar. Cinco pasos:

1. **Instalar**: copia `odoo-mcp.exe` a `%LOCALAPPDATA%\Programs\odoo-mcp\`.
2. **Preguntar**: URL de Odoo → autodetección de la base de datos vía
   `/web/database/list` → email → contraseña oculta. (Lógica actual, se conserva.)
3. **Guardar**: `%APPDATA%\odoo-mcp\config.env` en UTF-8 sin BOM, con ACL
   restringida al usuario actual (hoy el `.env` se escribe con permisos heredados).
4. **Registrar en los dos clientes**:
   - *Claude Code*: `claude mcp add odoo -s user -- <ruta>\odoo-mcp.exe`. Si el CLI
     no está en el PATH, se escribe `mcpServers.odoo` directamente en
     `%USERPROFILE%\.claude.json`.
   - *Claude Desktop*: se **fusiona** `mcpServers.odoo` en su configuración, con
     copia `.bak` previa. Nunca se sobrescribe el archivo entero: otros servidores
     MCP del usuario sobreviven. Hay **dos ubicaciones posibles** y buscar solo la
     primera fue un fallo real, detectado al probarlo en una máquina de verdad:
     - clásica (instalador .exe): `%APPDATA%\Claude\`
     - Microsoft Store: `%LOCALAPPDATA%\Packages\Claude_<hash>\LocalCache\Roaming\Claude\`
       El `<hash>` cambia en cada máquina, así que se busca con comodín `Claude_*`.
   - Si un cliente no está instalado, se omite y se informa.
5. **Verificar**: ejecuta `odoo-mcp.exe --check`. Esto comprueba el ejecutable real
   y la configuración real, no solo que la contraseña sea válida. Al final resume
   qué clientes quedaron configurados y recuerda reiniciar Claude Desktop.

`desinstalar.bat` / `desinstalar.ps1`: quita el servidor de ambos clientes, borra
`%LOCALAPPDATA%\Programs\odoo-mcp` y pregunta si borrar también las credenciales.

## Ruido de stdin (añadido tras la primera prueba real)

El transporte stdio del SDK valida como JSON *cada* línea que lee, incluidas las
vacías. Una línea en blanco del cliente genera `Invalid JSON: EOF while parsing a
value` y una notificación de "Internal Server Error". La sesión sobrevive (el SDK
hace `continue`), pero el ruido asusta y ensucia los registros.

`stdio_filter.py` envuelve `sys.stdin.buffer` —lo único que el SDK lee— con un
filtro que descarta las líneas vacías y normaliza `

` a `
`. Colapsar saltos
consecutivos es seguro: en JSON-RPC los mensajes van delimitados por saltos y un
salto dentro de una cadena JSON siempre viaja escapado, nunca como byte 0x0A.

## Manejo de errores

- Sin `odoo-mcp.exe` junto al script: mensaje claro y salida.
- Odoo inalcanzable o credenciales inválidas: se detiene antes de escribir nada en
  la configuración de Claude.
- JSON de Claude Desktop corrupto: no se toca; se avisa y se imprime el bloque para
  pegar a mano.
- `--check` fallido tras registrar: se avisa de que el registro quedó hecho pero la
  conexión falla, con el error de Odoo textual.

## Pruebas

- `tests/test_config.py`: lectura del archivo, precedencia entorno > archivo,
  entorno vacío que no pisa, archivo ausente, comentarios y comillas, orden de
  búsqueda de rutas. Se eliminan los cuatro tests de `adjust_url_for_docker`.
- `tests/test_server.py`: `check_connection` en éxito y en fallo de autenticación,
  usando `FakeClient`.
- `tests/test_installer.py`: detección de las dos ubicaciones de Claude Desktop,
  fusión y borrado del JSON (conserva otros MCP, respeta uno corrupto, deja `.bak`,
  sin BOM), y el asistente completo con Odoo simulado, incluyendo que una credencial
  rechazada no deje nada escrito.
- `getpass` lee del dispositivo de consola, no de stdin: sin consola se cuelga para
  siempre. Se cae a `input()` cuando no hay tty, con prueba propia.

## Documentación

`README.md` y `LEEME.txt` sin Docker. Para compartir el MCP bastan tres archivos:
`odoo-mcp.exe`, `instalar.bat`, `configurar.ps1`. Requisito previo para quien lo
recibe: ninguno más allá de tener Claude.
