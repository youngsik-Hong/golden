# -*- coding: utf-8 -*-
from __future__ import annotations

"""smtm.engine.handlers

핵심 목표(현 단계):
- CMD 요청을 안전하게 라우팅하고(주문/비주문 분리)
- SNAPSHOT.GET은 payload 검증에 걸리지 않도록 우선 처리
- Python 3.9 호환 (typing | union 미사용)
"""

import time
from typing import Any, Dict, Optional, Tuple

from .state import EngineState, now_ts_str, params_hash
from .order_state import OrderPolicy


def ack(
    req: Dict[str, Any],
    state: EngineState,
    ok: bool = True,
    payload: Optional[Dict[str, Any]] = None,
    error: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    if payload is None:
        payload = {}
    return {
        "v": 1,
        "type": "ACK",
        "ts": now_ts_str(),
        "req_id": req.get("req_id"),
        "run_id": state.run_id,
        "ok": bool(ok),
        "error": error,
        "payload": payload,
    }


def status_payload(state: EngineState) -> Dict[str, Any]:
    return {
        "engine": {"run_id": state.run_id, "started_ts": state.started_ts},
        "mode": {"armed": state.armed, "killed": state.killed, "block_orders": state.block_orders},
        "active": {"symbol": state.symbol, "tf": state.tf, "strategy": state.strategy_id, "profile": state.profile},
        "versions": {"config_version": state.config_version, "params_hash": state.params_hash},
        "market": {"last_price": state.last_price, "last_tick_ts": state.last_tick_ts},
        "health": {"feed": "OK", "latency_ms": 0, "evt_backlog": 0},
    }


def handle_command(
    req: Dict[str, Any],
    state: EngineState,
    services: Optional[Dict[str, Any]] = None,
) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]]]:
    """returns: (ack_message, event_to_broadcast_or_none)"""

    t = str(req.get("type") or "").strip().upper()
    payload = req.get("payload") or {}

    # ---- SNAPSHOT: always before any validation ----
    if t == "SNAPSHOT.GET":
        tf = str(payload.get("tf") or getattr(state, "tf", "1m"))
        try:
            limit = int(payload.get("limit", 120))
        except Exception:
            limit = 120
        snap = _build_snapshot(state, tf=tf, limit=limit, services=services)
        # 과거 형태 호환: payload 안에 snapshot 키로 감싸서 반환
        return ack(req, state, True, {"snapshot": snap}), None

    # ---- lightweight commands (no ARM required) ----
    if t == "PING":
        return ack(req, state, True, {"pong": True}), None

    if t == "ENGINE.STATUS":
        return ack(req, state, True, status_payload(state)), None

    if t in ("LIVE.UNBLOCK", "ORDERS.UNBLOCK"):
        state.block_orders = False
        return ack(req, state, True, {"block_orders": state.block_orders}), None

    # ---- ARM / DISARM / KILL ----
    if t == "LIVE.ARM":
        if state.killed:
            return ack(req, state, False, error={"code": "ENGINE_KILLED", "message": "KILL 상태에서는 ARM 불가"}), None
        state.armed = True
        state.block_orders = False
        return ack(req, state, True, {"armed": True, "block_orders": state.block_orders}), None

    if t == "LIVE.DISARM":
        state.armed = False
        return ack(req, state, True, {"armed": False}), None

    if t == "KILL.SWITCH":
        state.killed = True
        state.armed = False
        state.block_orders = True
        return ack(req, state, True, {"killed": True, "block_orders": True}), None

    if t == "EVENT.SUBSCRIBE":
        return ack(req, state, True, {"subscribed": True}), None

    if t == "CONFIG.APPLY":
        if state.killed:
            return ack(req, state, False, error={"code": "ENGINE_KILLED", "message": "KILL 상태에서는 설정 적용 불가"}), None
        if state.armed:
            return ack(req, state, False, error={"code": "ENGINE_ARMED", "message": "ARM 상태에서는 설정 적용 불가 (DISARM 필요)"}), None

        state.symbol = payload.get("symbol", state.symbol)
        state.tf = payload.get("tf", state.tf)
        state.strategy_id = payload.get("strategy_id", state.strategy_id)
        state.profile = payload.get("profile", state.profile)
        state.params = payload.get("params", {}) or {}
        state.params_hash = params_hash(state.params)
        state.config_version += 1

        evt = {
            "v": 1,
            "type": "CONFIG.UPDATED",
            "ts": now_ts_str(),
            "run_id": state.run_id,
            "symbol": state.symbol,
            "seq": state.bump_seq(),
            "payload": {
                "config_version": state.config_version,
                "strategy_id": state.strategy_id,
                "profile": state.profile,
                "symbol": state.symbol,
                "params": state.params,
                "params_hash": state.params_hash,
            },
        }
        return ack(req, state, True, {"config_version": state.config_version, "params_hash": state.params_hash}), evt

    # ---- below: requires ARM for trading-related actions ----
    if not state.armed:
        return ack(req, state, False, error={"code": "ENGINE_NOT_ARMED", "message": "ARM 필요 (LIVE.ARM 실행)"}), None

    # ---- order commands are blocked only for ORDER.* ----
    if state.block_orders and t.startswith("ORDER."):
        return ack(req, state, False, error={"code": "ENGINE_BLOCKED", "message": "주문 차단(block_orders) 상태"}), None

    # ---- ORDER.PLACE.LIMIT ----
    if t == "ORDER.PLACE.LIMIT":
        if state.killed:
            return ack(req, state, False, error={"code": "ENGINE_KILLED", "message": "KILL 상태: 주문 불가"}), None

        if services is None or services.get("orders") is None:
            return ack(req, state, False, error={"code": "ENGINE_NO_ORDERS", "message": "OrderManager 미연결(services['orders'] 필요)"}), None
        orders = services["orders"]

        symbol = str(payload.get("symbol") or state.symbol)
        side = str(payload.get("side") or "").upper().strip()
        if side not in ("BUY", "SELL"):
            return ack(req, state, False, error={"code": "INVALID_PAYLOAD", "message": "side는 BUY/SELL"}), None

        try:
            price = float(payload.get("price"))
            qty = float(payload.get("qty"))
        except Exception:
            return ack(req, state, False, error={"code": "INVALID_PAYLOAD", "message": "price/qty 숫자 필요"}), None

        if price <= 0 or qty <= 0:
            return ack(req, state, False, error={"code": "INVALID_PAYLOAD", "message": "price/qty는 0보다 커야 함"}), None

        client_oid = payload.get("client_oid")
        client_oid = str(client_oid).strip() if client_oid else None

        # policy (선택)
        policy = OrderPolicy()
        pol_in = payload.get("policy") or {}
        if isinstance(pol_in, dict):
            if "ack_timeout_ms" in pol_in:
                try:
                    policy.ack_timeout_ms = int(pol_in["ack_timeout_ms"])
                except Exception:
                    pass
            if "fill_timeout_ms" in pol_in:
                try:
                    policy.fill_timeout_ms = int(pol_in["fill_timeout_ms"])
                except Exception:
                    pass
            if "enable_reconcile" in pol_in:
                policy.enable_reconcile = bool(pol_in["enable_reconcile"])
            if "idempotent" in pol_in:
                policy.idempotent = bool(pol_in["idempotent"])
            if "allow_reuse_after_terminal" in pol_in:
                policy.allow_reuse_after_terminal = bool(pol_in["allow_reuse_after_terminal"])

        existed = bool(client_oid and client_oid in getattr(orders, "orders", {}))

        try:
            if client_oid:
                order_payload = {
                    "client_oid": client_oid,
                    "symbol": symbol,
                    "side": side,
                    "order_type": "LIMIT",
                    "price": float(price),
                    "qty": float(qty),
                }
                o = orders.ensure_order(order_payload, reason="ui_place_limit", policy=policy)

            else:
                o = orders.create_order(
                    symbol, side, "LIMIT", price, qty,
                    reason="ui_place_limit", policy=policy
                )
                client_oid = o.client_oid
        except Exception as e:
            return ack(req, state, False, error={"code": "ORDER_CREATE_FAILED", "message": str(e)}), None

        now_ms = int(time.time() * 1000)
        try:
            send_ready = bool(orders.request_send(client_oid, now_ms))
        except Exception:
            send_ready = False

        return ack(req, state, True, payload={
            "accepted": (not existed),
            "duplicate": existed,
            "send_ready": send_ready,
            "client_oid": client_oid,
            "symbol": symbol,
            "side": side,
            "price": float(price),
            "qty": float(qty),
            "status": getattr(o, "status", None),
        }), None

    return ack(req, state, False, error={"code": "UNKNOWN_CMD", "message": f"알 수 없는 명령: {t}"}), None


def _build_snapshot(
    state: EngineState,
    tf: str,
    limit: int,
    services: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """최소 스냅샷 (현 단계: 더미 캔들 + 주문 요약)"""
    # candles: state에 과거 캔들이 없으면 더미 생성
    candles = []
    base = float(state.last_price or 1500000.0)
    now = int(time.time())
    t0 = now - (now % 60)
    limit_i = max(0, int(limit))
    for i in range(limit_i):
        t = t0 - (limit_i - 1 - i) * 60
        price = base + (i % 7 - 3) * 50.0
        candles.append({"t": t, "o": price - 20, "h": price + 30, "l": price - 35, "c": price, "v": 1.0})

    orders_list = []
    active = 0
    try:
        if services and services.get("orders") is not None:
            om = services["orders"]
            for oid, o in getattr(om, "orders", {}).items():
                status = getattr(o, "status", None)
                orders_list.append({
                    "client_oid": oid,
                    "symbol": getattr(o, "symbol", None),
                    "side": getattr(o, "side", None),
                    "price": getattr(o, "price", None),
                    "qty": getattr(o, "qty", None),
                    "status": status,
                })
                if status not in ("FILLED", "CANCELED", "EXPIRED", "REJECTED"):
                    active += 1
    except Exception:
        orders_list = []
        active = 0

    return {
        "tf": tf,
        "limit": limit_i,
        "candles": candles,
        "orders": orders_list,
        "active": active,
        "market": {"last_price": state.last_price, "last_tick_ts": state.last_tick_ts},
        "mode": {"armed": state.armed, "killed": state.killed, "block_orders": state.block_orders},
    }
