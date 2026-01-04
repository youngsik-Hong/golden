# -*- coding: utf-8 -*-
"""Python 3.9에서 금지되는 타입힌트(PEP604 'X | None')가 남아있는지 점검.

사용:
cd C:\hys\smtm
python -m smtm.tools.verify_py39_typing

출력:
- 발견된 라인 번호와 내용(일부)을 출력
- 없으면 OK 출력
"""

from __future__ import annotations

import os
import re
import sys

TARGET = os.path.join(os.path.dirname(__file__), "..", "ui", "ui_tuning_simulator.py")
TARGET = os.path.abspath(TARGET)

PAT = re.compile(r"\b\w+\s*\|\s*None\b")

def main() -> int:
    if not os.path.exists(TARGET):
        print(f"[VERIFY][ERR] not found: {TARGET}")
        return 2

    with open(TARGET, "r", encoding="utf-8") as f:
        lines = f.readlines()

    hits = []
    for i, line in enumerate(lines, 1):
        if "| None" in line and PAT.search(line):
            hits.append((i, line.rstrip("\n")))

    print(f"[VERIFY] target={TARGET}")
    if not hits:
        print("[VERIFY] OK: no 'X | None' typing found (Py39 safe)")
        return 0

    print(f"[VERIFY][WARN] found {len(hits)} Py39-incompatible typing(s):")
    for i, s in hits[:50]:
        print(f"  L{i}: {s.strip()}")
    if len(hits) > 50:
        print(f"  ... and {len(hits)-50} more")

    print("\n수정 방법(권장): 'X | None' -> 'Optional[X]' 로 교체하고 Optional import 확인")
    return 1

if __name__ == "__main__":
    raise SystemExit(main())
