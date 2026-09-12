#!/usr/bin/env python3
"""Inventory compatibility/deprecation debt in shipped Python code.

The report is intentionally informational while the modernization review is in
progress. Once the listed compatibility layers are removed or explicitly
accepted, CI can turn the corresponding categories into hard failures.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOTS = ("shinken", "bin", "cli", "modules", "libexec")
WATCHED_IMPORTS = {"cgi", "imp", "optparse", "distutils", "six"}
VENDORED_FRAMEWORKS = {
    "shinken/webui/bottlecore.py": "vendored Bottle 0.12.x compatibility copy",
    "shinken/webui/bottlewebui.py": "vendored pre-0.12 Bottle compatibility copy",
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


def imports_for(path: Path):
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
    except (OSError, SyntaxError, UnicodeDecodeError):
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
        for finding in imports_for(path):
            deprecated_imports.append({"path": relative, **finding})

    vendored = [
        {"path": path, "reason": reason}
        for path, reason in VENDORED_FRAMEWORKS.items()
        if (ROOT / path).exists()
    ]
    report = {
        "deprecated_imports": deprecated_imports,
        "python2_shebangs": python2_shebangs,
        "vendored_legacy_frameworks": vendored,
        "counts": {
            "deprecated_imports": len(deprecated_imports),
            "python2_shebangs": len(python2_shebangs),
            "vendored_legacy_frameworks": len(vendored),
        },
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
