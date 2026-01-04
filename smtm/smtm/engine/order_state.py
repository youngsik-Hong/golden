# -*- coding: utf-8 -*-
"""Order State Machine (Gate 2C - Idempotency Preflight)

Gate 2A: timeout(EXPIRED)
Gate 2B: reconcile로 timeout 정정(FILLED/CANCELED)
Gate 2C: 중복 주문 방지(멱등성) - 같은 identifier/client_oid로는 '새 주문 생성/발주'를 허용하지 않는다.

핵심
- identifier(client_oid)는 엔진 내부에서 "주문 1개의 영구 키"로 취급한다.
- 동일 identifier로 요청이 다시 들어오면:
    * 기존 주문이 있으면 그대로 반환 (새 주문 생성 금지)
    * 상태가 terminal이면 정책에 따라 새 주문 허용/금지(기본: 금지)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Literal, Optional

OrderStatus = Literal[
    "REQUEST", "SENT", "ACK", "PARTIAL", "FILLED",
    "CANCELED", "REJECTED", "ERROR", "EXPIRED"
]
Side = Literal["BUY", "SELL"]
OrderType = Literal["LIMIT", "MARKET"]


@dataclass
class OrderPolicy:
    ack_timeout_ms: int = 2500
    fill_timeout_ms: int = 120000
    max_retry: int = 2
    enable_reconcile: bool = True

    # Gate 2C: 멱등성 정책
    # - True: 동일 identifier 주문이 '존재'하면 새 주문 생성/발주를 금지
    # - False: (비권장) 동일 identifier로 새 주문 생성 허용
    idempotent: bool = True

    # Gate 2C: terminal(FILLED/CANCELED/...) 이후 같은 identifier 재사용 허용 여부
    allow_reuse_after_terminal: bool = False


@dataclass
class OrderState:
    client_oid: str               # identifier(멱등키)
    symbol: str
    side: Side
    order_type: OrderType
    price: float
    qty: float

    status: OrderStatus = "REQUEST"
    exchange_order_id: Optional[str] = None  # Upbit uuid 등

    filled_qty: float = 0.0
    avg_fill_price: Optional[float] = None
    fee: float = 0.0

    reason: Optional[str] = None
    retry_count: int = 0

    requested_at: str = ""
    sent_at: Optional[str] = None
    ack_at: Optional[str] = None
    done_at: Optional[str] = None
    last_update_ts: str = ""

    sent_ms: Optional[int] = None
    ack_ms: Optional[int] = None
    last_fill_ms: Optional[int] = None

    policy: OrderPolicy = field(default_factory=OrderPolicy)
    raw_last: Optional[Dict[str, Any]] = None
