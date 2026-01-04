import os
import re
import shutil
import sys


def _find_target() -> str:
    import smtm  # type: ignore
    base = os.path.dirname(os.path.abspath(smtm.__file__))
    return os.path.join(base, "ui", "live_monitor_pro.py")


def _patch_imports(src: str) -> tuple[str, bool]:
    """Return (new_src, changed)."""
    if "QtGui" in src and re.search(r"\bQtGui\b", src):
        # Still may be missing import, but usually indicates it's present.
        pass

    changed = False

    # 1) Common case: from pyqtgraph.Qt import QtCore, QtWidgets
    pat = re.compile(r"^(\s*from\s+pyqtgraph\.Qt\s+import\s+)(.+)$", re.M)
    m = pat.search(src)
    if m:
        prefix, names = m.group(1), m.group(2)
        # Normalize list
        parts = [p.strip() for p in names.split(',') if p.strip()]
        if "QtGui" not in parts:
            # Insert QtGui after QtCore if present else append
            if "QtCore" in parts:
                idx = parts.index("QtCore") + 1
                parts.insert(idx, "QtGui")
            else:
                parts.append("QtGui")
            newline = prefix + ", ".join(parts)
            src = src[:m.start()] + newline + src[m.end():]
            changed = True
            return src, changed

    # 2) Alternative: from PyQt5 import QtCore, QtWidgets (rare here)
    pat2 = re.compile(r"^(\s*from\s+PyQt5\s+import\s+)(.+)$", re.M)
    m2 = pat2.search(src)
    if m2:
        prefix, names = m2.group(1), m2.group(2)
        parts = [p.strip() for p in names.split(',') if p.strip()]
        if "QtGui" not in parts:
            if "QtCore" in parts:
                idx = parts.index("QtCore") + 1
                parts.insert(idx, "QtGui")
            else:
                parts.append("QtGui")
            newline = prefix + ", ".join(parts)
            src = src[:m2.start()] + newline + src[m2.end():]
            changed = True
            return src, changed

    # 3) Fallback: add a dedicated import near top if neither import style exists
    lines = src.splitlines(True)
    insert_at = 0
    # Skip shebang/encoding and module docstring
    i = 0
    if lines and lines[0].startswith("#!"):
        i = 1
    while i < len(lines) and (lines[i].strip().startswith("#") or lines[i].strip() == ""):
        i += 1
    # Very light docstring skip
    if i < len(lines) and lines[i].lstrip().startswith(('"""', "'''")):
        q = lines[i].lstrip()[:3]
        i += 1
        while i < len(lines) and q not in lines[i]:
            i += 1
        if i < len(lines):
            i += 1
    insert_at = i

    inject = "from pyqtgraph.Qt import QtGui\n"
    if inject not in src:
        lines.insert(insert_at, inject)
        src = "".join(lines)
        changed = True
    return src, changed


def main() -> int:
    target = _find_target()
    if not os.path.exists(target):
        print(f"[FIX][ERR] target not found: {target}")
        return 2

    with open(target, "r", encoding="utf-8") as f:
        src = f.read()

    new_src, changed = _patch_imports(src)
    if not changed:
        print(f"[FIX] no change needed: {target}")
        return 0

    bak = target + ".bak"
    shutil.copy2(target, bak)
    with open(target, "w", encoding="utf-8", newline="\n") as f:
        f.write(new_src)

    print(f"[FIX] patched: {target}")
    print(f"[FIX] backup : {bak}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
