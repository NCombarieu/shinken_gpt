"""Smoke tests for the bin/ and libexec/ scripts that have no .py suffix."""

import subprocess
import sys
import warnings
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _python_scripts():
    for folder in ("bin", "libexec"):
        for path in sorted((ROOT / folder).rglob("*")):
            if not path.is_file() or "__pycache__" in path.parts:
                continue
            first = path.read_bytes().split(b"\n", 1)[0]
            if path.suffix == ".py" or (not path.suffix and b"python" in first):
                yield path


@pytest.mark.parametrize("path", list(_python_scripts()), ids=lambda p: str(p.relative_to(ROOT)))
def test_script_compiles_without_warning(path):
    source = path.read_bytes()
    with warnings.catch_warnings():
        warnings.simplefilter("error", SyntaxWarning)
        compile(source, str(path), "exec")


# Scripts run as-is (libexec is not rewritten by pip); daemon launchers are
# rewritten by pip at install time and are checked elsewhere.
def _shebang_checked():
    for path in _python_scripts():
        rel = path.relative_to(ROOT).as_posix()
        if rel.startswith("libexec/") or rel in (
                "bin/shinken", "bin/shinken-discovery", "bin/shinken-healthcheck"):
            yield path


@pytest.mark.parametrize("path", list(_shebang_checked()),
                         ids=lambda p: str(p.relative_to(ROOT)))
def test_script_has_python3_shebang(path):
    first = path.read_bytes().split(b"\n", 1)[0]
    assert first == b"#!/usr/bin/env python3"


def _run(*args, cwd=None):
    return subprocess.run([sys.executable, *args], capture_output=True, text=True,
                          timeout=60, check=False, cwd=cwd)


def test_shinken_cli_help_and_list(tmp_path):
    ini = tmp_path / "shinken.ini"
    proc = _run(str(ROOT / "bin" / "shinken"), "--help")
    assert proc.returncode == 0, proc.stderr
    assert "--list" in proc.stdout
    proc = _run(str(ROOT / "bin" / "shinken"), "--init", "-c", str(ini))
    assert proc.returncode == 0, proc.stderr
    assert "[paths]" in ini.read_text(encoding="utf-8")
    proc = _run(str(ROOT / "bin" / "shinken"), "--list", "-c", str(ini))
    assert proc.returncode == 0, proc.stderr
    for keyword in ("install", "search", "inventory", "doc-serve"):
        assert keyword in proc.stdout
    proc = _run(str(ROOT / "bin" / "shinken"), "-c", str(ini), "no-such-command")
    assert proc.returncode != 0


def test_shinken_discovery_help(tmp_path):
    proc = _run(str(ROOT / "bin" / "shinken-discovery"), "--help", cwd=tmp_path)
    assert proc.returncode == 0, proc.stderr
    assert "--cfg-input" in proc.stdout
