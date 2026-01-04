# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional
import time
import uuid
import hashlib
import json


def now_ts_str() -> str:
    t = time.time()
    lt = time.localtime(t)
    ms = int((t - int(t)) * 1000)
    return time.strftime("%Y-%m-%d %H:%M:%S", lt) + f".{ms:03d}"


def make_run_id() -> str:
    lt = time.localtime()
    return "live-" + time.strftime("%Y%m%d", lt) + "-" + uuid.uuid4().hex[:3]


def params_hash(params: Dict[str, Any]) -> str:
    try:
        s = json.dumps(params, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    except Exception:
        s = str(params)
    h = hashlib.sha1(s.encode("utf-8")).hexdigest()[:12]
    return "sha1:" + h


@dataclass
class EngineState:
    run_id: str = field(default_factory=make_run_id)
    symbol: str = "BTC-KRW"
    tf: str = "1m"

    armed: bool = False
    killed: bool = False
    block_orders: bool = True  # 3단계: 관측 전용

    strategy_id: str = "NONE"
    profile: str = "SAFE"
    config_version: int = 0
    params: Dict[str, Any] = field(default_factory=dict)
    params_hash: str = "sha1:000000000000"

    last_price: Optional[float] = None
    last_tick_ts: Optional[str] = None

    evt_seq: int = 0
    started_ts: str = field(default_factory=now_ts_str)
    started_epoch: float = field(default_factory=time.time)

    def bump_seq(self) -> int:
        self.evt_seq += 1
        return self.evt_seq
