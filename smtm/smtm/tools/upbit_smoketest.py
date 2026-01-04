# -*- coding: utf-8 -*-
"""Upbit reconcile smoke test (read-only)

사용 예)
  # uuid로 조회
  python -m smtm.tools.upbit_smoketest --uuid 1234-...

  # identifier로 조회 (engine client_oid를 넣는 용도)
  python -m smtm.tools.upbit_smoketest --identifier cli-live-...

필요한 환경변수
  UPBIT_OPEN_API_ACCESS_KEY
  UPBIT_OPEN_API_SECRET_KEY
  UPBIT_OPEN_API_SERVER_URL   (보통 https://api.upbit.com)

출력
  - 원본 Upbit /v1/order 응답(dict) 일부
  - 엔진 reconcile 표준 dict(reconcile_for_engine) 변환 결과
"""

from __future__ import annotations

import argparse
import os
import json
import sys

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--uuid", default=None, help="Upbit order uuid")
    ap.add_argument("--identifier", default=None, help="Upbit order identifier (client_oid)")
    args = ap.parse_args()

    if not args.uuid and not args.identifier:
        print("ERROR: --uuid 또는 --identifier 중 하나는 필요합니다.", file=sys.stderr)
        return 2

    ak = os.environ.get("UPBIT_OPEN_API_ACCESS_KEY")
    sk = os.environ.get("UPBIT_OPEN_API_SECRET_KEY")
    url = os.environ.get("UPBIT_OPEN_API_SERVER_URL") or "https://api.upbit.com"
    if not (ak and sk):
        print("ERROR: UPBIT_OPEN_API_ACCESS_KEY / UPBIT_OPEN_API_SECRET_KEY 환경변수가 필요합니다.", file=sys.stderr)
        return 2
    os.environ["UPBIT_OPEN_API_SERVER_URL"] = url

    from smtm.trader.upbit_trader import UpbitTrader

    t = UpbitTrader()  # 내부에서 env 사용
    raw = t.get_order(request_uuid=args.uuid, identifier=args.identifier)
    print("=== RAW /v1/order ===")
    print(json.dumps(raw, ensure_ascii=False, indent=2)[:4000])

    rec = t.reconcile_for_engine(client_oid=args.identifier or "", exchange_order_id=args.uuid)
    print("\n=== reconcile_for_engine ===")
    print(json.dumps(rec, ensure_ascii=False, indent=2))

    return 0

if __name__ == "__main__":
    raise SystemExit(main())
