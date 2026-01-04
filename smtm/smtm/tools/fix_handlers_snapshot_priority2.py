# -*- coding: utf-8 -*-
"""Robust fix: ensure SNAPSHOT.GET returns before any payload validation in smtm.engine.handlers.

This version does NOT depend on `t = req.get('type')` being present.
It inserts an early-return right after `def handle_command(...):` (after docstring if any):

    if req.get("type") == "SNAPSHOT.GET":
        return ack(req, state, True, payload=_build_snapshot(state)), None

Idempotent via marker.

Usage:
  python -m smtm.tools.fix_handlers_snapshot_priority2
"""
from __future__ import annotations

import re
from pathlib import Path


MARKER = "fix_handlers_snapshot_priority2"


def _find_insertion(lines, def_idx):
    # insert after optional docstring immediately following def line
    i = def_idx + 1
    # skip blank lines
    while i < len(lines) and lines[i].strip() == "":
        i += 1
    if i < len(lines):
        s = lines[i].lstrip()
        if s.startswith('"""') or s.startswith("'''"):
            # consume until closing triple quote
            quote = '"""' if s.startswith('"""') else "'''"
            i += 1
            while i < len(lines):
                if quote in lines[i]:
                    i += 1
                    break
                i += 1
            # skip following blank line
            while i < len(lines) and lines[i].strip() == "":
                i += 1
    return i


def main() -> int:
    import smtm.engine.handlers as h
    target = Path(h.__file__).resolve()
    txt = target.read_text(encoding="utf-8", errors="replace")

    if MARKER in txt:
        print(f"[FIX] Marker already present in {target}. No change.")
        return 0

    lines = txt.splitlines(True)
    # find def handle_command
    def_idx = None
    for i, line in enumerate(lines):
        if re.match(r"^def\s+handle_command\s*\(", line):
            def_idx = i
            break
    if def_idx is None:
        print(f"[FIX] def handle_command(...) not found in {target}")
        return 2

    insert_at = _find_insertion(lines, def_idx)
    indent = "    "  # function indent

    block = (
        f"{indent}# {MARKER}: route SNAPSHOT.GET before any validation\n"
        f"{indent}if req.get(\"type\") == \"SNAPSHOT.GET\":\n"
        f"{indent}    return ack(req, state, True, payload=_build_snapshot(state)), None\n\n"
    )

    lines.insert(insert_at, block)
    target.write_text("".join(lines), encoding="utf-8")
    print(f"[FIX] Inserted SNAPSHOT.GET early routing into {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
