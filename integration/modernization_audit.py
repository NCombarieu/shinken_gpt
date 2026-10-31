#!/usr/bin/env python3
"""Audit compatibility/deprecation debt in shipped Python code.

Known removed compatibility layers and files that do not even parse
(SyntaxError, e.g. Python 2 code left behind) are hard failures so they cannot
silently return. Remaining deprecated imports and SyntaxWarnings (invalid
escape sequences, errors in a future Python) are reported for staged cleanup.
"""

from __future__ import annotations

import ast
import json
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOTS = ("shinken", "bin", "cli", "modules", "libexec", "integration")
WATCHED_IMPORTS = {"cgi", "imp", "optparse", "distutils", "six"}
# Python-2 compatibility layers must not return to the Python-3-only runtime.
FORBIDDEN_IMPORTS = {"cgi", "imp", "six"}
FORBIDDEN_PATHS = {
    "shinken/webui/bottlecore.py": "vendored Bottle runtime",
    "shinken/webui/bottlewebui.py": "vendored legacy Bottle WebUI",
}


def iter_python_files():
    for root_name in SOURCE_ROOTS:
        root = ROOT / root_name
        if root.is_file() and root.suffix == ".py":
            yield root
            continue
        if root.is_dir():
            yield from sorted(root.rglob("*.py"))
    for script_dir in (ROOT / "bin", ROOT / "libexec"):
        if not script_dir.is_dir():
            continue
        for path in sorted(script_dir.iterdir()):
            if path.is_file() and path.suffix != ".py":
                try:
                    first_line = path.open("r", encoding="utf-8", errors="ignore").readline()
                except OSError:
                    continue
                if "python" in first_line:
                    yield path


def parse(path: Path):
    """Return (tree, syntax_error, syntax_warnings) for one file."""
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exp:
        return None, "%s: %s" % (type(exp).__name__, exp), []
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", SyntaxWarning)
        try:
            tree = ast.parse(source, filename=str(path))
        except SyntaxError as exp:
            return None, "line %s: %s" % (exp.lineno, exp.msg), []
    syntax_warnings = sorted({
        "line %s: %s" % (w.lineno, w.message) for w in caught
        if issubclass(w.category, SyntaxWarning)
    })
    return tree, None, syntax_warnings


def imports_for(tree):
    if tree is None:
        return []
    findings = []
    for node in ast.walk(tree):
        names = []
        if isinstance(node, ast.Import):
            names = [alias.name.split(".", 1)[0] for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            names = [node.module.split(".", 1)[0]]
        for name in names:
            if name in WATCHED_IMPORTS:
                findings.append({"module": name, "line": node.lineno})
    return findings


def main() -> int:
    deprecated_imports = []
    python2_shebangs = []
    syntax_errors = []
    syntax_warnings = []
    seen = set()
    for path in iter_python_files():
        path = path.resolve()
        if path in seen:
            continue
        seen.add(path)
        relative = path.relative_to(ROOT).as_posix()
        try:
            first_line = path.open("r", encoding="utf-8", errors="ignore").readline().strip()
        except OSError:
            first_line = ""
        if "python2" in first_line:
            python2_shebangs.append(relative)
        tree, error, file_warnings = parse(path)
        if error:
            syntax_errors.append({"path": relative, "error": error})
        for message in file_warnings:
            syntax_warnings.append({"path": relative, "warning": message})
        for finding in imports_for(tree):
            deprecated_imports.append({"path": relative, **finding})

    forbidden_paths = [
        {"path": path, "reason": reason}
        for path, reason in FORBIDDEN_PATHS.items()
        if (ROOT / path).exists()
    ]
    forbidden_imports = [
        finding for finding in deprecated_imports if finding["module"] in FORBIDDEN_IMPORTS
    ]
    report = {
        "deprecated_imports": deprecated_imports,
        "python2_shebangs": python2_shebangs,
        "forbidden_legacy_paths": forbidden_paths,
        "forbidden_imports": forbidden_imports,
        "syntax_errors": syntax_errors,
        "syntax_warnings": syntax_warnings,
        "counts": {
            "deprecated_imports": len(deprecated_imports),
            "python2_shebangs": len(python2_shebangs),
            "forbidden_legacy_paths": len(forbidden_paths),
            "forbidden_imports": len(forbidden_imports),
            "syntax_errors": len(syntax_errors),
            "syntax_warnings": len(syntax_warnings),
        },
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    if python2_shebangs or forbidden_paths or forbidden_imports or syntax_errors:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
