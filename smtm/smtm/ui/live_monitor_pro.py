
# -*- coding: utf-8 -*-
"""SMTM 전문가용 실전 모니터(프로용) UI - 도킹 기반 관측 전용 창

목표:
- 설정/튜닝 콘솔과 완전히 분리된 '관측 전용' 실전 모니터 UI
- 엔진 IPC EVT 스트림을 구독해 가격/주문/체결/포지션/리스크/로그를 한 화면에서 확인
- 로컬 전용(단일 PC) 기준

실행:
  cd C:\hys\smtm
  python -m smtm.ui.live_monitor_pro

요구사항:
- PyQt6
- (선택) pyqtgraph: 있으면 간단 차트 표시, 없으면 텍스트로 대체
"""
from pyqtgraph.Qt import QtGui

from __future__ import annotations

import json
import sys
import time
from datetime import datetime
import traceback
from collections import deque
from dataclasses import dataclass
from typing import Any, Deque, Dict, Optional, Tuple, List

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QAction, QFont, QTextCursor
from PyQt6.QtWidgets import (
    QApplication,
    QDockWidget,
    QLabel,
    QMainWindow,
    QMessageBox,
    QStatusBar,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

# pyqtgraph optional
try:
    import pyqtgraph as pg  # type: ignore
except Exception:
    pg = None  # type: ignore



# -----------------------------
# Small ring-buffer logger (UI)
# -----------------------------
class _RingLog:
    """Tiny in-memory ring log.
    - append(line): store a line
    - tail(n): return last n lines joined by \n
    """
    def __init__(self, maxlen: int = 2000):
        self._buf = deque(maxlen=maxlen)

    def clear(self) -> None:
        self._buf.clear()

    def append(self, line: str) -> None:
        try:
            self._buf.append(str(line))
        except Exception:
            # never crash UI by logging
            pass

    def tail(self, n: int = 200) -> str:
        try:
            if n <= 0:
                return ""
            items = list(self._buf)[-n:]
            return "\n".join(items)
        except Exception:
            return ""

# -----------------------------
# Candle / Chart helpers
# -----------------------------


@dataclass
class Candle:
    """단순 OHLC 캔들 (1개 바)."""

    t: int  # epoch seconds
    o: float
    h: float
    l: float
    c: float
    v: float = 0.0
    source: str = ""


if pg is not None:

    class TimeAxisItem(pg.AxisItem):
        """epoch seconds -> HH:MM:SS"""

        def tickStrings(self, values, scale, spacing):  # noqa: N802
            out = []
            for v in values:
                try:
                    out.append(datetime.fromtimestamp(float(v)).strftime("%H:%M:%S"))
                except Exception:
                    out.append("")
            return out

    class CandlestickItem(pg.GraphicsObject):
        """간단 캔들스틱 그래픽 아이템 (pyqtgraph GraphicsObject).

        - candles: [{t,o,h,l,c,v}, ...]  (t: epoch sec)
        """

        def __init__(self, candles: "Optional[List[Dict[str, Any]]]" = None):
            super().__init__()
            self._candles: "List[Dict[str, Any]]" = []
            self._picture: "Optional[QtGui.QPicture]" = None
            self._w: float = 30.0  # half-width in seconds (auto)

            if candles:
                self.set_candles(candles)
            else:
                self._rebuild_picture()

        def set_candles(self, candles: "List[Dict[str, Any]]") -> None:
            self._candles = list(candles or [])

            # candle 폭: 시간 간격(초) 기반으로 자동 산정 (기본 60초)
            ts = [float(c.get('t', 0)) for c in self._candles if c.get('t') is not None]
            ts = sorted(set(ts))
            if len(ts) >= 2:
                dt = max(1.0, ts[-1] - ts[-2])
                # 몸통이 서로 겹치지 않도록 70% 정도
                self._w = max(1.0, dt * 0.35)
            else:
                self._w = 30.0

            self._rebuild_picture()
            self.prepareGeometryChange()
            self.update()

        def _rebuild_picture(self) -> None:
            pic = QtGui.QPicture()
            p = QtGui.QPainter(pic)
            p.setRenderHint(QtGui.QPainter.Antialiasing, False)

            w = float(self._w)

            for c in self._candles:
                try:
                    t = float(c.get('t'))
                    o = float(c.get('o'))
                    h = float(c.get('h'))
                    l = float(c.get('l'))
                    cl = float(c.get('c'))
                except Exception:
                    continue

                up = cl >= o
                pen = QtGui.QPen(QtGui.QColor(0, 255, 0) if up else QtGui.QColor(255, 0, 0))
                pen.setWidthF(1.0)
                p.setPen(pen)
                p.setBrush(QtGui.QBrush(QtGui.QColor(0, 255, 0, 80) if up else QtGui.QColor(255, 0, 0, 80)))

                # wick
                p.drawLine(QtCore.QPointF(t, l), QtCore.QPointF(t, h))

                # body
                top = max(o, cl)
                bot = min(o, cl)
                rect = QtCore.QRectF(t - w, bot, 2 * w, max(1e-9, top - bot))
                p.drawRect(rect)

            p.end()
            self._picture = pic

        def paint(self, p: QtGui.QPainter, *args) -> None:
            if self._picture is None:
                return
            p.drawPicture(0, 0, self._picture)

        def boundingRect(self) -> QtCore.QRectF:
            if not self._candles:
                return QtCore.QRectF()

            xs = [float(c.get('t', 0.0)) for c in self._candles]
            lows = [float(c.get('l', c.get('c', 0.0))) for c in self._candles]
            highs = [float(c.get('h', c.get('c', 0.0))) for c in self._candles]

            x0 = min(xs) - self._w
            x1 = max(xs) + self._w
            y0 = min(lows)
            y1 = max(highs)

            # 안전 padding
            pad_y = (y1 - y0) * 0.05 if y1 > y0 else 1.0
            return QtCore.QRectF(x0, y0 - pad_y, (x1 - x0), (y1 - y0) + 2 * pad_y)


class RuntimeState:
    run_id: str = ""
    cfg_ver: Optional[int] = None
    profile: str = "SAFE"
    strategy_id: str = ""
    last_evt_ts: Optional[str] = None
    last_cmd_ts: Optional[str] = None
    # 최신 지표(표시용) - 예: {"rsi14": 55.2, "ema20": 1498230.0, "bb_up": ..., "bb_lo": ...}
    indicators: Dict[str, Any] = None  # type: ignore


@dataclass
class MarketSnapshot:
    """현재 시장 스냅샷(모니터 표기용).

    - live_monitor_pro는 EVT 스트림에서 들어온 DATA.CANDLE / INDICATOR.UPDATE 를
      UI에 표시할 때 최근 가격/심볼 등 '지금 상태'를 보관한다.
    - 최소 필드만 유지(확장 가능): symbol, last_price
    """
    symbol: str = "BTC-KRW"
    last_price: float = 0.0
    last_ts: str = ""  # optional: 최근 업데이트 시각(문자열)

    def update_price(self, symbol: str, price: float, ts: str = "") -> None:
        try:
            if symbol:
                self.symbol = symbol
        except Exception:
            pass
        try:
            self.last_price = float(price)
        except Exception:
            # price가 None/비정상일 때는 유지
            pass
        if ts:
            self.last_ts = ts


class LiveMonitorPro(QMainWindow):
    """전문가용 실전 모니터 메인 윈도우 (관측 전용)"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("SMTM 실전 모니터 PRO (관측 전용)")
        self.resize(1500, 900)

        self._ipc: Optional[Any] = None
        self._connected_cmd = False
        self._connected_evt = False

        self.state = RuntimeState()
        if self.state.indicators is None:
            self.state.indicators = {}
        self.market = MarketSnapshot()
        self._log = _RingLog()

        self._candles: Deque[Candle] = deque(maxlen=240)
        self._ema20_series: Deque[Tuple[float, float]] = deque(maxlen=240)
        self._bb_up_series: Deque[Tuple[float, float]] = deque(maxlen=240)
        self._bb_lo_series: Deque[Tuple[float, float]] = deque(maxlen=240)

        self._build_ui()
        self._bind_actions()

        # 타이머: 상태/차트 갱신
        self._ui_timer = QTimer(self)
        self._ui_timer.setInterval(500)
        self._ui_timer.timeout.connect(self._tick_ui)
        self._ui_timer.start()

        # 시작 시 연결 시도
        self._connect_ipc()

    # ---------------- UI 구성 ----------------

    def _build_ui(self) -> None:
        self._status = QStatusBar(self)
        self.setStatusBar(self._status)
        self._status_label = QLabel("대기 중")
        self._status.addWidget(self._status_label, 1)

        # 툴바
        tb = QToolBar("도구", self)
        self.addToolBar(tb)
        self.act_reconnect = QAction("재연결", self)
        self.act_clear = QAction("로그 지우기", self)
        tb.addAction(self.act_reconnect)
        tb.addAction(self.act_clear)

        # 중앙: 요약 + 차트
        central = QWidget(self)
        v = QVBoxLayout(central)
        v.setContentsMargins(6, 6, 6, 6)

        self.lbl_symbol = QLabel("심볼: KRW-BTC")
        self.lbl_price = QLabel("현재가: -")
        self.lbl_cfg = QLabel("CFG: -")
        self.lbl_ind = QLabel("지표: -")
        self.lbl_conn = QLabel("IPC: CMD- / EVT-")
        for w in (self.lbl_symbol, self.lbl_price, self.lbl_cfg, self.lbl_ind, self.lbl_conn):
            w.setStyleSheet("font-weight:600;")
        v.addWidget(self.lbl_symbol)
        v.addWidget(self.lbl_price)
        v.addWidget(self.lbl_cfg)
        v.addWidget(self.lbl_ind)
        v.addWidget(self.lbl_conn)

        if pg is not None:
            axis = TimeAxisItem(orientation="bottom")
            self._plot = pg.PlotWidget(background="k", axisItems={"bottom": axis})
            self._plot.showGrid(x=True, y=True, alpha=0.3)
            self._plot.setLabel("left", "price")
            self._plot.setLabel("bottom", "time")
            self._plot.setMouseEnabled(x=True, y=True)
            self._plot.setMenuEnabled(True)

            self._candle_item = CandlestickItem()
            self._plot.addItem(self._candle_item)

            # Indicator overlays (keep simple, consistent colors)
            self._ema_curve = self._plot.plot([], [], pen=pg.mkPen((120, 200, 255), width=1))
            self._bb_up_curve = self._plot.plot([], [], pen=pg.mkPen((160, 160, 160), width=1))
            self._bb_lo_curve = self._plot.plot([], [], pen=pg.mkPen((160, 160, 160), width=1))
        else:
            # pyqtgraph 미설치 환경에서는 단순 안내 라벨로 대체
            self._plot = QLabel("pyqtgraph not installed")
        v.addWidget(self._plot, 1)
        self.setCentralWidget(central)

        # 도킹: 주문/체결, 포지션, 리스크, 이벤트(raw), 로그
        self.dock_orders = self._make_table_dock("주문/체결", ["시간", "유형", "심볼", "가격", "수량", "메모"])
        self.dock_positions = self._make_table_dock("포지션", ["심볼", "수량", "평단", "평가손익", "상태"])
        self.dock_risk = self._make_text_dock("리스크/상태")
        self.dock_events = self._make_text_dock("이벤트 RAW")
        self.dock_log = self._make_text_dock("운영 로그")

        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.dock_orders)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.dock_positions)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.dock_log)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.dock_events)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.dock_risk)

        self.tabifyDockWidget(self.dock_orders, self.dock_positions)
        self.dock_orders.raise_()

    def _make_table_dock(self, title: str, headers: list[str]) -> QDockWidget:
        dock = QDockWidget(title, self)
        dock.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)
        table = QTableWidget(0, len(headers), dock)
        table.setHorizontalHeaderLabels(headers)
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setAlternatingRowColors(True)
        table.setSortingEnabled(False)
        dock.setWidget(table)
        return dock

    def _make_text_dock(self, title: str) -> QDockWidget:
        dock = QDockWidget(title, self)
        dock.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)
        box = QTextEdit(dock)
        box.setReadOnly(True)
        box.setFont(QFont("Consolas", 10))
        dock.setWidget(box)
        if title == "운영 로그":
            self.txt_log = box
        elif title == "이벤트 RAW":
            self.txt_events = box
        elif title == "리스크/상태":
            self.txt_risk = box
        return dock

    # ---------------- 액션 ----------------

    def _bind_actions(self) -> None:
        self.act_reconnect.triggered.connect(self._connect_ipc)
        self.act_clear.triggered.connect(self._clear_logs)

    def closeEvent(self, event) -> None:  # type: ignore[override]
        try:
            if self._ipc is not None and hasattr(self._ipc, "close"):
                self._ipc.close()
        except Exception:
            pass
        super().closeEvent(event)

    # ---------------- IPC ----------------

    def _connect_ipc(self) -> None:
        if IpcClient is None:
            self._append_log("[ERR] IpcClient import 실패: smtm.ipc.client 확인 필요")
            QMessageBox.critical(self, "IPC 오류", "IpcClient를 import 할 수 없습니다. smtm.ipc.client를 확인하세요.")
            return

        try:
            if self._ipc is not None and hasattr(self._ipc, "close"):
                try:
                    self._ipc.close()
                except Exception:
                    pass

            self._ipc = IpcClient()

            # 신호 연결(오버로드 대응)
            self._safe_connect_signal("cmd_connected", self._on_cmd_connected)
            self._safe_connect_signal("cmd_disconnected", self._on_cmd_disconnected)
            self._safe_connect_signal("evt_connected", self._on_evt_connected)
            self._safe_connect_signal("evt_disconnected", self._on_evt_disconnected)
            self._safe_connect_signal("evt_message", self._on_evt_message)

            # 연결 시도(메서드 존재하는 것만)
            ok_cmd = self._call_if_exists(self._ipc, ["connect_cmd", "connect", "open_cmd"], default=False)
            ok_evt = self._call_if_exists(self._ipc, ["connect_evt", "open_evt"], default=False)

            self._append_log(f"[IPC] connect_cmd={ok_cmd} connect_evt={ok_evt}")
            self._set_status("IPC 연결 시도 완료", 3000)

        except Exception as e:
            self._append_log(f"[ERR] IPC 연결 실패: {e}")
            self._append_log(traceback.format_exc())
            QMessageBox.critical(self, "IPC 오류", f"IPC 연결 실패:\n{e}")

    def _safe_connect_signal(self, obj: Any, sig_name: str, slot: Any) -> bool:
        """Connect PyQt signal safely.

        PyQt can raise AttributeError when accessing a signal with a specific signature
        (e.g. it complains about 'cmd_disconnected()'). We support both plain and
        overloaded(str) signals without crashing.
        """
        if obj is None:
            return False

        sig = None
        # 1) Try normal attribute access
        try:
            sig = getattr(obj, sig_name)
        except Exception:
            sig = None

        # 2) If that failed, try binding the class descriptor (works for some PyQt cases)
        if sig is None:
            try:
                sig_desc = getattr(obj.__class__, sig_name, None)
                if sig_desc is not None:
                    sig = sig_desc.__get__(obj, obj.__class__)
            except Exception:
                sig = None

        if sig is None:
            self._log_line(f"[IPC] signal missing: {sig_name}")
            return False

        # Prefer 'str' overload first (avoids PyQt selecting the empty '()' signature)
        for getter in (lambda s: s[str], lambda s: s):
            try:
                s = getter(sig)
                s.connect(slot)
                return True
            except Exception:
                continue

        self._log_line(f"[IPC] signal connect failed: {sig_name}")
        return False
    def _call_if_exists(self, obj: Any, fn_names: list[str], default: Any = None) -> Any:
        for fn in fn_names:
            if hasattr(obj, fn):
                try:
                    return getattr(obj, fn)()
                except TypeError:
                    continue
                except Exception:
                    continue
        return default

    # ---------------- IPC 콜백 ----------------

    def _on_cmd_connected(self, *args) -> None:
        self._connected_cmd = True
        self.state.last_cmd_ts = self._now()
        self._append_log("[IPC] CMD 연결됨")

    def _on_cmd_disconnected(self, *args) -> None:
        self._connected_cmd = False
        self._append_log("[IPC] CMD 끊김")

    def _on_evt_connected(self, *args) -> None:
        self._connected_evt = True
        self.state.last_evt_ts = self._now()
        self._append_log("[IPC] EVT 연결됨")

    def _on_evt_disconnected(self, *args) -> None:
        self._connected_evt = False
        self._append_log("[IPC] EVT 끊김")

    def _on_evt_message(self, msg: Dict[str, Any]) -> None:
        try:
            self.state.last_evt_ts = self._now()
            raw = json.dumps(msg, ensure_ascii=False)
            self._append_event(raw)
            self._apply_event(msg)
        except Exception as e:
            self._append_log(f"[ERR] EVT 처리 실패: {e}")
            self._append_log(traceback.format_exc())

    # ---------------- 이벤트 파싱 ----------------

    def _apply_event(self, msg: Dict[str, Any]) -> None:
        et = str(msg.get("type") or msg.get("evt") or msg.get("event") or "").upper()
        payload = msg.get("payload") or msg

        # 공통 심볼
        try:
            sym = msg.get("symbol") or payload.get("symbol") or payload.get("market")
            if sym:
                self.market.symbol = str(sym)
        except Exception:
            pass

        if et in ("CONFIG.UPDATED", "CONFIG_UPDATED", "CFG.UPDATED"):
            try:
                self.state.cfg_ver = payload.get("config_version") or payload.get("ver") or payload.get("version")
                self.state.profile = payload.get("profile") or self.state.profile
                self.state.strategy_id = payload.get("strategy_id") or self.state.strategy_id
            except Exception:
                pass
            self._append_log(f"[CFG] updated ver={self.state.cfg_ver} profile={self.state.profile}")
            return

        if et in ("TICK", "MARKET.TICK", "PRICE.TICK", "QUOTE"):
            px = payload.get("price") or payload.get("last") or payload.get("trade_price")
            try:
                if px is not None:
                    self.market.last_price = float(px)
                    self._push_price(self.market.last_price, ts=payload.get("ts"))
            except Exception:
                pass
            return

        # 엔진이 내보내는 캔들 이벤트(현재 스냅샷/리플레이/더미 포함)
        if et in ("DATA.CANDLE", "CANDLE", "MARKET.CANDLE", "CANDLE.UPDATE", "CANDLE.UPDATED"):
            candle = payload.get("candle") if isinstance(payload, dict) else None
            if isinstance(candle, dict):
                # 표준 키: t,o,h,l,c,v (epoch seconds)
                px = candle.get("c") or candle.get("close")
                ts = candle.get("t") or candle.get("ts")
            else:
                px = payload.get("c") or payload.get("close") or payload.get("price")
                ts = payload.get("t") or payload.get("ts")

            try:
                if px is not None:
                    c = float(px)
                    t = float(ts or time.time())
                    # Prefer full OHLC when present
                    o = payload.get("o")
                    h = payload.get("h")
                    l = payload.get("l")
                    if isinstance(candle, dict):
                        o = candle.get("o", o)
                        h = candle.get("h", h)
                        l = candle.get("l", l)
                    o = c if o is None else float(o)
                    h = c if h is None else float(h)
                    l = c if l is None else float(l)

                    self.market.last_price = c
                    self._push_candle(t, o, h, l, c)
            except Exception:
                pass
            return

        # 지표 업데이트(차트 상단/리스크 패널 표시용)
        if et in ("INDICATOR.UPDATE", "INDICATOR_UPDATED", "INDICATOR.UPDATED"):
            try:
                values = payload.get("values") or {}
                if isinstance(values, dict):
                    self.state.indicators.update(values)
                t = payload.get("at_t") or payload.get("t") or time.time()
                if isinstance(values, dict):
                    self._push_indicator(float(t), values)
            except Exception:
                pass
            return

        if et in ("ORDER", "ORDER.UPDATED", "FILL", "TRADE", "EXECUTION"):
            self._append_order_row(payload, et)
            return

        if et in ("POSITION", "POSITION.UPDATED", "RISK", "RISK.UPDATED", "PNL"):
            self._refresh_risk(payload)
            self._refresh_positions(payload)
            return

    def _append_order_row(self, payload: Dict[str, Any], et: str) -> None:
        table: QTableWidget = self.dock_orders.widget()  # type: ignore
        row = table.rowCount()
        table.insertRow(row)

        ts = payload.get("kst") or payload.get("ts") or self._now()
        sym = payload.get("symbol") or payload.get("market") or self.market.symbol
        price = payload.get("price") or payload.get("trade_price") or payload.get("avg_price") or "-"
        qty = payload.get("qty") or payload.get("volume") or payload.get("size") or "-"
        memo = payload.get("side") or payload.get("state") or payload.get("type") or ""

        vals = [str(ts), et, str(sym), str(price), str(qty), str(memo)]
        for c, v in enumerate(vals):
            table.setItem(row, c, QTableWidgetItem(v))
        table.scrollToBottom()

    def _refresh_positions(self, payload: Dict[str, Any]) -> None:
        table: QTableWidget = self.dock_positions.widget()  # type: ignore
        sym = payload.get("symbol") or self.market.symbol
        qty = payload.get("qty") or payload.get("position_qty") or payload.get("balance") or "-"
        avg = payload.get("avg_price") or payload.get("entry") or "-"
        pnl = payload.get("pnl") or payload.get("unrealized") or "-"
        st = payload.get("state") or payload.get("status") or ""
        if table.rowCount() == 0:
            table.insertRow(0)
        vals = [str(sym), str(qty), str(avg), str(pnl), str(st)]
        for c, v in enumerate(vals):
            table.setItem(0, c, QTableWidgetItem(v))

    def _refresh_risk(self, payload: Dict[str, Any]) -> None:
        lines = []
        lines.append(f"심볼: {self.market.symbol}")
        lines.append(f"프로파일: {self.state.profile}")
        lines.append(f"전략: {self.state.strategy_id}")
        lines.append(f"CFG ver: {self.state.cfg_ver}")
        lines.append("")
        for k in ("leverage", "exposure", "drawdown", "max_dd", "risk_level"):
            if k in payload:
                lines.append(f"{k}: {payload.get(k)}")
        self.txt_risk.setPlainText("\n".join(lines))

    # ---------------- UI 업데이트 ----------------

    def _tick_ui(self) -> None:
        self.lbl_symbol.setText(f"심볼: {self.market.symbol}")
        self.lbl_price.setText("현재가: -" if self.market.last_price is None else f"현재가: {self.market.last_price:,.0f}")
        self.lbl_cfg.setText(f"CFG: ver={self.state.cfg_ver} / {self.state.profile}")

        # 지표(있으면 표시)
        try:
            ind = self.state.indicators or {}
            parts = []
            if "rsi14" in ind and ind.get("rsi14") is not None:
                parts.append(f"RSI14:{float(ind.get('rsi14')):.1f}")
            if "ema20" in ind and ind.get("ema20") is not None:
                parts.append(f"EMA20:{float(ind.get('ema20')):,.0f}")
            if "bb_up" in ind and ind.get("bb_up") is not None and "bb_lo" in ind and ind.get("bb_lo") is not None:
                parts.append(f"BB:{float(ind.get('bb_lo')):,.0f}~{float(ind.get('bb_up')):,.0f}")
            self.lbl_ind.setText("지표: -" if not parts else "지표: " + "  ".join(parts))
        except Exception:
            self.lbl_ind.setText("지표: -")

        self.lbl_conn.setText(f"IPC: CMD={'OK' if self._connected_cmd else '-'} / EVT={'OK' if self._connected_evt else '-'}")
        self._status_label.setText(f"마지막 EVT: {self.state.last_evt_ts or '-'} | 마지막 CMD: {self.state.last_cmd_ts or '-'}")

        if pg is not None and hasattr(self, "_candle_item"):
            if len(self._candles) >= 2:
                # Qt의 QGraphicsItem.setData(int, QVariant)와 이름이 충돌하므로
                # CandlestickItem 전용 API(set_candles)를 사용한다.
                self._candle_item.set_candles(list(self._candles))

            xs = [c.t for c in self._candles]
            if xs:
                ema_map = {t: v for (t, v) in self._ema20_series}
                up_map = {t: v for (t, v) in self._bb_up_series}
                lo_map = {t: v for (t, v) in self._bb_lo_series}

                nan = float("nan")
                ema = [ema_map.get(t, nan) for t in xs]
                up = [up_map.get(t, nan) for t in xs]
                lo = [lo_map.get(t, nan) for t in xs]

                try:
                    self._ema_curve.setData(xs, ema)
                    self._bb_up_curve.setData(xs, up)
                    self._bb_lo_curve.setData(xs, lo)
                except Exception:
                    pass


        # auto-range (최근 캔들 기준)
        try:
            if self._candles and hasattr(self, '_price_plot'):
                xs = [c.t for c in self._candles]
                x0, x1 = min(xs), max(xs)
                # Y는 캔들 high/low 기준
                lows = [c.l for c in self._candles]
                highs = [c.h for c in self._candles]
                y0, y1 = min(lows), max(highs)
                if x1 > x0:
                    self._price_plot.setXRange(x0, x1, padding=0.02)
                if y1 > y0:
                    self._price_plot.setYRange(y0, y1, padding=0.05)
        except Exception:
            pass

    def _push_price(self, price: float, ts: Optional[float] = None) -> None:
        """(호환용) 가격만 들어오는 경우 선형 캔들로 축적."""
        t = time.time() if ts is None else float(ts)
        self._push_candle(t, price, price, price, price)

    def _push_candle(self, t: float, o: float, h: float, l: float, c: float) -> None:
        """DATA.CANDLE 수신 시 캔들 버퍼 갱신."""
        t = float(t)
        cd = Candle(t=t, o=float(o), h=float(h), l=float(l), c=float(c))
        if self._candles and abs(self._candles[-1].t - t) < 1e-6:
            self._candles[-1] = cd
        else:
            self._candles.append(cd)

    def _push_indicator(self, t: float, values: Dict[str, Any]) -> None:
        """INDICATOR.UPDATE 수신 시 지표 시계열 갱신."""
        t = float(t)
        def _up(series: Deque[Tuple[float, float]], val: Any) -> None:
            if val is None:
                return
            try:
                fv = float(val)
            except Exception:
                return
            if series and abs(series[-1][0] - t) < 1e-6:
                series[-1] = (t, fv)
            else:
                series.append((t, fv))

        _up(self._ema20_series, (values or {}).get("ema20"))
        _up(self._bb_up_series, (values or {}).get("bb_up"))
        _up(self._bb_lo_series, (values or {}).get("bb_lo"))

    # ---------------- 로그 ----------------

    def _append_log(self, line: str) -> None:
        s = f"{self._now()} {line}"
        self._log.add(s)
        self.txt_log.append(s)
        self.txt_log.moveCursor(QTextCursor.MoveOperation.End)

    def _append_event(self, raw: str) -> None:
        self.txt_events.append(raw)
        doc = self.txt_events.document()
        if doc.blockCount() > 500:
            cursor = QTextCursor(doc)
            cursor.movePosition(QTextCursor.MoveOperation.Start)
            cursor.select(QTextCursor.SelectionType.BlockUnderCursor)
            cursor.removeSelectedText()
            cursor.deleteChar()

    def _clear_logs(self) -> None:
        self.txt_log.clear()
        self.txt_events.clear()
        self._append_log("[UI] 로그 초기화")

    def _set_status(self, text: str, ms: int = 5000) -> None:
        self.statusBar().showMessage(text, ms)

    @staticmethod
    def _now() -> str:
        return time.strftime("%Y-%m-%d %H:%M:%S")


def main() -> None:
    app = QApplication(sys.argv)
    w = LiveMonitorPro()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()