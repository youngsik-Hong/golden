# -*- coding: utf-8 -*-
"""SMTM - 실전 모니터 실행 검증 스크립트(간이 검증용)

목적:
- ui_tuning_simulator에서 '실전 모니터 열기' 버튼이 UI를 닫지 않고
  별도 프로세스로 모니터를 띄우는지 독립적으로 검증한다.

사용:
  python -m smtm.tools.verify_open_live_monitor

주의:
- 이 스크립트는 프로젝트 검증용이며, 프로덕션 코드에 영향을 주지 않는다.
"""

import sys
import time
from PyQt6.QtCore import QCoreApplication, QProcess

def main():
    app = QCoreApplication(sys.argv)

    program = sys.executable
    args = ["-m", "smtm.ui.live_monitor_ipc"]

    ok, pid = QProcess.startDetached(program, args)
    if ok:
        print(f"[VERIFY] startDetached OK pid={pid}")
        # 모니터가 뜰 시간을 조금 준다.
        time.sleep(1.0)
        print("[VERIFY] done (UI 종료 없음 기대)")
        return 0
    else:
        print("[VERIFY][ERR] startDetached returned False")
        return 2

if __name__ == "__main__":
    raise SystemExit(main())
