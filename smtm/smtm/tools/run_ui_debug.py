# -*- coding: utf-8 -*-
"""UI가 '창이 안 뜨고' 조용히 종료/정지되는 경우 원인 출력용 디버그 런처.

사용:
cd C:\hys\smtm
python -m smtm.tools.run_ui_debug

동작:
- smtm.ui.ui_tuning_simulator 를 import 한 뒤,
  1) main() 이 있으면 main() 호출
  2) 없으면 run() 이 있으면 run() 호출
  3) 둘 다 없으면, TuningMainWindow가 있으면 QApplication 생성 후 show()
- 최상위 예외를 모두 잡아서 traceback을 콘솔에 출력
"""

from __future__ import annotations

import sys
import traceback

def main() -> None:
    try:
        import smtm.ui.ui_tuning_simulator as ui
        print(f"[DBG] ui_tuning_simulator={ui.__file__}")

        if hasattr(ui, "main"):
            ui.main()
            return
        if hasattr(ui, "run"):
            ui.run()
            return

        # 마지막 수단: 클래스 기반으로 직접 띄우기
        if hasattr(ui, "TuningMainWindow"):
            from PyQt6.QtWidgets import QApplication
            app = QApplication(sys.argv)
            w = ui.TuningMainWindow()
            w.show()
            sys.exit(app.exec())
            return

        raise RuntimeError("ui_tuning_simulator에 실행 진입점(main/run) 또는 TuningMainWindow가 없습니다.")

    except SystemExit:
        raise
    except Exception as e:
        print(f"[DBG][FATAL] 예외: {e}")
        print(traceback.format_exc())
        try:
            input("엔터를 누르면 종료합니다...")
        except Exception:
            pass
        raise SystemExit(2)

if __name__ == "__main__":
    main()
