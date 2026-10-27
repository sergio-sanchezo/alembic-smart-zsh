# alembic-smart-zsh

Alembic completion for Zsh and Oh My Zsh, **independent of your environment manager**. Use it with venv, pip, Poetry, Conda, and other tools when invoking `alembic` directly. Optional integration with `uv run alembic` is also available.

- Completes Alembic commands and options (`upgrade`, `downgrade`, `revision`, `history`, and more).
- Suggests `head`, `heads`, `base`, `-1`, `+1`, and actual project revisions where applicable.
- Finds revision IDs and branch labels by parsing migration files such as `migrations/versions/*.py`, **without executing project code**.
- Reads `script_location` and `version_locations` from `alembic.ini` or `pyproject.toml`; supports `--config` and `--name` before the subcommand.
- Does not require `uv` or replace your `alembic` command by default.
- Provides an **optional shortcut, disabled by default**, from `alembic` to `uv run alembic`.
- Provides an **optional adapter** for `uv run alembic <TAB>` that delegates other commands to the existing native `uv` completer.

## Python environment compatibility

The plugin **only completes Alembic arguments**: it does not install Alembic or decide how to run migrations. For projects using `venv`, `conda`, `pip`, `pipx`, or Poetry, make `alembic` available in your shell as you normally would (for example, by activating your environment), then type `alembic <TAB>`.

The plugin does not guarantee completion for `poetry run alembic`, `pipenv run alembic`, or `pdm run alembic`. In this version, the only adapter for commands with a runner prefix is the explicitly enabled `uv` adapter. Reading project revisions requires `python3` running **Python 3.11 or later**, because the reader uses `tomllib`.

## Installation with Oh My Zsh

```sh
mkdir -p "${ZSH_CUSTOM:-$HOME/.oh-my-zsh/custom}/plugins/alembic-smart"
# Copy alembic-smart.plugin.zsh and revisions.py into that directory.
```

In `~/.zshrc`, append `alembic-smart` to your existing plugins, **before** the line that initializes Oh My Zsh (`source "$ZSH/oh-my-zsh.sh"`). Keep all the plugins you already use. You can add this line immediately after your existing `plugins=(...)` assignment:

```zsh
plugins+=(alembic-smart)
```

Alternatively, edit the existing array itself. For example, if it currently contains `git` and `z`, the complete updated assignment is:

```zsh
plugins=(git z alembic-smart)
```

Use one approach, not both. The `...` in the prose notation `plugins=(...)` means your existing plugin names; do not type a literal ellipsis into the array.

If you **also** want completion for the full `uv run alembic` command, configure the adapter **after** the Oh My Zsh initialization line.

If you have already configured official `uv` completion, simply add a call to `alembic_smart_enable_uv` immediately after that configuration.

Otherwise, generate the official completion file once:

```sh
mkdir -p "$HOME/.config/zsh"
uv generate-shell-completion zsh > "$HOME/.config/zsh/uv-completion.zsh"
```

Then add the following to `~/.zshrc`, after `source "$ZSH/oh-my-zsh.sh"`:

```zsh
source "$HOME/.config/zsh/uv-completion.zsh"
alembic_smart_enable_uv
```

This lets you review the `uv` completion code before loading it; no `eval` is needed.

> IMPORTANT: the `uv` integration supports `uv run alembic ...`, with no options between `uv`, `run`, and `alembic`. For other invocation patterns, use `alembic ...` directly.

Reload Zsh with `exec zsh`.

## Installation without Oh My Zsh

After `autoload -Uz compinit; compinit` in `~/.zshrc`, add the following, replacing the path with the plugin's actual location:

```zsh
source "$HOME/path/to/alembic-smart-zsh/alembic-smart.plugin.zsh"
```

To add the `uv run alembic` adapter, use the same configuration block shown above, after loading the plugin and initializing native `uv` completion.

## Examples

```sh
alembic <TAB>                # upgrade, downgrade, revision, ...
alembic upgr<TAB>            # upgrade
alembic upgrade <TAB>        # head, heads, actual revision IDs, ...
alembic downgrade -<TAB>     # -1 and options
alembic revision --<TAB>     # --autogenerate, --head, --message, ...
alembic revision --head <TAB> # actual revision IDs
uv run alembic upgrade <TAB> # the same, if the adapter is enabled
```

## Security design

1. **No `eval`**, sourcing of project files, or execution of project scripts is used to discover revisions.
2. When completing Alembic arguments, the plugin **never runs `alembic`, `uv`, `env.py`, or migrations**. It only invokes the `python3` found on `PATH` to read metadata statically; use a trusted interpreter. For other `uv` commands, the optional adapter delegates to your existing `uv` completer, whose behavior is outside this plugin's control.
3. `revisions.py` uses `ast.parse` and `ast.literal_eval` to parse data without executing the Python source it reads.
4. The metadata reader does not create or overwrite temporary files, open sockets, or read credential variables. It reads configuration and revision files, and honors the `ALEMBIC_CONFIG` environment variable when no explicit config path is supplied.
5. The reader limits each configuration or migration file to 256 KiB and examines at most 2,000 migration files per request, including invalid files and duplicate revision IDs.
6. Only if you set `ALEMBIC_SMART_WRAP_UV=1` before loading the plugin and `uv` is available will `alembic` run `uv run alembic` when you press Enter. By default, your command is left unchanged. The non-execution guarantee above applies to completion, not to running a command.

## Limitations

- The plugin does not query the database to determine the current revision, which would require running the migration environment. `current` is a symbolic completion candidate, not a confirmed database state.
- Static parsing supports literal assignments to `revision`, `down_revision`, and `branch_labels`. Dynamically computed revisions, `package:resources` locations, and complex custom layouts are not completed automatically.
- AST parsing can introduce a delay when you press Tab. For projects with more than 2,000 migration files, scanning is capped, so the revision list and calculated heads may be incomplete. There is no cache, avoiding cache invalidation and file writes.
- Without an explicit config path or `ALEMBIC_CONFIG`, if both `alembic.ini` and `pyproject.toml` exist in the current directory, only `alembic.ini` is read; their settings are not merged. `--name` selects an INI section; TOML configuration always uses `[tool.alembic]`. The reader does not recurse into subdirectories of version directories.
- The `uv` adapter requires native `uv` completion to be loaded **before** calling `alembic_smart_enable_uv`.
- Interactive tests cover a clean Zsh session; they do not validate every combination of Oh My Zsh plugins, themes, and versions.

## Enabling the optional uv shortcut

By default, the plugin **does not change** what `alembic` runs. If you explicitly want `alembic` to invoke `uv run alembic`, add this **before** loading the plugin:

```zsh
export ALEMBIC_SMART_WRAP_UV=1
```

Completion for `uv run alembic` is independent of this shortcut and is enabled with `alembic_smart_enable_uv`, as described above.

## Running tests

From the plugin directory, run:

```sh
python3 -m unittest discover -s tests -v
zsh -n alembic-smart.plugin.zsh
```

The reader tests require only Python 3.11+. Integration tests require `zsh`; tests that press Tab in a real pseudoterminal also require the optional Python package `pexpect`. If a dependency is missing, the affected tests are marked as skipped, not passed. The tests cover commands, options, project revisions, `-1`, and the `uv` adapter with a simulated native completer, without running migrations.

## Uninstalling

Remove `alembic-smart` from your plugin array (or remove the `plugins+=(alembic-smart)` line if you used that approach), remove the `alembic_smart_enable_uv` call and any plugin-specific shortcut setting, delete the plugin directory, and run `exec zsh`. If you installed without Oh My Zsh, remove the line that sources `alembic-smart.plugin.zsh` as well. Keep the native `uv` completion configuration if you still use it.

MIT license (see LICENSE).
