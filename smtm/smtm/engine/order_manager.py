# -*- coding: utf-8 -*-
"""
SMTM Engine OrderManager (IPC-safe, compat)

목표:
- handlers.py / IPC 핸들러가 어떤 호출 스타일로 ensure_order를 불러도 죽지 않게 한다.
- payload는 최종적으로 dict가 되도록 정규화한다.
- reason은 옵션(str)이며 중복 전달( positional+keyword )로 크래시 나지 않게 한다.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional
import json


@dataclass
class Order:
    client_oid: str
    symbol: str
    side: str
    price: Optional[float] = None
    qty: Optional[float] = None
    type: str = "LIMIT"
    status: str = "NEW"
    created_ts: str = ""
    updated_ts: str = ""
    reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class OrderManager:
    def __init__(self, state: Optional[Dict[str, Any]] = None, broadcaster=None):
        # tolerate older call sites
        self.state: Dict[str, Any] = state if isinstance(state, dict) else {}
        self._broadcast = broadcaster if callable(broadcaster) else None

        self.state.setdefault("orders", [])
        self.state.setdefault("active", 0)

        # local index
        self._orders_by_oid: Dict[str, Dict[str, Any]] = {}
        self._orders: List[Dict[str, Any]] = []

    @property
    def active_count(self) -> int:
        try:
            return int(self.state.get("active", 0))
        except Exception:
            return 0

    def list_orders(self) -> List[Dict[str, Any]]:
        v = self.state.get("orders", [])
        return list(v) if isinstance(v, list) else []

    # ------------------------------------------------------------------
    # Internal implementation: expects payload dict (+ optional reason kw)
    # ------------------------------------------------------------------
    def _ensure_order_impl(self, payload: Dict[str, Any], *, reason: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        if not isinstance(payload, dict):
            raise TypeError("payload must be dict")

        client_oid = payload.get("client_oid") or payload.get("oid") or payload.get("id")
        if not client_oid:
            raise ValueError("missing client_oid")

        symbol = payload.get("symbol")
        side = payload.get("side")
        if not symbol or not side:
            raise ValueError("missing symbol/side")

        price = payload.get("price")
        qty = payload.get("qty") or payload.get("quantity")
        otype = payload.get("type") or payload.get("order_type") or payload.get("otype") or "LIMIT"

        now_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

        order = self._orders_by_oid.get(client_oid)
        if order is None:
            order = {
                "client_oid": client_oid,
                "symbol": symbol,
                "side": side,
                "type": otype,
                "price": price,
                "qty": qty,
                "status": "NEW",
                "created_ts": now_ts,
                "updated_ts": now_ts,
                "reason": reason,
            }
            self._orders_by_oid[client_oid] = order
            self._orders.append(order)
            # reflect to shared state for SNAPSHOT.GET
            self.state["orders"] = list(self._orders)
        else:
            order["updated_ts"] = now_ts
            if reason:
                order["reason"] = reason
            for k, v in (("price", price), ("qty", qty), ("type", otype), ("symbol", symbol), ("side", side)):
                if v is not None:
                    order[k] = v
            self.state["orders"] = list(self._orders)

        # active count: status NEW/REQUEST 등을 active로 보는 최소정책
        self.state["active"] = len(self._orders)

        if self._broadcast:
            try:
                self._broadcast("ORDER.LOCAL", {"order": order})
            except Exception:
                pass

        return order

    # ------------------------------------------------------------------
    # Public compat wrapper
    # ------------------------------------------------------------------
    def ensure_order(self, *args, **kwargs) -> Dict[str, Any]:
        """
        Compatibility wrapper.

        Accepts (legacy):
          - ensure_order(payload_dict)
          - ensure_order(payload_dict, reason_str)
          - ensure_order(reason_str, payload_dict)
          - ensure_order(payload=payload_dict, reason=reason_str)
          - ensure_order(cmd_str, payload_dict, reason=cmd_str)  # 중복 방지
          - JSON-string payload ( "{...}" )
        """
        payload = kwargs.pop("payload", None)
        reason = kwargs.pop("reason", None)

        # gather positional
        pos = list(args)

        def maybe_json_dict(x):
            if not isinstance(x, str):
                return None
            t = x.strip()
            if not t or not t.startswith("{"):
                return None
            # 1) JSON 먼저
            try:
                obj = json.loads(t)
                return obj if isinstance(obj, dict) else None
            except Exception:
                pass
            # 2) Python dict repr fallback: "{'a': 1}"
            try:
                import ast
                obj = ast.literal_eval(t)
                return obj if isinstance(obj, dict) else None
            except Exception:
                return None
        # payload from kw aliases
        if payload is None:
            for k in ("p", "data", "order", "req"):
                v = kwargs.get(k)
                if isinstance(v, dict):
                    payload = v
                    break
                j = maybe_json_dict(v)
                if isinstance(j, dict):
                    payload = j
                    break

        # swapped positional: (reason:str, payload:dict)
        if payload is not None and not isinstance(payload, dict) and isinstance(reason, dict):
            payload, reason = reason, payload

        # payload from positional
        if payload is None:
            for x in pos:
                if isinstance(x, dict):
                    payload = x
                    break
                j = maybe_json_dict(x)
                if isinstance(j, dict):
                    payload = j
                    break

        if not isinstance(payload, dict):
            raise TypeError("payload must be dict")

        # reason from positional non-json string, or kw aliases
        if not (isinstance(reason, str) and reason.strip()):
            reason = None
            for x in pos:
                if isinstance(x, str) and x.strip() and not x.strip().startswith("{"):
                    reason = x
                    break
            if reason is None:
                for k in ("cmd", "op", "name"):
                    v = kwargs.get(k)
                    if isinstance(v, str) and v.strip():
                        reason = v
                        break

        # IMPORTANT: reason은 keyword로만 전달해서 "multiple values for argument 'reason'" 방지
        if reason is not None:
            return self._ensure_order_impl(payload, reason=reason, **kwargs)
        return self._ensure_order_impl(payload, **kwargs)
