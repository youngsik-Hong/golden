import os
import shutil

# ================================
# 설정
# ================================
PROJECT_ROOT = os.path.abspath(".")
TARGET_DIR = os.path.join(PROJECT_ROOT, "smtm")
QUARANTINE_DIR = os.path.join(PROJECT_ROOT, "quarantine")

KEYWORDS = ["FIXED", "STEP", "copy"]
EXPLICIT_FILES = {"Golden.py"}

# ================================
# 유틸
# ================================
def ensure_dir(path):
    if not os.path.exists(path):
        os.makedirs(path)

def move_to_quarantine(src_path):
    rel = os.path.relpath(src_path, PROJECT_ROOT)
    dst = os.path.join(QUARANTINE_DIR, rel)
    ensure_dir(os.path.dirname(dst))
    print(f"[MOVE] {rel}")
    shutil.move(src_path, dst)

# ================================
# 메인 로직
# ================================
def main():
    ensure_dir(QUARANTINE_DIR)

    for root, dirs, files in os.walk(TARGET_DIR, topdown=False):
        # 1) __pycache__ 디렉토리
        for d in dirs:
            if d == "__pycache__":
                full = os.path.join(root, d)
                move_to_quarantine(full)

        # 2) 파일 검사
        for f in files:
            full = os.path.join(root, f)

            # pyc
            if f.endswith(".pyc"):
                move_to_quarantine(full)
                continue

            # 키워드 기반
            if any(k in f for k in KEYWORDS):
                move_to_quarantine(full)
                continue

            # 명시적 파일
            if f in EXPLICIT_FILES:
                move_to_quarantine(full)
                continue

    print("\n[OK] Quarantine completed.")
    print(f"→ 격리 폴더: {QUARANTINE_DIR}")
    print("→ 테스트 후 필요한 파일은 다시 되돌리면 됩니다.")

if __name__ == "__main__":
    main()


# 실행 python quarantine_smtm.py
# 복원 mv quarantine/smtm/simulation_operator_FIXED.py smtm/
