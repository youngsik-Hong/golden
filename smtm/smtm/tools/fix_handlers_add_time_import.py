# -*- coding: utf-8 -*-
"""Add missing `import time` to smtm/engine/handlers.py safely.

Usage:
  python -m smtm.tools.fix_handlers_add_time_import
"""
from __future__ import annotations

from pathlib import Path


def main() -> int:
    here = Path(__file__).resolve()
    root = here.parents[2]  # .../smtm/tools -> .../smtm
    target = root / "engine" / "handlers.py"
    if not target.exists():
        print(f"[FIX] handlers.py not found: {target}")
        return 2

    txt = target.read_text(encoding="utf-8")
    if "import time" in txt:
        print("[FIX] import time already present. No change.")
        return 0

    lines = txt.splitlines(True)

    insert_at = 0
    for i, line in enumerate(lines):
        if line.startswith("from __future__"):
            insert_at = i + 1
    for i, line in enumerate(lines[:80]):
        if line.startswith("from typing") or line.startswith("import "):
            insert_at = max(insert_at, i + 1)

    lines.insert(insert_at, "import time\n")
    target.write_text("".join(lines), encoding="utf-8")
    print(f"[FIX] Added `import time` to {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
