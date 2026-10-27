# alembic-smart-zsh

Autocompletado de Alembic para Zsh y Oh My Zsh, **independiente del gestor de entornos**. Se puede usar con venv, pip, Poetry, Conda y otros gestores al invocar `alembic` directamente. Existe una integración opcional con `uv run alembic`.

- Comandos y opciones de Alembic (`upgrade`, `downgrade`, `revision`, `history`, etc.).
- `head`, `heads`, `base`, `-1`, `+1` y revisiones reales del proyecto.
- Busca IDs y etiquetas de ramas analizando archivos `migrations/versions/*.py` **sin ejecutar código del proyecto**.
- Lee `script_location` de `alembic.ini` o `pyproject.toml`; permite `--config` y `--name` antes del subcomando.
- No requiere `uv` ni sustituye el comando `alembic` del usuario.
- Atajo **opcional y desactivado por defecto** `alembic` => `uv run alembic`.
- Adaptador **opcional** para `uv run alembic <TAB>` sin sustituir el autocompletado nativo de `uv` para otros comandos.

## Compatibilidad con entornos Python

El plugin **solo completa los argumentos** de Alembic: no instala Alembic ni decide cómo ejecutar las migraciones. Para proyectos con `venv`, `conda`, `pip`, `pipx` o Poetry, activa el entorno que uses para ejecutar `alembic` y escribe `alembic <TAB>`.

El plugin no garantiza completar `poetry run alembic`, `pipenv run alembic` o `pdm run alembic`: en esta versión el único adaptador de comandos prefijados es el de `uv`, que se activa explícitamente. La lectura de revisiones utiliza `python3` con Python **3.11 o superior** para `tomllib`.

## Instalación con Oh My Zsh

```sh
mkdir -p "${ZSH_CUSTOM:-$HOME/.oh-my-zsh/custom}/plugins/alembic-smart"
# Copia alembic-smart.plugin.zsh y revisions.py al directorio anterior.
```

En `~/.zshrc`, agrega `alembic-smart` a tu arreglo existente de plugins:

```zsh
plugins=(git alembic-smart)
```

Si **también** quieres sugerencias para el comando completo `uv run alembic`, configura el adaptador **después** del bloque que inicializa Oh My Zsh (`source $ZSH/oh-my-zsh.sh`).

Si ya tienes configurado el autocompletado oficial de `uv`, solamente añade la llamada a `alembic_smart_enable_uv` justo después de esa configuración.

Si todavía no lo tienes, genera una sola vez su archivo oficial:

```sh
mkdir -p "$HOME/.config/zsh"
uv generate-shell-completion zsh > "$HOME/.config/zsh/uv-completion.zsh"
```

Y después de `source $ZSH/oh-my-zsh.sh` añade en tu `~/.zshrc`:

```zsh
source "$HOME/.config/zsh/uv-completion.zsh"
alembic_smart_enable_uv
```

Así puedes revisar el código de autocompletado de `uv` antes de cargarlo; no necesitas `eval`.

> IMPORTANTE: la integración de `uv` funciona con `uv run alembic ...` (sin opciones entre `uv`, `run` y `alembic`). Para otras variantes usa `alembic ...` directamente.

Recarga Zsh con `exec zsh`.

## Instalación sin Oh My Zsh

Después de `autoload -Uz compinit; compinit` en `~/.zshrc`, añade:

```zsh
source "$HOME/ruta/al/alembic-smart-zsh/alembic-smart.plugin.zsh"
```

Para agregar el adaptador `uv run alembic`, usa el mismo bloque anterior, después de cargar el plugin y activar el autocompletado nativo de `uv`.

## Ejemplos

```sh
alembic <TAB>                  # upgrade, downgrade, revision, ...
alembic upgr<TAB>              # upgrade
alembic upgrade <TAB>         # head, heads, IDs reales, ...
alembic downgrade -<TAB>      # -1 y opciones
alembic revision --<TAB>      # --autogenerate, --head, --message, ...
alembic revision --head <TAB> # IDs reales
uv run alembic upgrade <TAB>  # lo mismo si activaste el adaptador
```

## Decisiones de seguridad

1. **No hay `eval`**, ni `source` de archivos del proyecto, ni `exec` de scripts.
2. Al pulsar Tab, el plugin **nunca ejecuta `alembic`, `uv`, `env.py` ni migraciones**. Solo lanza el `python3` disponible en `PATH` para lectura estática de metadatos; utiliza un intérprete de confianza.
3. `revisions.py` usa `ast.parse` y `ast.literal_eval`: son analizadores de datos y no ejecutan el código Python leído.
4. Nunca crea ni sobrescribe archivos temporales, ni abre sockets, ni lee variables de credenciales. Solo abre archivos de configuración y revisiones.
5. El lector limita cada archivo de configuración y migración a 256 KiB y examina hasta 2.000 archivos de migración por solicitud (también cuentan los inválidos y los IDs duplicados).
6. Solo si activas `ALEMBIC_SMART_WRAP_UV=1` antes de cargar el plugin y `uv` está disponible, `alembic` ejecuta `uv run alembic` al presionar Enter. Por defecto conserva el comando del usuario. La garantía de no ejecución anterior aplica al autocompletado.

## Limitaciones

- No consulta la BD para averiguar la revisión actual (esto exigiría ejecutar el entorno de migraciones). `current` es un candidato simbólico, no el estado confirmado de la base de datos.
- La lectura estática soporta asignaciones literales de `revision`, `down_revision` y `branch_labels`. Revisiones calculadas dinámicamente, ubicaciones declaradas como `package:resources` y diseños personalizados complejos no se completan automáticamente.
- El análisis AST puede añadir un retraso al pulsar Tab. En proyectos con más de 2.000 archivos se limita la exploración; la lista de revisiones y el cálculo de heads pueden quedar incompletos. Se evita mantener una caché para no manejar invalidaciones ni escribir archivos.
- Si existen `alembic.ini` y `pyproject.toml`, se lee solo el primero: no se combinan sus opciones. `--name` selecciona una sección INI; en TOML se usa `[tool.alembic]`. El lector no recorre subdirectorios de las carpetas de versiones.
- El adaptador de `uv` depende de cargar primero el completado nativo de `uv` y **luego** ejecutar `alembic_smart_enable_uv`.
- Las pruebas interactivas cubren Zsh limpio; no equivalen a validar todas las combinaciones de plugins, temas y versiones de Oh My Zsh.

## Activar el atajo opcional con uv

De manera predeterminada, el plugin **no cambia** qué ejecuta `alembic`. Si expresamente quieres que `alembic` invoque `uv run alembic`, añade **antes** de cargar el plugin:

```zsh
export ALEMBIC_SMART_WRAP_UV=1
```

La integración para completar `uv run alembic` es independiente de este atajo y se activa con `alembic_smart_enable_uv`, como se explica arriba.

## Ejecutar pruebas

```sh
python3 -m unittest discover -s tests -v
zsh -n alembic-smart.plugin.zsh
```

Las pruebas del lector solo requieren Python 3.11+. Las pruebas de integración necesitan `zsh`; las de Tab real en un pseudoterminal también necesitan el paquete Python opcional `pexpect`. Si falta alguna dependencia, esas pruebas se marcan como omitidas (no como aprobadas). Se comprueban comandos, opciones, revisiones del proyecto, `-1` y el adaptador `uv` con un completador nativo simulado, sin ejecutar migraciones.

## Desinstalar

Quita `alembic-smart` de `plugins=(...)`, quita el bloque `alembic_smart_enable_uv`, borra su carpeta y ejecuta `exec zsh`.

Licencia MIT (ver LICENSE).
