#!/usr/bin/env python3
"""Read Alembic revision metadata without importing project code or Alembic.

Only Python standard-library parsers are used. No eval/exec/subprocesses/network.
"""

import argparse
import ast
import configparser
from dataclasses import dataclass
import os
from pathlib import Path
import re
import tomllib

MAX_FILE_BYTES = 256 * 1024
MAX_MIGRATIONS = 2000
VALID_TOKEN = re.compile(r"[a-zA-Z0-9_][a-zA-Z0-9_.-]{0,127}\Z")


@dataclass(frozen=True)
class Revision:
    revision: str
    parents: tuple[str, ...]
    branch_labels: tuple[str, ...]
    description: str


def safe_token(value: object) -> str | None:
    return value if isinstance(value, str) and VALID_TOKEN.fullmatch(value) else None


def literal_assignment(stmt: ast.stmt):
    if isinstance(stmt, ast.Assign):
        names = [t.id for t in stmt.targets if isinstance(t, ast.Name)]
        return names, stmt.value
    if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
        return [stmt.target.id], stmt.value
    return [], None


def read_bounded(path: Path, encoding: str) -> str:
    """Bound actual reads too: a file can grow after stat()."""
    if not path.is_file() or path.stat().st_size > MAX_FILE_BYTES:
        raise ValueError("file exceeds metadata size limit")
    with path.open("rb") as stream:
        data = stream.read(MAX_FILE_BYTES + 1)
    if len(data) > MAX_FILE_BYTES:
        raise ValueError("file exceeds metadata size limit")
    return data.decode(encoding)


def read_revision(path: Path) -> Revision | None:
    try:
        tree = ast.parse(read_bounded(path, "utf-8-sig"), filename=str(path))
        values: dict[str, object] = {}
        for node in tree.body:
            keys, expr = literal_assignment(node)
            if expr is not None:
                for key in keys:
                    if key in {"revision", "down_revision", "branch_labels"}:
                        try:
                            values[key] = ast.literal_eval(expr)
                        except (
                            ValueError,
                            TypeError,
                            SyntaxError,
                            RecursionError,
                            MemoryError,
                        ):
                            values.pop(key, None)
        rev = safe_token(values.get("revision"))
        if rev is None:
            return None

        def tokens(value: object) -> tuple[str, ...]:
            if isinstance(value, str):
                return (token,) if (token := safe_token(value)) else ()
            if isinstance(value, (tuple, list)):
                return tuple(token for v in value if (token := safe_token(v)))
            return ()

        slug = path.stem
        if slug.startswith(rev + "_"):
            slug = slug[len(rev) + 1 :]
        slug = re.sub(r"[^\w .-]+", " ", slug, flags=re.UNICODE).strip()[:56]
        return Revision(
            rev,
            tokens(values.get("down_revision")),
            tokens(values.get("branch_labels")),
            slug,
        )
    except (
        OSError,
        UnicodeError,
        SyntaxError,
        ValueError,
        RecursionError,
        MemoryError,
    ):
        return None


def read_config(config_path: Path, section: str) -> dict[str, object]:
    if not config_path.is_file():
        return {}
    try:
        if config_path.suffix == ".toml":
            data = tomllib.loads(read_bounded(config_path, "utf-8"))
            tool = data.get("tool", {})
            if not isinstance(tool, dict):
                return {}
            opts = tool.get("alembic", {})
            if not isinstance(opts, dict):
                return {}
        else:
            ini = configparser.ConfigParser(interpolation=None, strict=False)
            ini.read_string(read_bounded(config_path, "utf-8"))
            opts = ini[section] if ini.has_section(section) else {}
        here = str(config_path.parent.resolve())
        values = {}
        for key in (
            "script_location",
            "version_locations",
            "path_separator",
            "version_path_separator",
        ):
            if key not in opts:
                continue
            value = opts[key]
            if isinstance(value, str):
                value = value.replace("%(here)s", here)
            elif isinstance(value, list):
                value = [
                    v.replace("%(here)s", here) if isinstance(v, str) else v
                    for v in value
                ]
            values[key] = value
        return values
    except (
        OSError,
        UnicodeError,
        ValueError,
        configparser.Error,
        TypeError,
        RecursionError,
        MemoryError,
    ):
        return {}


def config_options(
    cwd: Path, config_arg: str | None, section: str
) -> dict[str, object]:
    ini_path = cwd / "alembic.ini"
    toml_path = cwd / "pyproject.toml"
    for config_name in (os.environ.get("ALEMBIC_CONFIG"), config_arg):
        if not config_name:
            continue
        config_path = cwd / config_name
        if config_path.suffix == ".toml":
            toml_path = config_path
        else:
            ini_path = config_path
    if config_arg and not (cwd / config_arg).is_file():
        return {}
    toml_options = read_config(toml_path, section)
    ini_options = read_config(ini_path, section)
    if ini_options.get("version_locations"):
        toml_options.pop("path_separator", None)
        toml_options.pop("version_path_separator", None)
    else:
        ini_options.pop("version_locations", None)
    return toml_options | ini_options


def resolve_location(value: str, cwd: Path) -> Path | None:
    value = value.strip()
    if not value or ":" in value and value.split(":", 1)[0].isidentifier():
        return None
    return cwd / value


def locations_for(cwd: Path, config_arg: str | None, section: str) -> list[Path]:
    cwd = cwd.resolve()
    opts = config_options(cwd, config_arg, section)
    script_location = opts.get("script_location", "")
    version_locations = opts.get("version_locations")
    if not isinstance(script_location, str):
        return []

    if version_locations:
        if isinstance(version_locations, list):
            entries = [s for s in version_locations if isinstance(s, str)]
        elif isinstance(version_locations, str):
            separator = opts.get("path_separator", opts.get("version_path_separator"))
            separators = {
                "os": os.pathsep,
                "newline": "\n",
                "space": " ",
                ":": ":",
                ";": ";",
            }
            if separator is None:
                entries = re.split(r"[\s,]+", version_locations)
            elif isinstance(separator, str) and separator in separators:
                entries = version_locations.split(separators[separator])
            else:
                return []
        else:
            return []
    else:
        script_path = resolve_location(script_location, cwd)
        return (
            [script_path / "versions"]
            if script_path and (script_path / "versions").is_dir()
            else []
        )

    return [
        path
        for entry in entries
        if (path := resolve_location(entry, cwd)) is not None and path.is_dir()
    ]


def results(cwd: Path, config: str | None, section: str, mode: str) -> list[str]:
    records: dict[str, Revision] = {}
    scanned = 0
    for directory in locations_for(cwd, config, section):
        if scanned >= MAX_MIGRATIONS:
            break
        try:
            paths = directory.glob("*.py")
            for path in paths:
                if scanned >= MAX_MIGRATIONS:
                    break
                scanned += 1
                record = read_revision(path)
                if record:
                    records[record.revision] = record
        except OSError:
            continue

    referenced = {parent for record in records.values() for parent in record.parents}
    heads = set(records) - referenced
    output: set[str] = set()
    for record in records.values():
        if mode == "heads" and record.revision not in heads:
            continue
        output.add(f"{record.revision}:{record.description or 'migration'}")
        if mode == "all":
            for label in record.branch_labels:
                output.add(f"{label}:branch label")
                output.add(f"{label}@head:branch head")
    return sorted(output)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cwd", type=Path, default=Path.cwd())
    parser.add_argument("--config")
    parser.add_argument("--name", default="alembic")
    parser.add_argument("--mode", choices=("all", "heads"), default="all")
    args = parser.parse_args()
    for match in results(args.cwd, args.config, args.name, args.mode):
        print(match)


if __name__ == "__main__":
    main()
