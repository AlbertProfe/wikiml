#!/usr/bin/env python3
"""Expand {{< ex Ex#PY-0001 >}} markers into quarto-live cells before render.

quarto-live (live.lua) walks {pyodide} CodeBlocks in its own filter pass, which
runs *before* custom shortcodes. A shortcode that emits a pyodide cell therefore
arrives too late and is written out as a static <pre>. This script expands the
markers in the .qmd files at pre-render — so the cells exist at parse time —
and restores the shortcode source at post-render.

Usage:
  python3 tools/expand-exercises.py           # pre-render (restore leftovers, then expand)
  python3 tools/expand-exercises.py --restore # post-render
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GEN = ROOT / "_generated"
BACKUP = GEN / "src"
CATALOG = GEN / "data-catalog.json"
MARKER_RE = re.compile(r"\{\{<\s*ex\s+([^>]+?)\s*>\}\}")
SKIP_DIRS = {"_site", "_generated", "_archive", "_extensions", "_freeze", ".git", ".quarto"}


def catalog() -> dict:
    if not CATALOG.is_file():
        sys.exit("expand-exercises: missing _generated/data-catalog.json (run validate-data.py first)")
    data = json.loads(CATALOG.read_text(encoding="utf-8"))
    entries = data.get("entries") or {}
    if not isinstance(entries, dict):
        sys.exit("expand-exercises: catalog has no entries object")
    return entries


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def html_escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def sample_inner(text: str) -> str:
    text = text.strip("\n")
    if re.search(r"<[a-zA-Z/!]", text):
        return text
    return f"<pre><code>{html_escape(text)}</code></pre>"


def render_card(entry: dict, root: Path) -> str:
    eid = entry["id"]
    anchor = entry.get("anchor") or eid.replace("#", "-").lower()
    folder = entry.get("folder")
    if not folder:
        sys.exit(f"expand-exercises: {eid} has no code folder")
    starter_path = root / folder / "starter.py"
    if not starter_path.is_file():
        sys.exit(f"expand-exercises: missing {folder}/starter.py")
    starter = starter_path.read_text(encoding="utf-8")
    if not starter.endswith("\n"):
        starter += "\n"

    credit = entry.get("credit") or {}
    author = credit.get("author") or ""
    url = credit.get("url") or ""
    licence = credit.get("licence") or ""
    if url:
        credit_html = (
            f'Credit: <a href="{html_escape(url)}" rel="noopener" target="_blank">'
            f"{html_escape(author)}</a>"
        )
    else:
        credit_html = f"Credit: {html_escape(author)}"
    if licence:
        credit_html += f" · {html_escape(licence)}"

    tags = entry.get("tags") or []
    tags_html = " ".join(
        f'<span class="code-unit-tag">{html_escape(str(t))}</span>' for t in tags
    )
    name = html_escape(str(entry.get("name") or eid))
    files_qty = entry.get("filesQty", 0)
    typ = html_escape(str(entry.get("type") or ""))
    solution = html_escape(str(entry.get("solution") or "hidden"))

    parts = [
        (
            f'::: {{.code-unit #{anchor} data-id="{eid}" '
            f'data-files-qty="{files_qty}" data-type="{typ}" data-solution="{solution}"}}'
        ),
        '<div class="code-unit-meta">',
        f'<div class="code-unit-name">{name}</div>',
    ]
    if tags_html:
        parts.append(f'<div class="code-unit-tags">{tags_html}</div>')
    parts += [
        f'<div class="code-unit-credit">{credit_html}</div>',
        "</div>",
        "",
        f"[{eid}](#{anchor}){{.code-unit-id}}",
        "```{pyodide}",
        "#| autorun: true",
        starter.rstrip("\n"),
        "```",
    ]

    sample = entry.get("sample_output")
    if isinstance(sample, str) and sample.strip():
        parts += ["", "::: {.sample-output}", sample_inner(sample), ":::"]

    mode = str(entry.get("solution") or "hidden")
    if mode in {"show", "toggle"} and entry.get("has_solution"):
        sol = (root / folder / "solution.py").read_text(encoding="utf-8")
        escaped = html_escape(sol.rstrip("\n"))
        if mode == "toggle":
            parts += [
                "",
                '<details class="code-unit-solution">',
                "<summary>Solution</summary>",
                f'<pre><code class="language-python">{escaped}</code></pre>',
                "</details>",
            ]
        else:
            parts += [
                "",
                '<div class="code-unit-solution is-open">',
                '<div class="code-unit-solution-label">Solution</div>',
                f'<pre><code class="language-python">{escaped}</code></pre>',
                "</div>",
            ]

    parts += [":::", ""]
    return "\n".join(parts)


def iter_qmd() -> list[Path]:
    files = []
    for path in ROOT.rglob("*.qmd"):
        if any(part in SKIP_DIRS for part in path.relative_to(ROOT).parts):
            continue
        files.append(path)
    return sorted(files)


def restore(*, quiet: bool = False) -> int:
    if not BACKUP.is_dir():
        if not quiet:
            print("expand-exercises: nothing to restore")
        return 0
    count = 0
    for backup in sorted(BACKUP.rglob("*.qmd")):
        rel = backup.relative_to(BACKUP)
        dest = ROOT / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(backup.read_text(encoding="utf-8"), encoding="utf-8")
        backup.unlink()
        count += 1
    # tidy empty dirs
    for folder in sorted(BACKUP.rglob("*"), reverse=True):
        if folder.is_dir():
            try:
                folder.rmdir()
            except OSError:
                pass
    if not quiet or count:
        print(f"expand-exercises: restored {count} source file(s)")
    return count


def expand() -> int:
    entries = catalog()
    count_files = 0
    count_markers = 0
    missing = []
    for path in iter_qmd():
        text = read(path)
        if not MARKER_RE.search(text):
            continue
        rel = path.relative_to(ROOT)
        backup = BACKUP / rel
        backup.parent.mkdir(parents=True, exist_ok=True)
        backup.write_text(text, encoding="utf-8")

        def repl(match: re.Match[str]) -> str:
            eid = match.group(1).strip()
            entry = entries.get(eid)
            if not entry:
                missing.append(f"{rel}: unknown id '{eid}'")
                return match.group(0)
            return render_card(entry, ROOT)

        new, n = MARKER_RE.subn(repl, text)
        if missing:
            continue
        path.write_text(new, encoding="utf-8")
        count_files += 1
        count_markers += n
        print(f"expand-exercises: {rel} ({n} cell(s))")
    if missing:
        # restore what we already backed up so the tree is clean on failure
        restore(quiet=True)
        print("expand-exercises failed:", file=sys.stderr)
        for msg in missing:
            print(f"  - {msg}", file=sys.stderr)
        sys.exit(1)
    print(f"expand-exercises: expanded {count_markers} marker(s) in {count_files} file(s)")
    return count_markers


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--restore", action="store_true", help="restore shortcode sources after render")
    args = parser.parse_args()
    if args.restore:
        restore()
        return 0
    restore(quiet=True)
    expand()
    return 0


if __name__ == "__main__":
    sys.exit(main())
