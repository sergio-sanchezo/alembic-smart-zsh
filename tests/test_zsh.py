"""Zsh routing and real Tab regressions (PTY tests optionally use pexpect)."""

from pathlib import Path
import os
import shlex
import shutil
import subprocess
import tempfile
import unittest

try:
    import pexpect
except ImportError:
    pexpect = None

PLUGIN = Path(__file__).resolve().parents[1] / "alembic-smart.plugin.zsh"
ZSH = shutil.which("zsh")
TEST_ENV = {**os.environ, "ALEMBIC_SMART_WRAP_UV": "0", "ALEMBIC_CONFIG": ""}


@unittest.skipUnless(ZSH, "zsh is not installed")
class ZshRoutingTests(unittest.TestCase):
    def run_zsh(self, script, env=None):
        result = subprocess.run(
            [ZSH, "-f", "-c", f"source {shlex.quote(str(PLUGIN))}\n{script}"],
            text=True, capture_output=True, check=True, env=env or TEST_ENV,
        )
        return result.stdout.strip()

    def test_no_wrapper_by_default(self):
        self.assertEqual(self.run_zsh('print ${+functions[alembic]}'), "0")

    def test_wrapper_opt_in_preserves_arguments(self):
        with tempfile.TemporaryDirectory() as directory:
            uv = Path(directory) / 'uv'
            uv.write_text('#!/bin/sh\nprintf "<%s>\\n" "$@"\n')
            uv.chmod(0o755)
            env = {**TEST_ENV, "ALEMBIC_SMART_WRAP_UV": "1",
                   "PATH": directory + os.pathsep + os.environ.get("PATH", "")}
            self.assertEqual(self.run_zsh('alembic revision -m "two words"', env),
                             '<run>\n<alembic>\n<revision>\n<-m>\n<two words>')

    def test_attached_config_and_section(self):
        self.assertEqual(self.run_zsh('''
            _describe() { :; }
            _alembic_smart_revisions() { print -r -- "$@"; }
            words=(alembic -ccustom.ini -ntenant upgrade '')
            CURRENT=5 PREFIX=''
            _alembic_smart
        '''), "upgrade custom.ini tenant")

    def test_uv_preserves_other_commands_and_is_idempotent(self):
        self.assertEqual(self.run_zsh('''
            autoload -Uz compinit; compinit -D
            _original_uv() { print -r -- "original:$*"; }
            compdef _original_uv uv
            alembic_smart_enable_uv
            alembic_smart_enable_uv
            words=(uv add requests '') CURRENT=4
            _alembic_smart_uv forwarded
        '''), "original:forwarded")

    def test_uv_rebases_words_and_current(self):
        self.assertEqual(self.run_zsh('''
            _alembic_smart() { print -r -- "$CURRENT:${(j:,:)words}"; }
            words=(uv run alembic upgrade '') CURRENT=5
            _alembic_smart_uv
            print -r -- "$CURRENT:${(j:,:)words}"
        '''), "3:alembic,upgrade,\n5:uv,run,alembic,upgrade,")


@unittest.skipUnless(ZSH and pexpect, "interactive tests require zsh and pexpect")
class InteractiveTabTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        (root / 'migrations' / 'versions').mkdir(parents=True)
        (root / 'alembic.ini').write_text('[alembic]\nscript_location = migrations\n')
        (root / 'custom.ini').write_text('[tenant]\nscript_location = migrations\n')
        (root / 'migrations' / 'versions' / 'abc123_change.py').write_text(
            "revision = 'abc123'\ndown_revision = None\n"
        )
        self.shell = pexpect.spawn(ZSH, ['-f'], cwd=str(root), encoding='utf-8',
                                  timeout=15, dimensions=(30, 160), env=TEST_ENV)
        self.addCleanup(self.shell.close, force=True)
        self.shell.sendline(
            "PROMPT='TEST> '; autoload -Uz compinit; compinit -D; "
            f"source {shlex.quote(str(PLUGIN))}; "
            "function capture-buffer() { print -r -- BUFFER=$BUFFER; zle send-break }; "
            "zle -N capture-buffer; bindkey '^X' capture-buffer; "
            "_test_uv() { compadd native_uv; }; compdef _test_uv uv; "
            "alembic_smart_enable_uv; print __SETUP_DONE__"
        )
        self.shell.expect_exact('\r\n__SETUP_DONE__\r\n')
        self.shell.expect_exact('TEST> ')

    def completed(self, line):
        # ^X reads the edited buffer; Enter never executes a migration command.
        self.shell.send(line + '\t\x18')
        self.shell.expect_exact('BUFFER=')
        return self.shell.readline().rstrip('\r\n')

    def test_command(self):
        self.assertEqual(self.completed('alembic upgr'), 'alembic upgrade ')

    def test_project_revision(self):
        self.assertEqual(self.completed('alembic upgrade abc'), 'alembic upgrade abc123 ')

    def test_custom_config_and_section(self):
        self.assertEqual(self.completed('alembic -ccustom.ini -ntenant upgrade abc'),
                         'alembic -ccustom.ini -ntenant upgrade abc123 ')

    def test_equals_revision_option(self):
        self.assertEqual(self.completed('alembic revision --head=abc'),
                         'alembic revision --head=abc123 ')

    def test_long_option(self):
        self.assertEqual(self.completed('alembic revision --autog'),
                         'alembic revision --autogenerate ')

    def test_negative_revision(self):
        self.assertEqual(self.completed('alembic downgrade -1'), 'alembic downgrade -1 ')

    def test_uv_adapter(self):
        self.assertEqual(self.completed('uv run alembic upgr'), 'uv run alembic upgrade ')

    def test_uv_native_fallback(self):
        self.assertEqual(self.completed('uv add nat'), 'uv add native_uv ')


if __name__ == '__main__':
    unittest.main()
