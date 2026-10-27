"""Run: python3 -m unittest discover -s tests -v"""

import importlib.util
from pathlib import Path
import tempfile
from unittest import mock
import os
import unittest

PROJECT_DIR = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("smart_revisions", PROJECT_DIR / "revisions.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class StaticRevisionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        environment = mock.patch.dict(os.environ, {"ALEMBIC_CONFIG": ""})
        environment.start()
        self.addCleanup(environment.stop)
        self.versions = self.root / "migrations" / "versions"
        self.versions.mkdir(parents=True)
        (self.root / "alembic.ini").write_text(
            "[alembic]\nscript_location = %(here)s/migrations\n", encoding="utf-8"
        )

    def migration(self, filename, rev, parent=None, labels=None, extra=""):
        (self.versions / filename).write_text(
            f"revision: str = {rev!r}\n"
            f"down_revision = {parent!r}\n"
            f"branch_labels = {labels!r}\n"
            f"{extra}\n",
            encoding="utf-8",
        )

    def test_static_revisions_and_heads(self):
        self.migration("a1_create_users.py", "a1", None)
        self.migration("b2_add_active.py", "b2", "a1")
        self.assertEqual(
            module.results(self.root, None, "alembic", "all"),
            ["a1:create_users", "b2:add_active"],
        )
        self.assertEqual(module.results(self.root, None, "alembic", "heads"), ["b2:add_active"])

    def test_multiple_heads_branch_labels_and_multiple_parents(self):
        self.migration("a.py", "a", None)
        self.migration("b.py", "b", "a", ("payments",))
        self.migration("c.py", "c", "a")
        heads = module.results(self.root, None, "alembic", "heads")
        self.assertEqual(heads, ["b:b", "c:c"])
        all_results = module.results(self.root, None, "alembic", "all")
        self.assertIn("payments:branch label", all_results)
        self.assertIn("payments@head:branch head", all_results)
        self.migration("d.py", "d", ("b", "c"))
        self.assertEqual(module.results(self.root, None, "alembic", "heads"), ["d:d"])

    def test_source_python_is_never_executed(self):
        sentinel = self.root / "BREACH.txt"
        attack = (
            "import os\n"
            f"os.system('touch {sentinel}')\n"
            "def upgrade():\n"
            "    raise RuntimeError('should not execute')\n"
        )
        self.migration("safe_revision.py", "safe", extra=attack)
        self.assertIn("safe:revision", module.results(self.root, None, "alembic", "all"))
        self.assertFalse(sentinel.exists())

    def test_malicious_dynamic_revision_assignment_not_evaluated(self):
        sentinel = self.root / "BREACH.txt"
        (self.versions / "evil.py").write_text(
            f"revision = __import__('os').system('touch {sentinel}')\n", encoding="utf-8"
        )
        self.assertEqual(module.results(self.root, None, "alembic", "all"), [])
        self.assertFalse(sentinel.exists())

    def test_large_and_invalid_migration_files_ignored(self):
        (self.versions / "huge.py").write_text("#" * (module.MAX_FILE_BYTES + 1))
        (self.versions / "bad_syntax.py").write_text("revision = (\n")
        self.assertEqual(module.results(self.root, None, "alembic", "all"), [])

    def test_custom_config_and_section(self):
        (self.root / "custom.ini").write_text(
            "[tenant]\nscript_location = migrations\n", encoding="utf-8"
        )
        self.migration("123_my_change.py", "123")
        self.assertEqual(module.results(self.root, "custom.ini", "tenant", "heads"), ["123:my_change"])
        self.assertEqual(module.results(self.root, "custom.ini", "alembic", "heads"), [])

    def test_pyproject_toml(self):
        (self.root / "alembic.ini").unlink()
        (self.root / "pyproject.toml").write_text(
            '[tool.alembic]\nscript_location = "migrations"\n', encoding="utf-8"
        )
        self.migration("ab1_hello.py", "ab1")
        self.assertEqual(module.results(self.root, None, "alembic", "all"), ["ab1:hello"])

    def test_multiple_version_locations(self):
        extra_dir = self.root / "other" / "versions"
        extra_dir.mkdir(parents=True)
        (self.root / "alembic.ini").write_text(
            "[alembic]\nscript_location = migrations\n"
            "path_separator = os\n"
            f"version_locations = migrations/versions{__import__('os').pathsep}other/versions\n"
        )
        self.migration("a_one.py", "a")
        (extra_dir / "b_two.py").write_text("revision='b'\ndown_revision=None\n")
        self.assertEqual(module.results(self.root, None, "alembic", "heads"), ["a:one", "b:two"])

    def test_relative_cwd_is_resolved_once(self):
        self.migration("a_change.py", "a")
        relative = Path(os.path.relpath(self.root))
        self.assertEqual(module.results(relative, None, "alembic", "all"), ["a:change"])

    def test_malformed_toml_shapes_are_ignored(self):
        (self.root / "alembic.ini").unlink()
        for source in ('tool = "oops"', '[tool]\nalembic = 1',
                       '[tool.alembic]\nscript_location = []'):
            with self.subTest(source=source):
                (self.root / "pyproject.toml").write_text(source)
                self.assertEqual(module.results(self.root, None, "alembic", "all"), [])

    def test_oversized_configs_are_ignored(self):
        (self.root / "alembic.ini").write_text("#" * (module.MAX_FILE_BYTES + 1))
        self.assertEqual(module.results(self.root, None, "alembic", "all"), [])

    def test_dynamic_reassignment_does_not_keep_stale_revision(self):
        self.migration("a_change.py", "a", extra="revision = compute_revision()")
        self.assertEqual(module.results(self.root, None, "alembic", "all"), [])

    def test_scan_limit_counts_invalid_files(self):
        for number in range(5):
            (self.versions / f"invalid_{number}.py").write_text("# no metadata")
        with mock.patch.object(module, "MAX_MIGRATIONS", 2), mock.patch.object(
            module, "read_revision", wraps=module.read_revision
        ) as reader:
            self.assertEqual(module.results(self.root, None, "alembic", "all"), [])
            self.assertEqual(reader.call_count, 2)

    def test_scan_limit_counts_duplicate_ids(self):
        for number in range(5):
            self.migration(f"a_{number}.py", "a")
        with mock.patch.object(module, "MAX_MIGRATIONS", 2), mock.patch.object(
            module, "read_revision", wraps=module.read_revision
        ) as reader:
            module.results(self.root, None, "alembic", "all")
            self.assertEqual(reader.call_count, 2)

    def test_scan_limit_is_shared_across_directories(self):
        other = self.root / "other"
        other.mkdir()
        self.migration("a_one.py", "a")
        (other / "b_two.py").write_text("revision = 'b'\n")
        with (
            mock.patch.object(module, "locations_for", return_value=[self.versions, other]),
            mock.patch.object(module, "MAX_MIGRATIONS", 1),
        ):
            self.assertEqual(module.results(self.root, None, "alembic", "all"), ["a:one"])

    def test_alembic_config_environment_override(self):
        (self.root / "tenant.ini").write_text("[tenant]\nscript_location = migrations\n")
        self.migration("a_change.py", "a")
        with mock.patch.dict(os.environ, {"ALEMBIC_CONFIG": "tenant.ini"}):
            self.assertEqual(module.results(self.root, None, "tenant", "all"), ["a:change"])
            self.assertEqual(module.results(self.root, "missing.ini", "tenant", "all"), [])

    def test_read_is_bounded_even_if_stat_is_stale(self):
        path = mock.Mock()
        path.is_file.return_value = True
        path.stat.return_value.st_size = 1
        stream = mock.MagicMock()
        stream.read.return_value = b"#" * (module.MAX_FILE_BYTES + 1)
        path.open = mock.MagicMock()
        path.open.return_value.__enter__.return_value = stream
        with self.assertRaises(ValueError):
            module.read_bounded(path, "utf-8")
        stream.read.assert_called_once_with(module.MAX_FILE_BYTES + 1)


if __name__ == "__main__":
    unittest.main()
