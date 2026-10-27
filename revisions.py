#!/usr/bin/env python3
"""Read Alembic revision metadata without importing project code or Alembic.

Only Python standard-library parsers are used. No eval/exec/subprocesses/network.
"""

from __future__ import annotations

import argparse
import ast
import configparser
import os
from pathlib import Path
import re
import tomllib

MAX_FILE_BYTES = 256 * 1024
MAX_MIGRATIONS = 2000
VALID_TOKEN = re.compile(r"[a-zA-Z0-9_][a-zA-Z0-9_.-]{0,127}\Z")


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


def read_revision(path: Path) -> tuple[str, list[str], list[str], str] | None:
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
                        except (ValueError, TypeError, SyntaxError, RecursionError, MemoryError):
                            values.pop(key, None)
        rev = safe_token(values.get("revision"))
        if rev is None:
            return None

        def tokens(value: object) -> list[str]:
            if isinstance(value, str):
                return [token] if (token := safe_token(value)) else []
            if isinstance(value, (tuple, list)):
                return [token for v in value if (token := safe_token(v))]
            return []

        # Filenames are only used as human-readable descriptions.
        slug = path.stem
        if slug.startswith(rev + "_"):
            slug = slug[len(rev) + 1 :]
        slug = re.sub(r"[^\w .-]+", " ", slug, flags=re.UNICODE).strip()[:56]
        return rev, tokens(values.get("down_revision")), tokens(values.get("branch_labels")), slug
    except (OSError, UnicodeError, SyntaxError, ValueError, RecursionError, MemoryError):
        return None


def locations_for(cwd: Path, config_arg: str | None, section: str) -> list[Path]:
    cwd = cwd.resolve()
    config_name = config_arg or os.environ.get("ALEMBIC_CONFIG")
    if config_name:
        config_path = cwd / config_name
        if not config_path.is_file():
            return []
    elif (cwd / "alembic.ini").is_file():
        config_path = cwd / "alembic.ini"
    elif (cwd / "pyproject.toml").is_file():
        config_path = cwd / "pyproject.toml"
    else:
        return []

    script_location = ""
    version_locations: str | list[str] | None = None
    sep = ""
    try:
        if config_path.suffix == ".toml":
            data = tomllib.loads(read_bounded(config_path, "utf-8"))
            tool = data.get("tool", {})
            if not isinstance(tool, dict):
                return []
            opts = tool.get("alembic", {})
            if not isinstance(opts, dict):
                return []
            script_location = opts.get("script_location", "")
            version_locations = opts.get("version_locations")
            sep = opts.get("path_separator", "")
        else:
            ini = configparser.ConfigParser(interpolation=None, strict=False)
            ini.read_string(read_bounded(config_path, "utf-8"))
            opts = ini[section] if ini.has_section(section) else {}
            script_location = opts.get("script_location", "")
            version_locations = opts.get("version_locations")
            sep = opts.get("path_separator", "")
    except (OSError, UnicodeError, ValueError, configparser.Error, TypeError, RecursionError, MemoryError):
        return []

    if not isinstance(script_location, str):
        return []
    here = str(config_path.parent.resolve())

    def resolve(s: str) -> Path | None:
        s = s.replace("%(here)s", here).strip()
        if not s or ":" in s and s.split(":", 1)[0].isidentifier():
            # package:directory paths require importing app packages: deliberately unsupported.
            return None
        return Path(s) if Path(s).is_absolute() else cwd / s

    if version_locations:
        if isinstance(version_locations, list):
            entries = [s for s in version_locations if isinstance(s, str)]
        elif isinstance(version_locations, str):
            if sep == "os":
                entries = version_locations.split(os.pathsep)
            elif sep == "newline":
                entries = version_locations.splitlines()
            elif sep == "space" or not sep:
                entries = version_locations.split()
            elif sep == ":":
                entries = version_locations.split(":")
            elif sep == ";":
                entries = version_locations.split(";")
            else:
                entries = version_locations.split()
        else:
            return []
    else:
        entries = [str(path / "versions") for path in [resolve(script_location)] if path is not None]

    return [path for entry in entries if (path := resolve(entry)) is not None and path.is_dir()]


def results(cwd: Path, config: str | None, section: str, mode: str) -> list[str]:
    records = {}
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
                    records[record[0]] = record
        except OSError:
            continue

    referenced = {previous for _, prevs, _, _ in records.values() for previous in prevs}
    heads = set(records) - referenced
    output: set[str] = set()
    for rev, _, labels, desc in records.values():
        if mode == "heads" and rev not in heads:
            continue
        output.add(f"{rev}:{desc or 'migration'}")
        if mode == "all":
            for label in labels:
                output.add(f"{label}:branch label")
                if rev in heads:
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
