# -*- coding: utf-8 -*-
"""
SMTM Live Monitor (IPC 기반, 관측 전용)

- 엔진과 분리된 프로세스
- 시작 시퀀스: CMD 연결 → STATUS → SNAPSHOT → EVT 연결 → SUBSCRIBE
- 렌더링: 이벤트 버퍼링 후 10Hz 이하로 갱신

주의: 3단계 프로토타입은 '더미 데이터'로도 동작하도록 설계됨.
"""
from __future__ import annotations

import sys
from typing import Any, Dict, List, Optional

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QPlainTextEdit, QComboBox
)

import pyqtgraph as pg

from smtm.ipc.client import IpcClient


class StateStore:
    def __init__(self) -> None:
        self.run_id: str = ""
        self.symbol: str = "BTC-KRW"
        self.tf: str = "1m"
        self.armed: bool = False
        self.killed: bool = False
        self.config_version: int = 0
        self.strategy_id: str = "NONE"
        self.profile: str = "SAFE"
        self.params_hash: str = "sha1:000000000000"
        self.last_price: Optional[float] = None
        self.candles: List[Dict[str, Any]] = []  # items [{t,o,h,l,c,v}, ...]
        self.rsi14: Optional[float] = None

    def apply_snapshot(self, snap: Dict[str, Any]) -> None:
        self.run_id = snap.get("run_id") or self.run_id
        self.symbol = snap.get("symbol") or self.symbol
        self.tf = snap.get("tf") or self.tf

        cfg = snap.get("config") or {}
        self.strategy_id = cfg.get("strategy_id", self.strategy_id)
        self.profile = cfg.get("profile", self.profile)
        self.config_version = int(cfg.get("config_version", self.config_version) or 0)
        self.params_hash = cfg.get("params_hash", self.params_hash)

        mode = snap.get("mode") or {}
        self.armed = bool(mode.get("armed", self.armed))
        self.killed = bool(mode.get("killed", self.killed))

        mkt = snap.get("market") or {}
        self.last_price = mkt.get("last_price", self.last_price)

        candles = (snap.get("candles") or {}).get("items") or []
        if isinstance(candles, list):
            self.candles = candles

        ind = snap.get("indicators") or {}
        rsi_arr = ind.get("rsi14")
        if isinstance(rsi_arr, list) and rsi_arr:
            # 마지막 non-null
            for v in reversed(rsi_arr):
                if v is not None:
                    self.rsi14 = float(v)
                    break

    def apply_event(self, evt: Dict[str, Any]) -> None:
        t = (evt.get("type") or "").strip()

        if t == "ENGINE.STATUS.UPDATE":
            p = evt.get("payload") or {}
            mode = p.get("mode") or {}
            self.armed = bool(mode.get("armed", self.armed))
            self.killed = bool(mode.get("killed", self.killed))
            cfg = p.get("config") or {}
            self.strategy_id = cfg.get("strategy_id", self.strategy_id)
            self.profile = cfg.get("profile", self.profile)
            self.config_version = int(cfg.get("config_version", self.config_version) or 0)
            self.params_hash = cfg.get("params_hash", self.params_hash)
            mkt = p.get("market") or {}
            self.last_price = mkt.get("last_price", self.last_price)
            return

        if t == "CONFIG.UPDATED":
            p = evt.get("payload") or {}
            self.strategy_id = p.get("strategy_id", self.strategy_id)
            self.profile = p.get("profile", self.profile)
            self.config_version = int(p.get("config_version", self.config_version) or 0)
            self.params_hash = p.get("params_hash", self.params_hash)
            return

        if t == "MODE.ARMED":
            self.armed = True
            return
        if t == "MODE.DISARMED":
            self.armed = False
            return
        if t == "MODE.KILLED":
            self.killed = True
            self.armed = False
            return

        if t == "DATA.CANDLE":
            p = evt.get("payload") or {}
            c = p.get("candle") or {}
            if not isinstance(c, dict) or "t" not in c:
                return
            kind = p.get("kind", "UPDATE")
            t0 = int(c.get("t"))
            # 마지막 캔들 업데이트 정책
            if self.candles and int(self.candles[-1].get("t")) == t0:
                self.candles[-1] = c
            else:
                self.candles.append(c)
                # 버퍼 제한
                if len(self.candles) > 1200:
                    self.candles = self.candles[-1200:]
            self.last_price = c.get("c", self.last_price)
            return

        if t == "INDICATOR.UPDATE":
            p = evt.get("payload") or {}
            vals = p.get("values") or {}
            if "rsi14" in vals and vals["rsi14"] is not None:
                self.rsi14 = float(vals["rsi14"])
            return


class LiveMonitor(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("SMTM 실전 모니터 (관측 전용)")
        self.resize(1200, 820)

        self.client = IpcClient()
        self.store = StateStore()

        # UI
        root = QVBoxLayout(self)

        top = QHBoxLayout()
        self.lb_conn = QLabel("엔진: 미연결")
        self.lb_mode = QLabel("MODE: DISARMED")
        self.lb_cfg = QLabel("CFG: -")
        self.lb_price = QLabel("PRICE: -")
        self.lb_rsi = QLabel("RSI14: -")
        top.addWidget(self.lb_conn)
        top.addStretch(1)
        top.addWidget(self.lb_mode)
        top.addWidget(self.lb_cfg)
        top.addWidget(self.lb_price)
        top.addWidget(self.lb_rsi)

        self.bt_connect = QPushButton("엔진 연결/동기화")
        self.bt_connect.clicked.connect(self._connect_and_sync)
        top.addWidget(self.bt_connect)

        root.addLayout(top)

        # Chart
        self.plot = pg.PlotWidget()
        self.plot.showGrid(x=True, y=True)
        self.plot.setLabel("bottom", "time(t)")
        self.plot.setLabel("left", "price")
        self.curve = self.plot.plot([], [])
        root.addWidget(self.plot, 1)

        # Timeline
        self.te_log = QPlainTextEdit()
        self.te_log.setReadOnly(True)
        self.te_log.setMaximumHeight(220)
        root.addWidget(self.te_log)

        # Render timer
        self.render_timer = QTimer(self)
        self.render_timer.setInterval(100)  # 10Hz
        self.render_timer.timeout.connect(self._render)
        self.render_timer.start()

        # EVT signals
        self.client.evt_connected.connect(lambda: self._log("EVT 연결됨"))
        self.client.evt_disconnected.connect(lambda: self._log("EVT 연결 끊김 (재연결 시도 중)"))
        self.client.evt_message.connect(self._on_evt_msg)

    def _log(self, s: str) -> None:
        self.te_log.appendPlainText(s)

    def _connect_and_sync(self) -> None:
        # 1) CMD 연결 + STATUS
        ok = self.client.connect_cmd()
        if not ok:
            self.lb_conn.setText("엔진: CMD 연결 실패")
            self._log("CMD 연결 실패")
            return

        st = self.client.send_cmd("ENGINE.STATUS", {})
        if not st.get("ok"):
            self._log(f"STATUS 실패: {st.get('error')}")
        else:
            self._log("STATUS OK")

        # 2) SNAPSHOT
        snap = self.client.send_cmd("SNAPSHOT.GET", {"symbol": "BTC-KRW", "tf": "1m", "limit": 500, "include": {"indicators": True}})
        if snap.get("ok"):
            snapshot = (snap.get("payload") or {}).get("snapshot") or (snap.get("payload") or {}).get("snapshot", None)
            # handlers.py는 {"snapshot": snap} 를 payload로 감싸므로 아래 처리
            if snapshot is None:
                snapshot = (snap.get("payload") or {}).get("snapshot")
            if isinstance(snapshot, dict):
                self.store.apply_snapshot(snapshot)
                self._log(f"SNAPSHOT OK (candles={len(self.store.candles)})")
            else:
                self._log("SNAPSHOT 파싱 실패")
        else:
            self._log(f"SNAPSHOT 실패: {snap.get('error')}")

        # 3) EVT 연결 + 자동 재연결
        if self.client.connect_evt():
            self.lb_conn.setText("엔진: 연결됨")
            self._log("EVT 연결 성공")
        else:
            self.lb_conn.setText("엔진: EVT 연결 실패")
            self._log("EVT 연결 실패")
        self.client.start_evt_auto_reconnect()

        # 4) SUBSCRIBE (현재 엔진은 필터 저장만)
        self.client.send_cmd("EVENT.SUBSCRIBE", {"client_id": self.client.client_id, "symbol": self.store.symbol,
                                                 "channels": ["EVT.HEARTBEAT","ENGINE.STATUS.UPDATE","CONFIG.*","MODE.*","DATA.CANDLE","INDICATOR.UPDATE","TIMELINE.EVENT",
                    "ORDER.EVENT"
                ],
                                                 "tf": self.store.tf, "verbosity": "NORMAL"})

    def _on_evt_msg(self, evt: Dict[str, Any]) -> None:
        t = (evt.get("type") or "")
        if t == "TIMELINE.EVENT":
            p = evt.get("payload") or {}
            self._log(f"[{p.get('level')}] {p.get('category')} {p.get('code')}: {p.get('msg')}")
            return
        self.store.apply_event(evt)

    def _render(self) -> None:
        # Status line
        self.lb_mode.setText(f"MODE: {'KILLED' if self.store.killed else ('ARMED' if self.store.armed else 'DISARMED')}")
        self.lb_cfg.setText(f"CFG: {self.store.strategy_id} / {self.store.profile} v{self.store.config_version} ({self.store.params_hash})")
        self.lb_price.setText(f"PRICE: {self.store.last_price if self.store.last_price is not None else '-'}")
        self.lb_rsi.setText(f"RSI14: {self.store.rsi14 if self.store.rsi14 is not None else '-'}")

        # Chart data
        if not self.store.candles:
            return
        xs = [c["t"] for c in self.store.candles if "t" in c]
        ys = [c.get("c") for c in self.store.candles]
        if xs and ys and len(xs) == len(ys):
            self.curve.setData(xs, ys)


def main() -> int:
    app = QApplication(sys.argv)
    w = LiveMonitor()
    w.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
