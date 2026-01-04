# -*- coding: utf-8 -*-
"""
SMTM 로컬 IPC 클라이언트 (v1) - teardown-safe + signal-compat + connect timeout propagation

핵심
- UI 호환을 위해 cmd_connected/cmd_disconnected는 "무인자" 신호로 제공
- 문자열 정보는 별도 신호(cmd_connected_str/cmd_disconnected_str)로 제공
- 프로세스 종료/GC 타이밍에 발생하는 'wrapped C/C++ object ... deleted' RuntimeError 방지
- send_cmd(timeout_ms)가 connect_cmd(timeout_ms)에도 그대로 적용되도록 수정
"""
from __future__ import annotations

import time
import uuid
from typing import Any, Callable, Dict, Optional

from PyQt6.QtCore import QObject, pyqtSignal, QTimer
from PyQt6.QtNetwork import QLocalSocket

from .protocol import encode_message, DecodeBuffer


def now_ts_str() -> str:
    t = time.time()
    lt = time.localtime(t)
    ms = int((t - int(t)) * 1000)
    return time.strftime("%Y-%m-%d %H:%M:%S", lt) + f".{ms:03d}"


class IpcClient(QObject):
    """Qt 이벤트루프에서 동작하는 IPC 클라이언트. (동기/비동기 혼합 최소 구현)"""

    # EVT
    evt_message = pyqtSignal(dict)
    evt_connected = pyqtSignal()
    evt_disconnected = pyqtSignal()
    evt_connected_str = pyqtSignal(str)
    evt_disconnected_str = pyqtSignal(str)

    # CMD (UI 호환: 무인자 시그니처 유지)
    cmd_connected = pyqtSignal()
    cmd_disconnected = pyqtSignal()
    cmd_connected_str = pyqtSignal(str)
    cmd_disconnected_str = pyqtSignal(str)

    ENGINE_CMD_SERVER_NAME = "smtm_engine_ipc_cmd"
    ENGINE_EVT_SERVER_NAME = "smtm_engine_ipc_evt"

    def __init__(self,
                 server_cmd_name: str = ENGINE_CMD_SERVER_NAME,
                 server_evt_name: str = ENGINE_EVT_SERVER_NAME,
                 parent: Optional[QObject] = None) -> None:
        super().__init__(parent)

        self.server_cmd_name = str(server_cmd_name or self.ENGINE_CMD_SERVER_NAME)
        self.server_evt_name = str(server_evt_name or self.ENGINE_EVT_SERVER_NAME)

        # 디버그용 별칭(과거 코드 호환)
        self.server_name = self.server_cmd_name

        self.client_id = f"cli-{uuid.uuid4().hex[:10]}"

        self._cmd = QLocalSocket(self)
        self._evt = QLocalSocket(self)

        self._cmd_buf = DecodeBuffer()
        self._evt_buf = DecodeBuffer()

        self._pending_cmd_cb: Optional[Callable[[dict], None]] = None

        # CMD socket signals
        self._cmd.readyRead.connect(self._on_cmd_ready_read)
        self._cmd.disconnected.connect(self._on_cmd_disconnected)
        self._cmd.connected.connect(self._on_cmd_connected)

        # EVT socket signals
        self._evt.readyRead.connect(self._on_evt_ready_read)
        self._evt.disconnected.connect(self._on_evt_disconnected)
        self._evt.connected.connect(self._on_evt_connected)

        # 재연결 타이머(모니터용)
        self._evt_reconnect_timer = QTimer(self)
        self._evt_reconnect_timer.setInterval(1200)
        self._evt_reconnect_timer.timeout.connect(self._ensure_evt_connected)

    def connect_cmd(self, timeout_ms: int = 800) -> bool:
        if self._cmd.state() == QLocalSocket.LocalSocketState.ConnectedState:
            return True
        try:
            self._cmd.abort()
        except Exception:
            pass
        self._cmd.connectToServer(self.server_cmd_name)
        return self._cmd.waitForConnected(timeout_ms)

    def connect_evt(self, timeout_ms: int = 800) -> bool:
        if self._evt.state() == QLocalSocket.LocalSocketState.ConnectedState:
            return True
        try:
            self._evt.abort()
        except Exception:
            pass
        self._evt.connectToServer(self.server_evt_name)
        ok = self._evt.waitForConnected(timeout_ms)
        if ok:
            hello = {"v": 1, "type": "EVT.CLIENT_HELLO", "ts": now_ts_str(), "payload": {"client_id": self.client_id}}
            self._evt.write(encode_message(hello))
            self._evt.flush()
        return ok

    def start_evt_auto_reconnect(self) -> None:
        if not self._evt_reconnect_timer.isActive():
            self._evt_reconnect_timer.start()

    def stop_evt_auto_reconnect(self) -> None:
        if self._evt_reconnect_timer.isActive():
            self._evt_reconnect_timer.stop()

    def send_cmd(self, msg_type: str, payload: Optional[Dict[str, Any]] = None, req_id: Optional[str] = None,
                 timeout_ms: int = 1500) -> Dict[str, Any]:
        if payload is None:
            payload = {}
        if req_id is None:
            req_id = f"c-{uuid.uuid4().hex[:8]}"
        req = {"v": 1, "type": msg_type, "ts": now_ts_str(), "req_id": req_id, "source": "ui", "payload": payload}

        # ★ timeout_ms를 connect에도 동일하게 적용
        if not self.connect_cmd(timeout_ms=timeout_ms):
            try:
                err = self._cmd.errorString()
            except Exception:
                err = ""
            return {"ok": False, "error": {"code": "CMD_NOT_CONNECTED", "message": "엔진 CMD 채널 연결 실패", "qt_error_str": err, "server": self.server_cmd_name}}

        self._pending_cmd_cb = None
        self._cmd.write(encode_message(req))
        self._cmd.flush()

        if not self._cmd.waitForReadyRead(timeout_ms):
            return {"ok": False, "error": {"code": "CMD_TIMEOUT", "message": "엔진 응답 시간 초과"}}

        return self._read_one_cmd_message() or {"ok": False, "error": {"code": "CMD_BAD_RESPONSE", "message": "엔진 응답 파싱 실패"}}

    def _read_one_cmd_message(self) -> Optional[Dict[str, Any]]:
        while self._cmd.bytesAvailable() > 0:
            self._cmd_buf.feed(bytes(self._cmd.readAll()))
        return self._cmd_buf.next_message()

    def _on_cmd_ready_read(self) -> None:
        while self._cmd.bytesAvailable() > 0:
            self._cmd_buf.feed(bytes(self._cmd.readAll()))

    def _on_evt_ready_read(self) -> None:
        while self._evt.bytesAvailable() > 0:
            self._evt_buf.feed(bytes(self._evt.readAll()))
        while True:
            msg = self._evt_buf.next_message()
            if msg is None:
                break
            self.evt_message.emit(msg)

    # ---- emit helpers (teardown-safe) ----
    def _on_cmd_connected(self) -> None:
        try:
            self.cmd_connected.emit()
            self.cmd_connected_str.emit("connected")
        except RuntimeError:
            pass

    def _on_cmd_disconnected(self) -> None:
        try:
            self.cmd_disconnected.emit()
            self.cmd_disconnected_str.emit("disconnected")
        except RuntimeError:
            pass

    def _on_evt_connected(self) -> None:
        try:
            self.evt_connected.emit()
            self.evt_connected_str.emit("connected")
        except RuntimeError:
            pass

    def _on_evt_disconnected(self) -> None:
        try:
            self.evt_disconnected.emit()
            self.evt_disconnected_str.emit("disconnected")
        except RuntimeError:
            pass

    def _ensure_evt_connected(self) -> None:
        if self._evt.state() != QLocalSocket.LocalSocketState.ConnectedState:
            self.connect_evt()
