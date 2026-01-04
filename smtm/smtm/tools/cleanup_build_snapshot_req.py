# -*- coding: utf-8 -*-
"""Cleanup accidental SNAPSHOT.GET early-routing code inserted into _build_snapshot().

Symptom
- SNAPSHOT.GET -> ENGINE_EXCEPTION: name 'req' is not defined
- Traceback points inside _build_snapshot(), containing a stray line:
    if req.get("type") == "SNAPSHOT.GET":

Cause
- Previous auto-patch inserted SNAPSHOT.GET routing block into the wrong function.

Fix
- Remove any stray SNAPSHOT.GET-routing block that references `req` found INSIDE
  def _build_snapshot(...).

Idempotent.

Usage:
  python -m smtm.tools.cleanup_build_snapshot_req
"""
from __future__ import annotations

from pathlib import Path
import re


def main() -> int:
    import smtm.engine.handlers as h

    target = Path(h.__file__).resolve()
    txt = target.read_text(encoding="utf-8", errors="replace")
    lines = txt.splitlines(True)

    # Find _build_snapshot definition and its indent
    def_idx = None
    for i, line in enumerate(lines):
        if re.match(r"^def\s+_build_snapshot\s*\(", line):
            def_idx = i
            break
    if def_idx is None:
        print(f"[CLEAN] def _build_snapshot(...) not found in {target}")
        return 2

    base_indent = re.match(r"^(\s*)", lines[def_idx]).group(1)
    body_indent = base_indent + "    "

    # Remove blocks inside _build_snapshot that reference req SNAPSHOT.GET routing
    out = []
    i = 0
    removed = 0
    in_build = False
    skipping = False
    skip_indent = None

    while i < len(lines):
        line = lines[i]
        if i == def_idx:
            in_build = True
            out.append(line)
            i += 1
            continue

        # Determine if we left _build_snapshot (indentation back to base at new def)
        if in_build and re.match(r"^def\s+\w+\s*\(", line) and not line.startswith(body_indent):
            in_build = False

        if in_build and not skipping:
            if "fix_handlers_snapshot_priority2" in line or "fix_snapshot_get_args" in line or 'if req.get("type") == "SNAPSHOT.GET"' in line or "if req.get('type') == 'SNAPSHOT.GET'" in line:
                skipping = True
                skip_indent = re.match(r"^(\s*)", line).group(1)
                removed += 1
                i += 1
                continue

        if skipping:
            # stop skipping when indentation is less than skip_indent or we hit a blank line at same/higher indent after return
            cur_indent = re.match(r"^(\s*)", line).group(1)
            if len(cur_indent) < len(skip_indent):
                skipping = False
                skip_indent = None
                # do not consume this line; reprocess
                continue
            # also stop after an empty line at same indent or less
            if line.strip() == "" and len(cur_indent) <= len(skip_indent):
                skipping = False
                skip_indent = None
                i += 1
                continue
            # otherwise keep skipping
            i += 1
            continue

        out.append(line)
        i += 1

    if removed == 0:
        print(f"[CLEAN] No stray SNAPSHOT.GET routing found inside _build_snapshot in {target}. No change.")
        return 0

    target.write_text("".join(out), encoding="utf-8")
    print(f"[CLEAN] Removed {removed} stray routing block(s) inside _build_snapshot in {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
