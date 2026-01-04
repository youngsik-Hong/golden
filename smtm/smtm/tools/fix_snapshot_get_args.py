# -*- coding: utf-8 -*-
"""Fix SNAPSHOT.GET early routing to pass required tf/limit to _build_snapshot.

Symptom:
- SNAPSHOT.GET -> ENGINE_EXCEPTION: _build_snapshot() missing 'tf' and 'limit'

Fix:
- Replace the inserted early branch (marker fix_handlers_snapshot_priority2)
  with a version that uses existing `payload` dict if present, else req.get('payload').

Inserted code:

    if req.get("type") == "SNAPSHOT.GET":
        p = req.get("payload") or {}
        tf = str(p.get("tf") or getattr(state, "tf", "1m"))
        limit_raw = p.get("limit", 120)
        try: limit = int(limit_raw)
        except: limit = 120
        return ack(req, state, True, payload=_build_snapshot(state, tf, limit)), None

Usage:
  python -m smtm.tools.fix_snapshot_get_args
"""
from __future__ import annotations

from pathlib import Path
import re


def main() -> int:
    import smtm.engine.handlers as h
    target = Path(h.__file__).resolve()
    txt = target.read_text(encoding="utf-8", errors="replace")

    if "fix_snapshot_get_args" in txt:
        print(f"[FIX] Marker already present in {target}. No change.")
        return 0

    # Find the previously inserted branch line and replace the whole block
    # We look for the marker comment from priority2
    m = re.search(r"^[ \t]*#\s*fix_handlers_snapshot_priority2:.*\n[ \t]*if\s+req\.get\(\"type\"\)\s*==\s*\"SNAPSHOT\.GET\"\:\n[ \t]*return\s+ack\(req,\s*state,\s*True,\s*payload=_build_snapshot\(state\)\),\s*None\n", txt, flags=re.M)
    if not m:
        # Try a looser match (in case of single quotes)
        m = re.search(r"^[ \t]*#\s*fix_handlers_snapshot_priority2:.*\n[ \t]*if\s+req\.get\([^)]*type[^)]*\)\s*==\s*['\"]SNAPSHOT\.GET['\"]\:\n[ \t]*return\s+ack\(req,\s*state,\s*True,\s*payload=_build_snapshot\(state\)\),\s*None\n", txt, flags=re.M)
    if not m:
        print(f"[FIX] Could not find old SNAPSHOT.GET early-branch to replace in {target}")
        return 2

    # Determine indent from the marker line
    indent = re.match(r"^(\s*)", m.group(0)).group(1)

    repl = (
        f"{indent}# fix_snapshot_get_args: SNAPSHOT.GET needs tf/limit\n"
        f"{indent}if req.get(\"type\") == \"SNAPSHOT.GET\":\n"
        f"{indent}    p = req.get(\"payload\") or {{}}\n"
        f"{indent}    tf = str(p.get(\"tf\") or getattr(state, \"tf\", \"1m\"))\n"
        f"{indent}    limit_raw = p.get(\"limit\", 120)\n"
        f"{indent}    try:\n"
        f"{indent}        limit = int(limit_raw)\n"
        f"{indent}    except Exception:\n"
        f"{indent}        limit = 120\n"
        f"{indent}    return ack(req, state, True, payload=_build_snapshot(state, tf, limit)), None\n"
    )

    out = txt[:m.start()] + repl + txt[m.end():]
    target.write_text(out, encoding="utf-8")
    print(f"[FIX] Updated SNAPSHOT.GET early routing to pass tf/limit in {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
