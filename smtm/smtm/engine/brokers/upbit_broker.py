# -*- coding: utf-8 -*-
"""UpbitBroker (Gate 2D-2 scaffold)

목적
- Gate 2D-1의 SIMBroker 자리에 '실전 브로커'를 끼워 넣을 자리를 만든다.
- 키가 없으면 절대 동작하지 않으며, 키가 있어도 '발주'는 옵션으로만 동작하도록 설계(안전).

제공 기능(조회 중심)
- query_order(uuid/identifier) : Upbit /v1/order 로 조회 후 OrderManager 표준 dict로 변환
- place_limit(...)             : (옵션) UpbitTrader._send_order(..., identifier=client_oid) 사용

안전장치
- 기본값 allow_live_place=False : 발주를 막고, 조회만 가능
  (실발주를 하려면 환경변수 SMTM_ALLOW_LIVE_PLACE=1을 설정)
"""
from __future__ import annotations

import os
from typing import Any, Dict, Optional

from smtm.trader.upbit_trader import UpbitTrader


class UpbitBroker:
    def __init__(self) -> None:
        self.trader = UpbitTrader()
        self.allow_live_place = os.environ.get("SMTM_ALLOW_LIVE_PLACE") == "1"

    def query_order(self, uuid: Optional[str] = None, identifier: Optional[str] = None) -> Optional[Dict[str, Any]]:
        # UpbitTrader는 env 키가 없으면 내부 요청이 실패/None이 될 수 있음.
        try:
            return self.trader.reconcile_for_engine(client_oid=identifier or "", exchange_order_id=uuid)
        except Exception:
            return None

    def place_limit(self, market: str, side: str, price: float, volume: float, identifier: str) -> Dict[str, Any]:
        """실발주(옵션). identifier=client_oid를 멱등키로 전달."""
        if not self.allow_live_place:
            raise RuntimeError("LIVE_PLACE_DISABLED (set SMTM_ALLOW_LIVE_PLACE=1 to enable)")
        is_buy = (side.upper() == "BUY")
        req = {"price": float(price), "amount": float(volume), "client_oid": identifier, "identifier": identifier}
        # UpbitTrader._execute_order가 _send_order로 identifier를 전달하도록 Gate 2B-2에서 패치됨
        resp = self.trader._execute_order(is_buy=is_buy, request=req)  # type: ignore[attr-defined]
        # resp가 dict로 오며 uuid가 포함
        if isinstance(resp, dict) and (resp.get("uuid") or resp.get("id")):
            uuid = resp.get("uuid") or resp.get("id")
            return {"uuid": uuid, "identifier": identifier}
        # 실패 시 예외
        raise RuntimeError(f"UPBIT_PLACE_FAILED: {resp}")
