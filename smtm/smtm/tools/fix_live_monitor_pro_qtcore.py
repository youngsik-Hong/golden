# -*- coding: utf-8 -*-
"""Fix live_monitor_pro.py (PyQt6 + pyqtgraph):

1) Ensure `from __future__ import annotations` is the first import (after shebang/encoding).
2) Ensure `from pyqtgraph.Qt import QtCore, QtGui` exists so QtCore.QRectF works.

Creates .bak backup.
"""
from __future__ import annotations

import re
from pathlib import Path

TARGET = Path(__file__).resolve().parents[1] / "ui" / "live_monitor_pro.py"

def _fix_future_import(text: str) -> str:
    lines = text.splitlines()
    shebang = None
    encoding = None
    i = 0
    if lines and lines[0].startswith("#!"):
        shebang = lines[0]
        i = 1
    enc_pat = re.compile(r"^#.*coding[:=]\s*([\-\w.]+)")
    if i < len(lines) and enc_pat.match(lines[i]):
        encoding = lines[i]
        i += 1

    # remove any existing future import
    lines = [l for l in lines if l.strip() != "from __future__ import annotations"]
    while lines and lines[0].strip() == "":
        lines.pop(0)

    new = []
    if shebang:
        new.append(shebang)
    if encoding:
        new.append(encoding)
    new.append("from __future__ import annotations")
    new.append("")
    new.extend(lines)
    return "\n".join(new) + ("\n" if text.endswith("\n") else "")

def _ensure_pg_qtcore_qtgui(text: str) -> str:
    lines = text.splitlines()
    pat = re.compile(r"^\s*from\s+pyqtgraph\.Qt\s+import\s+(.+)$")
    for idx, l in enumerate(lines):
        m = pat.match(l)
        if m:
            imports = [s.strip() for s in m.group(1).split(",") if s.strip()]
            if "QtCore" not in imports:
                imports.insert(0, "QtCore")
            if "QtGui" not in imports:
                imports.append("QtGui")
            seen = set()
            out = []
            for it in imports:
                if it not in seen:
                    seen.add(it); out.append(it)
            lines[idx] = "from pyqtgraph.Qt import " + ", ".join(out)
            return "\n".join(lines) + ("\n" if text.endswith("\n") else "")
    # insert after future import
    for idx, l in enumerate(lines):
        if l.strip() == "from __future__ import annotations":
            insert_at = idx + 2 if (idx + 1 < len(lines) and lines[idx+1].strip() == "") else idx + 1
            lines.insert(insert_at, "from pyqtgraph.Qt import QtCore, QtGui")
            lines.insert(insert_at + 1, "")
            return "\n".join(lines) + ("\n" if text.endswith("\n") else "")
    return "from pyqtgraph.Qt import QtCore, QtGui\n\n" + text

def main() -> None:
    if not TARGET.exists():
        raise SystemExit(f"[FIX][ERR] target not found: {TARGET}")
    orig = TARGET.read_text(encoding="utf-8")
    new = _ensure_pg_qtcore_qtgui(_fix_future_import(orig))
    if new == orig:
        print(f"[FIX] no changes needed: {TARGET}")
        return
    bak = TARGET.with_suffix(TARGET.suffix + ".bak")
    bak.write_text(orig, encoding="utf-8")
    TARGET.write_text(new, encoding="utf-8")
    print(f"[FIX] patched: {TARGET}")
    print(f"[FIX] backup : {bak}")

if __name__ == "__main__":
    main()
