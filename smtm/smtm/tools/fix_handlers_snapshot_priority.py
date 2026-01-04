# -*- coding: utf-8 -*-
"""Ensure SNAPSHOT.GET is handled before any order payload validation in smtm.engine.handlers.

Symptom:
- SNAPSHOT.GET returns INVALID_PAYLOAD like 'price/qty 숫자 필요' because generic validation
  runs before routing.

Fix:
- Insert early return branch:
    if t == "SNAPSHOT.GET": return ack(req, state, True, payload=_build_snapshot(state)), None
  right after 't = req.get("type")' (or equivalent) in handle_command.

Idempotent: won't insert twice.

Usage:
  python -m smtm.tools.fix_handlers_snapshot_priority
"""
from __future__ import annotations

from pathlib import Path
import re


def main() -> int:
    import smtm.engine.handlers as h  # resolve actual path

    target = Path(h.__file__).resolve()
    txt = target.read_text(encoding="utf-8", errors="replace")

    if "fix_handlers_snapshot_priority" in txt:
        # previous marker
        print(f"[FIX] Marker already present in {target}. No change.")
        return 0

    # Find handle_command and the first assignment to t
    # Common patterns:
    #   t = req.get("type")
    #   t = req.get('type')
    m = re.search(r"def\s+handle_command\(.*?\):[\s\S]*?\n(\s*)t\s*=\s*req\.get\((?:'type'|\"type\")\)", txt)
    if not m:
        print(f"[FIX] Could not find handle_command() with t=req.get('type') in {target}")
        return 2

    indent = m.group(1)
    # Check if early SNAPSHOT.GET branch already exists near the top of handle_command
    head_window = txt[m.start(): m.start() + 1200]
    if re.search(r'if\s+t\s*==\s*["\']SNAPSHOT\.GET["\']', head_window):
        print(f"[FIX] SNAPSHOT.GET early branch already exists in {target}. No change.")
        return 0

    insert = (
        f"\n{indent}# fix_handlers_snapshot_priority: route SNAPSHOT.GET before payload validation\n"
        f"{indent}if t == \"SNAPSHOT.GET\":\n"
        f"{indent}    return ack(req, state, True, payload=_build_snapshot(state)), None\n"
    )

    # Insert right after the t = req.get('type') line
    # We'll locate end of that line
    tline = re.search(r"\n" + re.escape(indent) + r"t\s*=\s*req\.get\((?:'type'|\"type\")\).*?\n", txt[m.start():])
    if not tline:
        print(f"[FIX] Could not locate t assignment line end in {target}")
        return 2

    pos = m.start() + tline.end()
    out = txt[:pos] + insert + txt[pos:]

    target.write_text(out, encoding="utf-8")
    print(f"[FIX] Inserted SNAPSHOT.GET early routing into {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
