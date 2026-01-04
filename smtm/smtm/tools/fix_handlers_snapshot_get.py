# -*- coding: utf-8 -*-
"""Fix handlers.py: ensure BUY/SELL side validation only applies to ORDER.* requests.

This tool is idempotent: running multiple times won't keep changing the file.
It targets the *actual* module path of smtm.engine.handlers (import-time resolution).

Usage:
  python -m smtm.tools.fix_handlers_snapshot_get
"""
from __future__ import annotations

import re
from pathlib import Path


def main() -> int:
    try:
        import smtm.engine.handlers as h  # noqa
    except Exception as e:
        print(f"[FIX] cannot import smtm.engine.handlers: {e}")
        return 2

    target = Path(h.__file__).resolve()
    if not target.exists():
        print(f"[FIX] handlers.py not found: {target}")
        return 2

    txt = target.read_text(encoding="utf-8", errors="replace")

    # Locate the suspicious side validation line(s)
    # Examples seen:
    #   return ack(... "side는 BUY/SELL" ...), None
    #   return ack(... "side??BUY/SELL" ...), None
    key_re = re.compile(r"side.{0,10}BUY/SELL", re.IGNORECASE)

    # If file doesn't contain it, nothing to do
    if not key_re.search(txt):
        print(f"[FIX] No BUY/SELL side validation string found in {target}. No change.")
        return 0

    lines = txt.splitlines(True)

    changed = False
    i = 0
    while i < len(lines):
        if key_re.search(lines[i]):
            # We assume this return belongs to a validation block.
            # We will ensure that the validation block is under:
            #   if t.startswith('ORDER.'):
            # by inserting that guard above the nearest preceding 'if' that checks side,
            # if the guard isn't already present nearby.
            # Strategy:
            # - Look back up to 12 lines for an existing ORDER guard
            # - If not present, insert an ORDER guard one indent level above current line's indent.
            start = max(0, i - 12)
            tail = "".join(lines[start:i])
            if "startswith('ORDER.')" in tail or 'startswith("ORDER.")' in tail:
                # already guarded
                i += 1
                continue

            # Determine indent of current line
            indent = re.match(r"^(\s*)", lines[i]).group(1)

            # Insert guard just before the closest previous non-empty line in this window
            insert_at = i
            guard_line = indent + "if t.startswith('ORDER.'):\n"
            # To keep structure valid, we need to indent the existing validation block.
            # Easiest safe approach: only wrap the single return line by converting it into:
            #   if t.startswith('ORDER.'):
            #       <return ack ...>
            # That avoids trying to re-indent multiple lines we can't reliably parse.
            # So we insert guard, then add extra indent to this return line only.
            lines.insert(insert_at, guard_line)
            lines[insert_at + 1] = indent + "    " + lines[insert_at + 1].lstrip()
            changed = True
            i += 2
            continue
        i += 1

    if not changed:
        print(f"[FIX] Found side validation string, but it already appears guarded. No change.")
        return 0

    # Normalize garbled message if present
    out = "".join(lines).replace("side??BUY/SELL", "side는 BUY/SELL")
    target.write_text(out, encoding="utf-8")
    print(f"[FIX] Patched {target} (guarded side validation under ORDER.*).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
