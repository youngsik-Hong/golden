# -*- coding: utf-8 -*-
"""Trading Bridge (Gate 2D-2)

변경점
- SIMBroker를 기본으로 유지
- 환경변수가 준비된 경우에만 UpbitBroker를 선택할 수 있는 '팩토리'를 추가
  (실발주 기본 비활성)

선택 로직
- UPBIT_OPEN_API_ACCESS_KEY / UPBIT_OPEN_API_SECRET_KEY 가 설정되어 있으면 UpbitBroker 사용
- 아니면 SIMBroker 사용
"""
from __future__ import annotations

import os
from typing import Any, Dict, Optional

from dataclasses import dataclass


@dataclass
class BrokerOrder:
    uuid: str
    identifier: str
    state: str  # wait|done|cancel
    executed_volume: float = 0.0
    remaining_volume: float = 0.0
    avg_price: float = 0.0
    paid_fee: float = 0.0


class SIMBroker:
    """키 없이 검증용 브로커. identifier로 멱등 동작."""

    def __init__(self) -> None:
        import time
        self._time = time
        self._db_by_uuid: Dict[str, BrokerOrder] = {}
        self._db_by_identifier: Dict[str, BrokerOrder] = {}
        self._seq = 0

    def place_limit(self, market: str, side: str, price: float, volume: float, identifier: str,
                    scenario: str = "OK") -> BrokerOrder:
        if identifier in self._db_by_identifier:
            return self._db_by_identifier[identifier]
        self._seq += 1
        uuid = f"sim-{int(self._time.time())}-{self._seq:06d}"
        o = BrokerOrder(uuid=uuid, identifier=identifier, state="wait",
                       executed_volume=0.0, remaining_volume=float(volume),
                       avg_price=float(price), paid_fee=0.0)
        if scenario == "OK":
            o.state = "done"
            o.executed_volume = float(volume)
            o.remaining_volume = 0.0
        elif scenario == "CANCEL":
            o.state = "cancel"
        elif scenario in ("ACK_TIMEOUT_DONE", "FILL_TIMEOUT_CANCEL"):
            o.state = "wait"
        self._db_by_uuid[uuid] = o
        self._db_by_identifier[identifier] = o
        return o

    def query_order(self, uuid: Optional[str] = None, identifier: Optional[str] = None) -> Optional[Dict[str, Any]]:
        o = None
        if uuid:
            o = self._db_by_uuid.get(uuid)
        if o is None and identifier:
            o = self._db_by_identifier.get(identifier)
        if o is None:
            return None
        return {
            "exchange_order_id": o.uuid,
            "state": o.state,
            "executed_volume": o.executed_volume,
            "remaining_volume": o.remaining_volume,
            "avg_price": o.avg_price,
            "paid_fee": o.paid_fee,
        }

    def force_state(self, identifier: str, new_state: str, executed: Optional[float] = None) -> None:
        o = self._db_by_identifier.get(identifier)
        if not o:
            return
        o.state = new_state
        if executed is not None:
            o.executed_volume = float(executed)
            o.remaining_volume = max(0.0, o.remaining_volume - o.executed_volume)
        if new_state == "done":
            o.remaining_volume = 0.0


def make_broker() -> Any:
    ak = os.environ.get("UPBIT_OPEN_API_ACCESS_KEY")
    sk = os.environ.get("UPBIT_OPEN_API_SECRET_KEY")
    if ak and sk:
        try:
            from smtm.engine.brokers.upbit_broker import UpbitBroker
            return UpbitBroker()
        except Exception:
            # 키가 있어도 초기화 실패하면 SIM으로 폴백
            return SIMBroker()
    return SIMBroker()


class TradingBridge:
    """엔진에서 호출하는 단일 진입점."""

    def __init__(self, broker: Any) -> None:
        self.broker = broker

    def place_limit(self, market: str, side: str, price: float, volume: float, identifier: str,
                    scenario: str = "OK") -> Dict[str, Any]:
        # SIMBroker는 scenario를 받지만 UpbitBroker는 안 받는다.
        if hasattr(self.broker, "place_limit"):
            try:
                o = self.broker.place_limit(market, side, price, volume, identifier=identifier, scenario=scenario)  # type: ignore
                return {"uuid": getattr(o, "uuid", None) or o.get("uuid"), "identifier": identifier}  # type: ignore
            except TypeError:
                o = self.broker.place_limit(market, side, price, volume, identifier=identifier)  # type: ignore
                if isinstance(o, dict):
                    return o
                return {"uuid": getattr(o, "uuid", None), "identifier": identifier}
        raise RuntimeError("broker has no place_limit")

    def query_order(self, uuid: Optional[str] = None, identifier: Optional[str] = None) -> Optional[Dict[str, Any]]:
        if hasattr(self.broker, "query_order"):
            return self.broker.query_order(uuid=uuid, identifier=identifier)  # type: ignore
        return None
