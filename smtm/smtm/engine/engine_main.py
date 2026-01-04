# -*- coding: utf-8 -*-
"""
SMTM Engine 프로토타입 (3단계 전까지)

- 로컬 IPC 서버 (CMD + EVT)
- CMD: PING/ENGINE.STATUS/CONFIG.APPLY/ARM/DISARM/KILL/SNAPSHOT.GET
- EVT: HEARTBEAT/STATUS.UPDATE/DATA.CANDLE/INDICATOR.UPDATE/TIMELINE.EVENT (더미)

실거래/실데이터는 아직 연결하지 않는다. (관측/통신 안정화 목적)
"""
from __future__ import annotations

import sys
import time
from typing import Any, Dict, List, Optional

from PyQt6.QtCore import QCoreApplication, QObject, QTimer
from PyQt6.QtNetwork import QLocalServer, QLocalSocket

from smtm.ipc.protocol import encode_message, DecodeBuffer
from smtm.engine.state import EngineState, now_ts_str
from smtm.engine.handlers import handle_command, status_payload
from smtm.engine.order_manager import OrderManager


CMD_SERVER_NAME = "smtm_engine_ipc_cmd"
EVT_SERVER_NAME = "smtm_engine_ipc_evt"


class EngineServer(QObject):
    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self.state = EngineState()

        # Gate 2E: OrderManager 연결
        self.orders = OrderManager(self.state, self._broadcast)

        self.cmd_server = QLocalServer(self)
        self.evt_server = QLocalServer(self)

        # 기존 서버 잔존 제거(윈도우 재실행 대비)
        QLocalServer.removeServer(CMD_SERVER_NAME)
        QLocalServer.removeServer(EVT_SERVER_NAME)

        self.cmd_server.newConnection.connect(self._on_cmd_new_connection)
        self.evt_server.newConnection.connect(self._on_evt_new_connection)

        self._evt_clients: List[QLocalSocket] = []
        self._cmd_buffers: Dict[int, DecodeBuffer] = {}
        self._evt_buffers: Dict[int, DecodeBuffer] = {}

        # 더미 스트림 타이머
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._tick)

        self._status_timer = QTimer(self)
        self._status_timer.setInterval(10_000)
        self._status_timer.timeout.connect(self._broadcast_status_update)

    def start(self) -> bool:
        ok1 = self.cmd_server.listen(CMD_SERVER_NAME)
        ok2 = self.evt_server.listen(EVT_SERVER_NAME)
        if ok1 and ok2:
            self._timer.start()
            self._status_timer.start()
            self._log_timeline("SYSTEM", "ENGINE_START", "엔진 시작", {"cmd": CMD_SERVER_NAME, "evt": EVT_SERVER_NAME})
            return True
        return False

    # ---------------- CMD ----------------
    def _on_cmd_new_connection(self) -> None:
        sock = self.cmd_server.nextPendingConnection()
        if sock is None:
            return
        sid = int(sock.socketDescriptor())
        self._cmd_buffers[sid] = DecodeBuffer()
        sock.readyRead.connect(lambda s=sock: self._on_cmd_ready_read(s))
        sock.disconnected.connect(lambda s=sock: self._on_cmd_disconnected(s))

    def _on_cmd_disconnected(self, sock: QLocalSocket) -> None:
        sid = int(sock.socketDescriptor())
        self._cmd_buffers.pop(sid, None)
        sock.deleteLater()

    def _on_cmd_ready_read(self, sock: QLocalSocket) -> None:
        sid = int(sock.socketDescriptor())
        buf = self._cmd_buffers.get(sid)
        if buf is None:
            buf = DecodeBuffer()
            self._cmd_buffers[sid] = buf

        while sock.bytesAvailable() > 0:
            buf.feed(bytes(sock.readAll()))

        while True:
            req = buf.next_message()
            if req is None:
                break
            try:
                ack_msg, evt = handle_command(req, self.state, services={'orders': self.orders})
            except Exception as e:
                import traceback
                tb = traceback.format_exc(limit=30)
                ack_msg = {
                    'v': 1,
                    'type': 'ACK',
                    'ts': now_ts_str(),
                    'req_id': req.get('req_id', ''),
                    'run_id': self.state.run_id,
                    'ok': False,
                    'error': {'code': 'ENGINE_EXCEPTION', 'message': str(e)},
                    'payload': {'traceback': tb},
                }
                evt = None
            sock.write(encode_message(ack_msg))
            sock.flush()
            if evt is not None:
                self._broadcast(evt)

    # ---------------- EVT ----------------
    def _on_evt_new_connection(self) -> None:
        sock = self.evt_server.nextPendingConnection()
        if sock is None:
            return
        sid = int(sock.socketDescriptor())
        self._evt_clients.append(sock)
        self._evt_buffers[sid] = DecodeBuffer()
        sock.readyRead.connect(lambda s=sock: self._on_evt_ready_read(s))  # HELLO 정도만 처리
        sock.disconnected.connect(lambda s=sock: self._on_evt_disconnected(s))

        # 연결 즉시 최소 안내
        hello = {
            "v": 1, "type": "EVT.SERVER_HELLO", "ts": now_ts_str(), "run_id": self.state.run_id,
            "symbol": self.state.symbol, "seq": self.state.bump_seq(),
            "payload": {"msg": "EVT connected", "run_id": self.state.run_id}
        }
        sock.write(encode_message(hello))
        sock.flush()

    def _on_evt_disconnected(self, sock: QLocalSocket) -> None:
        try:
            self._evt_clients.remove(sock)
        except ValueError:
            pass
        sid = int(sock.socketDescriptor())
        self._evt_buffers.pop(sid, None)
        sock.deleteLater()

    def _on_evt_ready_read(self, sock: QLocalSocket) -> None:
        # 현재는 구독 필터를 EVT로 받는 정도만 허용(확장 여지)
        sid = int(sock.socketDescriptor())
        buf = self._evt_buffers.get(sid)
        if buf is None:
            buf = DecodeBuffer()
            self._evt_buffers[sid] = buf
        while sock.bytesAvailable() > 0:
            buf.feed(bytes(sock.readAll()))
        while True:
            msg = buf.next_message()
            if msg is None:
                break
            # HELLO/디버그 메시지 무시 (필요 시 필터 저장 확장 가능)
            # print("EVT client msg:", msg)
            pass

    # ---------------- Broadcast helpers ----------------
    def _broadcast(self, evt: Dict[str, Any]) -> None:
        dead: List[QLocalSocket] = []
        data = encode_message(evt)
        for c in list(self._evt_clients):
            try:
                c.write(data)
                c.flush()
            except Exception:
                dead.append(c)
        for d in dead:
            self._on_evt_disconnected(d)

    def _broadcast_status_update(self) -> None:
        evt = {
            "v": 1,
            "type": "ENGINE.STATUS.UPDATE",
            "ts": now_ts_str(),
            "run_id": self.state.run_id,
            "symbol": self.state.symbol,
            "seq": self.state.bump_seq(),
            "payload": {
                "mode": {"armed": self.state.armed, "killed": self.state.killed, "block_orders": self.state.block_orders},
                "config": {"strategy_id": self.state.strategy_id, "profile": self.state.profile,
                           "config_version": self.state.config_version, "params_hash": self.state.params_hash},
                "market": {"last_price": self.state.last_price, "last_tick_ts": self.state.last_tick_ts},
                "position": {"side": "NONE", "qty": 0.0, "avg_price": 0.0, "unrealized_pnl_pct": 0.0},
                "risk": {"block_state": "OK", "block_reason": None, "exposure_pct": 0.0,
                         "daily_loss_limit_pct": 30.0, "daily_pnl_pct": 0.0},
                "health": {"feed": "OK", "latency_ms": 0},
            }
        }
        self._broadcast(evt)

    def _log_timeline(self, category: str, code: str, msg: str, meta: Dict[str, Any] | None = None,
                      level: str = "INFO") -> None:
        evt = {
            "v": 1,
            "type": "TIMELINE.EVENT",
            "ts": now_ts_str(),
            "run_id": self.state.run_id,
            "symbol": self.state.symbol,
            "seq": self.state.bump_seq(),
            "payload": {"level": level, "category": category, "code": code, "msg": msg, "meta": meta or {}}
        }
        self._broadcast(evt)

    # ---------------- Dummy tick ----------------
    def _tick(self) -> None:
        # 하트비트
        hb = {
            "v": 1,
            "type": "EVT.HEARTBEAT",
            "ts": now_ts_str(),
            "run_id": self.state.run_id,
            "symbol": self.state.symbol,
            "seq": self.state.bump_seq(),
            "payload": {"lag_ms": 0, "evt_backlog": 0, "engine_uptime_sec": self._uptime_sec(),
                        "health": {"feed": "OK", "account": "UNKNOWN", "orders": "DISABLED"}}
        }
        self._broadcast(hb)

        # 더미 캔들(UPDATE)
        now = int(time.time())
        t0 = now - (now % 60)
        base = self.state.last_price or 1500000.0
        # 천천히 움직이도록
        step = (self.state.evt_seq % 7 - 3) * 150.0
        price = float(base + step)
        self.state.last_price = price
        self.state.last_tick_ts = now_ts_str()

        candle_evt = {
            "v": 1,
            "type": "DATA.CANDLE",
            "ts": now_ts_str(),
            "run_id": self.state.run_id,
            "symbol": self.state.symbol,
            "seq": self.state.bump_seq(),
            "payload": {
                "tf": self.state.tf,
                "kind": "UPDATE",
                "candle": {"t": t0, "o": price - 200, "h": price + 300, "l": price - 350, "c": price, "v": 1.23},
                "source": "DUMMY"
            }
        }
        self._broadcast(candle_evt)

        ind_evt = {
            "v": 1,
            "type": "INDICATOR.UPDATE",
            "ts": now_ts_str(),
            "run_id": self.state.run_id,
            "symbol": self.state.symbol,
            "seq": self.state.bump_seq(),
            "payload": {
                "tf": self.state.tf,
                "at_t": t0,
                "values": {"rsi14": 55.2, "ema20": price - 120, "bb_up": price * 1.01, "bb_lo": price * 0.99}
            }
        }
        self._broadcast(ind_evt)

    def _uptime_sec(self) -> int:
        # started_ts 문자열이므로 정확계산 생략(프로토타입)
        return int(time.time() - self.state.started_epoch)


def main() -> int:
    app = QCoreApplication(sys.argv)
    srv = EngineServer()
    if not srv.start():
        print("엔진 서버 시작 실패")
        return 2
    print(f"[ENGINE] CMD={CMD_SERVER_NAME} EVT={EVT_SERVER_NAME} run_id={srv.state.run_id}")
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
