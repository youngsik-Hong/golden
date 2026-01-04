import os
import shutil
import json
from datetime import datetime

PROJECT_ROOT = os.path.abspath(".")
QUARANTINE_DIR = os.path.join(PROJECT_ROOT, "_quarantine")

# 보호할 경로 (상대경로 기준)
WHITELIST_DIRS = [
    "smtm/app",
    "smtm/ui",
    "smtm/controller",
    "smtm/strategy",
    "smtm/domain",
    "smtm/core",
    "smtm/infra",
    "smtm/data",
]

WHITELIST_FILES = [
    "smtm/__main__.py",
    "smtm/config.py",
    "smtm/log_manager.py",
    "smtm/date_converter.py",
]

WHITELIST_EXT = [".ui", ".qss", ".png", ".jpg", ".ico"]

manifest = {
    "created_at": datetime.now().isoformat(),
    "moved": []
}

def is_whitelisted(path: str) -> bool:
    rel = os.path.relpath(path, PROJECT_ROOT)

    # 디렉토리 화이트리스트
    for d in WHITELIST_DIRS:
        if rel.startswith(d):
            return True

    # 파일 화이트리스트
    for f in WHITELIST_FILES:
        if rel == f:
            return True

    # 확장자 화이트리스트
    for ext in WHITELIST_EXT:
        if rel.lower().endswith(ext):
            return True

    return False

def ensure_quarantine():
    os.makedirs(QUARANTINE_DIR, exist_ok=True)

def move_to_quarantine(path: str):
    rel = os.path.relpath(path, PROJECT_ROOT)
    dest = os.path.join(QUARANTINE_DIR, rel)

    os.makedirs(os.path.dirname(dest), exist_ok=True)
    shutil.move(path, dest)

    manifest["moved"].append({
        "original": rel,
        "quarantine": os.path.relpath(dest, PROJECT_ROOT)
    })

def main():
    ensure_quarantine()

    for root, dirs, files in os.walk(PROJECT_ROOT, topdown=True):
        # quarantine 내부는 무시
        if root.startswith(QUARANTINE_DIR):
            continue

        # dirs 수정 (walk 중단 방지)
        dirs[:] = [
            d for d in dirs
            if is_whitelisted(os.path.join(root, d))
        ]

        for f in files:
            full = os.path.join(root, f)
            if not is_whitelisted(full):
                move_to_quarantine(full)

    # manifest 저장
    with open(os.path.join(QUARANTINE_DIR, "manifest.json"), "w", encoding="utf-8") as fw:
        json.dump(manifest, fw, indent=2, ensure_ascii=False)

    print(f"[OK] Quarantine completed. Moved {len(manifest['moved'])} items.")

if __name__ == "__main__":
    main()
