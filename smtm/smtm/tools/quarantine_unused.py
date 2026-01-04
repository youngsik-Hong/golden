import os
import shutil
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
QUARANTINE_ROOT = PROJECT_ROOT / "_quarantine"

# 격리 폴더 구조
CATEGORIES = {
    "legacy": [
        "*_v1*.py",
        "*_v2*.py",
        "*_v15*.py",
        "*old*.py",
        "*legacy*.py",
    ],
    "duplicate": [
        "*_copy.py",
        "*_backup.py",
        "*_dup.py",
    ],
    "experimental": [
        "*test*.py",
        "*temp*.py",
        "*debug*.py",
    ],
    "backup": [
        "*.bak",
        "*.old",
        "*.orig",
    ],
}

# 절대 이동 금지 (화이트리스트)
PROTECT_KEYWORDS = [
    "BBI_V3_Spec_V16",
    "operator",
    "worker",
    "simulation",
    "virtual_market",
    "analyzer",
    "data_repository",
    "graph",
    "config",
]

def is_protected(path: Path) -> bool:
    name = path.name.lower()
    return any(k.lower() in name for k in PROTECT_KEYWORDS)

def main():
    print("=== SMTM Quarantine Start ===")

    QUARANTINE_ROOT.mkdir(exist_ok=True)

    moved = 0

    for category, patterns in CATEGORIES.items():
        target_dir = QUARANTINE_ROOT / category
        target_dir.mkdir(parents=True, exist_ok=True)

        for pattern in patterns:
            for file in PROJECT_ROOT.rglob(pattern):
                if not file.is_file():
                    continue
                if "_quarantine" in file.parts:
                    continue
                if is_protected(file):
                    continue

                dest = target_dir / file.name
                print(f"[MOVE] {file} -> {dest}")
                shutil.move(str(file), str(dest))
                moved += 1

    print(f"\n=== DONE: {moved} files quarantined ===")
    print("If something breaks, restore from _quarantine/")

if __name__ == "__main__":
    main()
  # 실행파일  cd smtm python tools/quarantine_unused.py

