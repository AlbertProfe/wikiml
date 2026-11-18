#!/usr/bin/env python3
"""Validate data/*.yml catalogs and write _generated/data-catalog.json.

Fails the render on a missing required field, a duplicate id, or a missing
code folder (and starter.py) for types that keep their code in data/.
files / filesQty are computed from the folder and never read from YAML.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
GEN = ROOT / "_generated"

REQUIRED = ("id", "name", "tags", "description", "credit")
REQUIRED_ALSO = ("type", "section", "level", "source", "page", "status", "solution")
CREDIT_FIELDS = ("author", "url", "licence")
SOLUTIONS = {"show", "toggle", "hidden"}
# Labs live in GitHub repos; examples and Helsinki exercises keep code here.
LOCAL_CODE_TYPES = {"example", "helsinki"}
ID_RE = re.compile(r"^(Ex|Lab)#[A-Z]{2}-\d{4}$")
FORBIDDEN_STORED = ("files", "filesQty", "files_qty")

errors: list[str] = []


def err(msg: str) -> None:
    errors.append(msg)


def id_parts(eid: str) -> tuple[str, str, str] | None:
    m = ID_RE.match(eid or "")
    if not m:
        return None
    kind, rest = eid.split("#", 1)
    sec, num = rest.split("-", 1)
    return kind.lower(), sec.lower(), num


def folder_for(eid: str) -> Path | None:
    parts = id_parts(eid)
    if not parts:
        return None
    kind, sec, num = parts
    return DATA / sec / f"{kind}-{num}"


def list_code_files(folder: Path) -> list[str]:
    if not folder.is_dir():
        return []
    names = sorted(
        p.name
        for p in folder.iterdir()
        if p.is_file() and not p.name.startswith(".")
    )
    return names


def load_catalogs() -> list[dict]:
    if not DATA.is_dir():
        return []
    entries: list[dict] = []
    seen: dict[str, str] = {}
    for yml in sorted(DATA.glob("*.yml")):
        try:
            raw = yaml.safe_load(yml.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            err(f"{yml.relative_to(ROOT)}: invalid YAML ({exc})")
            continue
        if raw is None:
            err(f"{yml.relative_to(ROOT)}: file is empty")
            continue
        if not isinstance(raw, dict) or "entries" not in raw:
            err(f"{yml.relative_to(ROOT)}: expected a top-level 'entries' list")
            continue
        items = raw["entries"]
        if not isinstance(items, list):
            err(f"{yml.relative_to(ROOT)}: 'entries' must be a list")
            continue
        expected_sec = yml.stem.lower()
        for i, item in enumerate(items, start=1):
            loc = f"{yml.relative_to(ROOT)} entry {i}"
            if not isinstance(item, dict):
                err(f"{loc}: not a mapping")
                continue
            validate_entry(item, loc, expected_sec, seen, yml)
            entries.append(item)
    return entries


def validate_entry(
    item: dict, loc: str, expected_sec: str, seen: dict[str, str], yml: Path
) -> None:
    for key in REQUIRED + REQUIRED_ALSO:
        if key not in item or item[key] in (None, ""):
            err(f"{loc}: missing required field '{key}'")

    for key in FORBIDDEN_STORED:
        if key in item:
            err(f"{loc}: do not store '{key}'; it is computed from the code folder")

    eid = item.get("id")
    if eid:
        if not ID_RE.match(str(eid)):
            err(f"{loc}: id '{eid}' must look like Ex#PY-0001 or Lab#FU-0003")
        elif eid in seen:
            err(f"{loc}: duplicate id '{eid}' (already in {seen[eid]})")
        else:
            seen[eid] = loc

    tags = item.get("tags")
    if tags is not None and not (
        isinstance(tags, list) and tags and all(isinstance(t, str) and t.strip() for t in tags)
    ):
        err(f"{loc}: 'tags' must be a non-empty list of strings")

    credit = item.get("credit")
    if credit is not None:
        if not isinstance(credit, dict):
            err(f"{loc}: 'credit' must be a mapping with {', '.join(CREDIT_FIELDS)}")
        else:
            for field in CREDIT_FIELDS:
                if not credit.get(field):
                    err(f"{loc}: credit missing '{field}'")

    section = item.get("section")
    if section and str(section).lower() != expected_sec:
        err(
            f"{loc}: section '{section}' does not match catalog file "
            f"'{yml.name}' (expected {expected_sec.upper()})"
        )

    solution = item.get("solution")
    if solution is not None and solution not in SOLUTIONS:
        err(f"{loc}: solution must be one of {sorted(SOLUTIONS)}, not '{solution}'")

    entry_type = str(item.get("type") or "").lower()
    folder = folder_for(str(eid)) if eid else None
    if entry_type in LOCAL_CODE_TYPES:
        if folder is None:
            return
        rel = folder.relative_to(ROOT)
        if not folder.is_dir():
            err(f"{loc}: missing code folder {rel}/")
            return
        files = list_code_files(folder)
        if "starter.py" not in files:
            err(f"{loc}: {rel}/ is missing starter.py")
        if item.get("solution") in {"show", "toggle"} and "solution.py" not in files:
            err(f"{loc}: solution is '{item.get('solution')}' but {rel}/ has no solution.py")


def enrich(item: dict) -> dict:
    """Add computed path metadata; never trust stored files/filesQty."""
    out = dict(item)
    out.pop("files", None)
    out.pop("filesQty", None)
    out.pop("files_qty", None)
    eid = str(item.get("id") or "")
    parts = id_parts(eid)
    folder = folder_for(eid)
    if parts and folder:
        kind, sec, num = parts
        out["kind"] = kind
        out["section_key"] = sec
        out["slug"] = f"{kind}-{num}"
        out["anchor"] = f"{kind}-{sec}-{num}"
        out["folder"] = str(folder.relative_to(ROOT)).replace("\\", "/")
        files = list_code_files(folder)
        out["files"] = files
        out["filesQty"] = len(files)
        out["has_starter"] = "starter.py" in files
        out["has_solution"] = "solution.py" in files
    return out


def main() -> int:
    entries = load_catalogs()
    if errors:
        print("data catalog validation failed:", file=sys.stderr)
        for msg in errors:
            print(f"  - {msg}", file=sys.stderr)
        return 1

    catalog = {"entries": {e["id"]: enrich(e) for e in entries if e.get("id")}}
    GEN.mkdir(parents=True, exist_ok=True)
    dest = GEN / "data-catalog.json"
    dest.write_text(json.dumps(catalog, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"data catalog ok: {len(catalog['entries'])} entries -> {dest.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
