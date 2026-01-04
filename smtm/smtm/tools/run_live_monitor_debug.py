# -*- coding: utf-8 -*-
"""실전 모니터가 바로 꺼질 때 원인을 콘솔에 남기기 위한 디버그 실행기.

사용:
cd C:\hys\smtm
python -m smtm.tools.run_live_monitor_debug

설명:
- live_monitor_ipc를 import 후 main()을 호출합니다.
- 최상위 예외를 잡아 traceback을 출력하므로 '창이 꺼져서 원인을 못 보는' 문제를 줄입니다.
"""

from __future__ import annotations

import traceback

def main() -> None:
    try:
        import smtm.ui.live_monitor_ipc as lm
        print(f"[DBG] live_monitor_ipc={lm.__file__}")
        if hasattr(lm, "main"):
            lm.main()
        else:
            raise RuntimeError("live_monitor_ipc에 main()이 없습니다.")
    except SystemExit:
        raise
    except Exception as e:
        print(f"[DBG][FATAL] 예외: {e}")
        print(traceback.format_exc())
        # 창이 바로 닫히는 경우를 줄이기 위해 입력 대기(원치 않으면 지우세요)
        try:
            input("엔터를 누르면 종료합니다...")
        except Exception:
            pass
        raise SystemExit(2)

if __name__ == "__main__":
    main()
