# -*- coding: utf-8 -*-
"""UpbitTrader 미체결 조회 호출 경로 검증 도구(네트워크 호출 포함).

사용:
cd C:\hys\smtm
python -m smtm.tools.verify_open_orders

주의:
- 실제 Upbit API 호출이 발생합니다(키/URL 필요).
- 키가 없으면 BLOCK/ERR가 출력될 수 있습니다.
"""

from __future__ import annotations
import os, traceback

def main():
    try:
        from smtm.trader.upbit_trader import UpbitTrader
    except Exception as e:
        print(f"[VERIFY][ERR] UpbitTrader import 실패: {e}")
        print(traceback.format_exc())
        raise SystemExit(2)

    t = UpbitTrader()
    print("[VERIFY] trader=", t.__class__.__name__)

    # 환경변수/설정이 없으면 여기서 실패할 수 있음
    try:
        data = t._query_orders(state="wait")
        print("[VERIFY] _query_orders(wait) OK:", type(data), "items=", len(data) if isinstance(data, list) else "n/a")
    except Exception as e:
        print("[VERIFY][ERR] _query_orders(wait) failed:", e)

    try:
        data2 = t._query_order_list(state="wait")
        print("[VERIFY] _query_order_list(state=wait) OK:", type(data2), "items=", len(data2) if isinstance(data2, list) else "n/a")
    except Exception as e:
        print("[VERIFY][ERR] _query_order_list(state=wait) failed:", e)

if __name__ == "__main__":
    main()
