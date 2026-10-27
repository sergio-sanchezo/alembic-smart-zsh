# alembic-smart-zsh

Tab completion for Alembic in Zsh and Oh My Zsh. Works with any environment manager when you run `alembic` directly; `uv` integration is optional.

## Features

- Completes Alembic commands and options.
- Suggests project revision IDs, branch labels, and targets such as `head`, `base`, and `-1`.
- Reads migration metadata from `alembic.ini` and `pyproject.toml` without running Alembic, project code, or database queries. INI settings take precedence; TOML supplies missing settings, including in projects created with Alembic's `pyproject` template.
- Keeps branch targets such as `payments@head` available as a branch grows.
- Leaves your `alembic` command unchanged by default.

## Requirements

- Zsh with completion enabled.
- Python 3.11+ available as `python3` for project revision completion.
- Alembic installed in your preferred environment to run migrations.

Alembic is not required to load the plugin or generate completions. Without Python 3.11+, command, option, and built-in target completion still work; project revisions are unavailable. The plugin does not install Alembic or activate an environment for you.

## Installation

### Oh My Zsh

1. Clone the repository into your custom plugins directory:

   ```sh
   git clone https://github.com/sergio-sanchezo/alembic-smart-zsh.git \
     "${ZSH_CUSTOM:-$HOME/.oh-my-zsh/custom}/plugins/alembic-smart"
   ```

2. In `~/.zshrc`, add this after your existing `plugins=(...)` assignment and **before** `source "$ZSH/oh-my-zsh.sh"`:

   ```zsh
   plugins+=(alembic-smart)
   ```

3. Restart your shell with `exec zsh`.

### Without Oh My Zsh

Keep both plugin files together. After `autoload -Uz compinit; compinit` in `~/.zshrc`, source the plugin using its actual path:

```zsh
source "$HOME/path/to/alembic-smart-zsh/alembic-smart.plugin.zsh"
```

Restart your shell with `exec zsh`.

## Usage

Activate your Python environment as usual, then press Tab:

```text
alembic <TAB>                  # commands
alembic upgrade <TAB>          # head, heads, project revisions
alembic downgrade -<TAB>       # -1 and options
alembic revision --<TAB>       # --autogenerate, --message, and more
```

Revision discovery uses static metadata; dynamic revisions and custom layouts may not be detected. It does not check the database's current revision. Runner-prefixed commands such as `poetry run alembic` are not supported; use `alembic` directly or the optional uv adapter below.

Configuration discovery supports one explicit `-c` / `--config` file, combined with the other default configuration file. Repeated `-c` flags to select both files explicitly are not supported.

## Optional uv integration

For `uv run alembic <TAB>`, first generate native uv completion once:

```sh
mkdir -p "$HOME/.config/zsh"
uv generate-shell-completion zsh > "$HOME/.config/zsh/uv-completion.zsh"
```

Then add this to `~/.zshrc` **after** Oh My Zsh initialization (or after loading the standalone plugin):

```zsh
source "$HOME/.config/zsh/uv-completion.zsh"
alembic_smart_enable_uv
```

If native uv completion is already configured, just call `alembic_smart_enable_uv` after it. Restart with `exec zsh`. The adapter supports `uv run alembic` with no intervening options and delegates other commands to native uv completion.

To also make `alembic` run `uv run alembic`, add this **before** loading the plugin (before Oh My Zsh initialization):

```zsh
export ALEMBIC_SMART_WRAP_UV=1
```

This shortcut is disabled by default and is separate from completion support.

## Tests

```sh
python3 -m unittest discover -s tests -v
zsh -n alembic-smart.plugin.zsh
```

Interactive tests also require `pexpect`; tests with missing dependencies are skipped.

## License

[MIT](LICENSE).
