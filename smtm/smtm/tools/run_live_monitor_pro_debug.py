
# -*- coding: utf-8 -*-
"""실전 모니터 PRO 디버그 런처(예외 traceback 출력)

사용:
  cd C:\hys\smtm
  python -m smtm.tools.run_live_monitor_pro_debug
"""

from __future__ import annotations

import traceback

def main() -> None:
    try:
        import smtm.ui.live_monitor_pro as m
        print(f"[DBG] live_monitor_pro={m.__file__}")
        m.main()
    except SystemExit:
        raise
    except Exception as e:
        print(f"[DBG][FATAL] {e}")
        print(traceback.format_exc())
        try:
            input("엔터를 누르면 종료합니다...")
        except Exception:
            pass
        raise SystemExit(2)

if __name__ == "__main__":
    main()
