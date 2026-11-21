#!/usr/bin/env python3
"""Check the relative links of the documentation.

Scans the Markdown files of doc/, the root README.rst / DEVELOPMENT.md /
Governance.md and the ``doc/...`` paths quoted in the comments of etc/:

* every relative link must point to an existing file or directory;
* an ``#anchor`` must match a heading of the target page, using the GitHub
  anchor rules (lower case, punctuation removed, spaces turned into ``-``);
* MkDocs-only syntax (``!!!`` admonitions, ``{#id}`` anchors) is reported,
  since GitHub displays it verbatim.

Usage: python doc/tools/check_links.py [--allow-missing PATH ...]
Exit code 1 when a problem is found.
"""

import argparse
import os
import re
import sys
import unicodedata

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

MD_LINK = re.compile(r'(?<!\!)\[[^\]]*\]\(([^)\s]+)\)')
RST_LINK = re.compile(r'`[^`<]*<([^>`]+)>`_')
ETC_DOC_REF = re.compile(r'\b(doc/[A-Za-z0-9_./-]+\.md)')
HEADING = re.compile(r'^(#{1,6})\s+(.*?)\s*#*\s*$')
CODE_FENCE = re.compile(r'^\s*```')


def github_anchor(title):
    """Reproduce the anchor GitHub generates for a heading."""
    title = re.sub(r'`([^`]*)`', r'\1', title)
    title = re.sub(r'\[([^\]]*)\]\([^)]*\)', r'\1', title)
    title = title.replace('**', '').replace('__', '')
    title = title.strip().lower()
    out = []
    for char in title:
        if char in (' ', '-'):
            out.append('-')
        elif char == '_' or char.isalnum() or unicodedata.category(char).startswith('M'):
            out.append(char)
    return ''.join(out)


def anchors_of(path, cache={}):
    if path not in cache:
        anchors = set()
        counts = {}
        in_code = False
        with open(path, encoding='utf-8') as handle:
            for line in handle:
                if CODE_FENCE.match(line):
                    in_code = not in_code
                    continue
                if in_code:
                    continue
                match = HEADING.match(line)
                if match:
                    base = github_anchor(match.group(2))
                    number = counts.get(base, 0)
                    counts[base] = number + 1
                    anchors.add(base if number == 0 else '%s-%d' % (base, number))
        cache[path] = anchors
    return cache[path]


def iter_links(path):
    in_code = False
    with open(path, encoding='utf-8') as handle:
        for lineno, line in enumerate(handle, 1):
            if path.endswith('.md') and CODE_FENCE.match(line):
                in_code = not in_code
                continue
            if in_code:
                continue
            if path.endswith('.rst'):
                pattern, scanned = RST_LINK, line
            else:
                # links quoted inside inline code are examples, not links
                pattern, scanned = MD_LINK, re.sub(r'`[^`]*`', '', line)
            for match in pattern.finditer(scanned):
                yield lineno, match.group(1), line


def check_target(source, target, allow_missing):
    if re.match(r'^[a-z]+:', target) or target.startswith('mailto:'):
        return None
    path_part, _, anchor = target.partition('#')
    if path_part:
        resolved = os.path.normpath(os.path.join(os.path.dirname(source), path_part))
    else:
        resolved = source
    rel = os.path.relpath(resolved, ROOT)
    if not os.path.exists(resolved):
        if any(rel == a or rel.startswith(a.rstrip('/') + '/') for a in allow_missing):
            return None
        return 'missing target %s' % rel
    if anchor and resolved.endswith('.md') and anchor not in anchors_of(resolved):
        return 'missing anchor #%s in %s' % (anchor, rel)
    return None


def doc_files():
    for directory, _dirs, files in os.walk(os.path.join(ROOT, 'doc')):
        for name in files:
            if name.endswith('.md'):
                yield os.path.join(directory, name)
    for name in ('README.rst', 'DEVELOPMENT.md', 'Governance.md', 'CONTRIBUTING.rst'):
        path = os.path.join(ROOT, name)
        if os.path.exists(path):
            yield path
    for directory, _dirs, files in os.walk(os.path.join(ROOT, 'etc')):
        for name in files:
            if name.endswith('.md'):
                yield os.path.join(directory, name)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--allow-missing', nargs='*', default=[],
                        help='paths (relative to the repository) allowed to be missing')
    args = parser.parse_args()
    problems = []
    for path in sorted(doc_files()):
        rel = os.path.relpath(path, ROOT)
        with open(path, encoding='utf-8') as handle:
            text = handle.read()
        if path.endswith('.md') and '/revue/' not in path:
            for lineno, line in enumerate(text.splitlines(), 1):
                if line.lstrip().startswith('!!!') or re.search(r'\{#[\w-]+\}', line):
                    problems.append('%s:%d: MkDocs syntax not rendered by GitHub' % (rel, lineno))
        for lineno, target, _line in iter_links(path):
            error = check_target(path, target, args.allow_missing)
            if error:
                problems.append('%s:%d: %s' % (rel, lineno, error))
    # doc/ paths quoted in the comments of the example configuration
    for directory, _dirs, files in os.walk(os.path.join(ROOT, 'etc')):
        for name in files:
            if not name.endswith('.cfg'):
                continue
            path = os.path.join(directory, name)
            with open(path, encoding='utf-8') as handle:
                for lineno, line in enumerate(handle, 1):
                    for match in ETC_DOC_REF.finditer(line):
                        if not os.path.exists(os.path.join(ROOT, match.group(1))):
                            problems.append('%s:%d: missing %s'
                                            % (os.path.relpath(path, ROOT), lineno, match.group(1)))
    for problem in problems:
        print(problem)
    print('%d problem(s)' % len(problems))
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main())
