# -*- coding: utf-8 -*-
"""smtm.engine.order_manager

Gate 2E 단계에서 엔진이 최소한으로 '주문 수락/중복 차단/스냅샷 표시'를 할 수 있도록
in-memory OrderManager를 제공합니다.

- 외부 브로커(UpbitBroker 등) 연결 전 단계: place_limit()는 '요청 수락'까지만 수행
- idempotency: client_oid 기준 중복 요청은 duplicate=True로 응답하고, 기존 주문 상태를 유지
- snapshot: UI/CLI가 SNAPSHOT.GET로 확인할 수 있도록 orders/active를 제공

주의:
- 실전 매매 연결 시에는 실제 브로커/체결 이벤트에 맞춰 status 전이를 추가해야 합니다.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional, Tuple
import time


_ACTIVE_STATUSES = {"REQUEST", "SENT", "ACK", "PARTIAL"}
_DONE_STATUSES = {"FILLED", "CANCELED", "EXPIRED", "REJECTED", "ERROR"}


def _now_ms() -> int:
    return int(time.time() * 1000)


@dataclass
class Order:
    client_oid: str
    symbol: str
    side: str  # BUY/SELL
    price: float
    qty: float
    status: str = "REQUEST"
    created_ms: int = 0
    updated_ms: int = 0

    # 실브로커 연결 이후 사용 가능(현재는 optional로 둠)
    broker_uuid: Optional[str] = None
    message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        # snapshot에는 ms보다 사람이 보기 쉬운 값도 종종 쓰므로 필요시 확장
        return d


class OrderManager:
    """In-memory order manager (minimal, Gate 2E)."""

    def __init__(self, max_orders: int = 5000) -> None:
        self.max_orders = int(max_orders) if max_orders else 5000
        self._by_oid: Dict[str, Order] = {}
        self._order_seq: List[str] = []  # insertion order (oldest -> newest)

    # -------------------------
    # Query helpers
    # -------------------------
    def get(self, client_oid: str) -> Optional[Order]:
        return self._by_oid.get(client_oid)

    def list_orders(self, limit: int = 200) -> List[Dict[str, Any]]:
        limit = int(limit) if limit else 200
        oids = self._order_seq[-limit:]
        return [self._by_oid[oid].to_dict() for oid in oids if oid in self._by_oid]

    def active_count(self) -> int:
        return sum(1 for o in self._by_oid.values() if o.status in _ACTIVE_STATUSES)

    # -------------------------
    # Core actions
    # -------------------------
    def place_limit(self, payload: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
        """Accept a LIMIT order request.

        Returns (ok, payload_for_ack).
        """
        required = ["client_oid", "symbol", "side", "price", "qty"]
        for k in required:
            if k not in payload:
                return False, {"code": "INVALID_PAYLOAD", "message": f"{k} 필요"}

        client_oid = str(payload["client_oid"]).strip()
        symbol = str(payload["symbol"]).strip()
        side = str(payload["side"]).strip().upper()

        if side not in ("BUY", "SELL"):
            return False, {"code": "INVALID_PAYLOAD", "message": "side는 BUY/SELL"}

        try:
            price = float(payload["price"])
            qty = float(payload["qty"])
        except Exception:
            return False, {"code": "INVALID_PAYLOAD", "message": "price/qty 숫자 필요"}

        if price <= 0 or qty <= 0:
            return False, {"code": "INVALID_PAYLOAD", "message": "price/qty > 0"}

        # idempotency
        existing = self._by_oid.get(client_oid)
        if existing is not None:
            return True, {
                "accepted": True,
                "duplicate": True,
                "send_ready": existing.status in _ACTIVE_STATUSES,
                "client_oid": existing.client_oid,
                "symbol": existing.symbol,
                "side": existing.side,
                "price": existing.price,
                "qty": existing.qty,
                "status": existing.status,
            }

        now = _now_ms()
        order = Order(
            client_oid=client_oid,
            symbol=symbol,
            side=side,
            price=float(price),
            qty=float(qty),
            status="REQUEST",
            created_ms=now,
            updated_ms=now,
        )

        # store
        self._by_oid[client_oid] = order
        self._order_seq.append(client_oid)

        # trim oldest if too many
        if len(self._order_seq) > self.max_orders:
            drop = len(self._order_seq) - self.max_orders
            for _ in range(drop):
                old_oid = self._order_seq.pop(0)
                self._by_oid.pop(old_oid, None)

        return True, {
            "accepted": True,
            "duplicate": False,
            "send_ready": True,
            "client_oid": order.client_oid,
            "symbol": order.symbol,
            "side": order.side,
            "price": order.price,
            "qty": order.qty,
            "status": order.status,
        }

    # -------------------------
    # Status update (optional)
    # -------------------------
    def set_status(self, client_oid: str, status: str, message: Optional[str] = None, broker_uuid: Optional[str] = None) -> bool:
        o = self._by_oid.get(client_oid)
        if not o:
            return False
        o.status = str(status).upper()
        o.updated_ms = _now_ms()
        if message is not None:
            o.message = message
        if broker_uuid is not None:
            o.broker_uuid = broker_uuid
        return True
