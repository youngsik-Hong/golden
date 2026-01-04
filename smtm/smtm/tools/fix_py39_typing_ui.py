# -*- coding: utf-8 -*-
"""ui_tuning_simulator.py 안의 Py39 비호환 타입힌트(PEP604 'X | None')를 정식으로 교체."""

from __future__ import annotations

import os
import re

TARGET = os.path.join(os.path.dirname(__file__), "..", "ui", "ui_tuning_simulator.py")
TARGET = os.path.abspath(TARGET)

REPLS = [
    (re.compile(r"(def\s+_latest\(paths:\s*list\[str\]\)\s*->)\s*str\s*\|\s*None\s*:"), r"\1 Optional[str]:"),
    (re.compile(r"(def\s+_line\(label:\s*str,\s*p:)\s*str\s*\|\s*None(\)\s*->\s*str\s*:)"), r"\1 Optional[str]\2"),
    (re.compile(r":\s*str\s*\|\s*None\b"), r": Optional[str]"),
    (re.compile(r"->\s*str\s*\|\s*None\b"), r"-> Optional[str]"),
]

def _ensure_optional_import(lines):
    joined = "".join(lines)
    if re.search(r"\bfrom\s+typing\s+import\s+.*\bOptional\b", joined):
        return lines

    insert_at = None
    for i, line in enumerate(lines):
        if line.startswith("from typing import"):
            insert_at = i + 1
            break
    if insert_at is None:
        for i, line in enumerate(lines):
            if line.strip() == "" and i > 0:
                insert_at = i
                break
    if insert_at is None:
        insert_at = 0

    lines.insert(insert_at, "from typing import Optional\n")
    return lines

def main():
    if not os.path.exists(TARGET):
        print(f"[FIX][ERR] not found: {TARGET}")
        return 2

    with open(TARGET, "r", encoding="utf-8") as f:
        lines = f.readlines()

    original = "".join(lines)
    lines = _ensure_optional_import(lines)
    text = "".join(lines)

    changed = False
    for pat, repl in REPLS:
        new_text, n = pat.subn(repl, text)
        if n:
            changed = True
            text = new_text

    if not changed and text == original:
        print("[FIX] nothing to change")
        return 0

    with open(TARGET, "w", encoding="utf-8") as f:
        f.write(text)

    print(f"[FIX] patched: {TARGET}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
