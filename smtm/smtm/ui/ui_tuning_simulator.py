# -*- coding: utf-8 -*-
"""
BBI V3 Spec v1.6 (Volume) - Tuning UI (Full: UI <-> Backtest Runner) [INTEGRATED FINAL]

핵심
- SMTM_ROOT 자동 탐지 + 절대경로 고정 (환경변수 SMTM_ROOT 우선)
- subprocess + QThread 로 백테스트 실행 및 로그 스트리밍
- 실행 시 cwd 고정 + env["SMTM_ROOT"] 강제 주입
- output/result 폴더 자동 생성
- DB(smtm.db) upbit 테이블 기준으로 날짜 범위 자동 제한 (Backtest 페이지 생성 후 적용)
"""

import json
import os
import uuid
import traceback
import datetime

print("[UI] UI_FILE =", os.path.abspath(__file__))
print("[UI] UI_VER  =", "ui-v41-stable-backtest-safe")
import sys
import time
import subprocess
import sqlite3
from copy import deepcopy
from typing import Dict, Any, List, Optional, Tuple

import requests
import platform


from PyQt6.QtCore import Qt, QDate, QThread, pyqtSignal, QTimer
from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QListWidget,
    QStackedWidget,
    QHBoxLayout,
    QVBoxLayout,
    QLabel,
    QSlider,
    QDoubleSpinBox,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QPushButton,
    QFileDialog,
    QMenuBar,
    QStatusBar,
    QMessageBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QLineEdit,
    QDateEdit,
    QPlainTextEdit,
    QTabWidget,
)

from PyQt6.QtWidgets import QCheckBox
# --------------------------------------------------------------------------------------
# Project constants
# --------------------------------------------------------------------------------------

STRATEGY_CODE = "BBI-V3-SPEC-V16-VOL"
TUNING_FILE_NAME = "bbi_v16_vol_tuning.json"

DEFAULT_SMTM_ROOT = r"C:\hys\smtm"

UPBIT_MARKETS_URL = "https://api.upbit.com/v1/market/all"
UPBIT_TICKER_URL = "https://api.upbit.com/v1/ticker"


# --------------------------------------------------------------------------------------
# Root / Path helpers
# --------------------------------------------------------------------------------------

def detect_project_root() -> str:
    """
    파일이 .../smtm/ui/ui_tuning_simulator.py 에 있다고 가정.
    -> project root(= .../ ) 반환
    """
    here = os.path.abspath(__file__)
    ui_dir = os.path.dirname(here)          # .../smtm/ui
    smtm_dir = os.path.dirname(ui_dir)      # .../smtm
    root = os.path.dirname(smtm_dir)        # .../
    return root

def pick_smtm_root() -> str:
    env_root = os.environ.get("SMTM_ROOT", "").strip()
    if env_root:
        return os.path.abspath(env_root)

    try:
        auto = detect_project_root()
        if os.path.isdir(os.path.join(auto, "smtm")):
            return os.path.abspath(auto)
    except Exception:
        pass

    return os.path.abspath(DEFAULT_SMTM_ROOT)

SMTM_ROOT = pick_smtm_root()

# Ensure SMTM package import works even when running this file directly.
if SMTM_ROOT and SMTM_ROOT not in sys.path:
    sys.path.insert(0, SMTM_ROOT)

DEFAULT_RESULTS_JSON = os.path.join(SMTM_ROOT, "output", "multi_backtest_results.json")


def ensure_dir(path: str) -> None:
    if path:
        os.makedirs(path, exist_ok=True)

def atomic_write_json(path: str, data: Dict[str, Any]) -> None:
    ensure_dir(os.path.dirname(path))
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)

def qdate_to_yyyy_mm_dd(d: QDate) -> str:
    return d.toString("yyyy-MM-dd")

def file_exists(path: str) -> bool:
    try:
        return bool(path) and os.path.exists(path)
    except Exception:
        return False


# --------------------------------------------------------------------------------------
# Presets
# --------------------------------------------------------------------------------------

PRESET_BALANCED: Dict[str, Any] = {
    "EMERGENCY_STOP_LOSS": 0.08,
    "EMERGENCY_STOP_MAX_BUY_COUNT": 2,
    "MAX_LOSS_AFTER_5TH": 0.02,
    "DRAWDOWN_THRESHOLDS": [0.0, 0.02, 0.03, 0.04, 0.05],
    "BUY_WEIGHTS": [7.0, 5.0, 3.6, 2.4, 2.0],
    "BUY_COOLDOWN_TICKS": 15,
    "VOL_SPIKE_FACTOR": 2.5,
    "VOL_MA_PERIOD": 20,
    "LATE_RSI_LIMIT": 60,
    "LATE_MACD_LIMIT": -250000,
    "LATE_STOCH_LIMIT": 2.5,
    "LATE_EMA_DISTANCE_MIN": 0.37,
    "BREAKEVEN_EXIT_THRESHOLDS": [0.01, 0.009, 0.008, 0.007, 0.006],
    "RALLY_START_PROFIT": 0.02,
    "RALLY_TRAIL_DROP": 0.01,
    "ATR_PERCENTILE": 40,
    "EMA_DISTANCE_PERCENT_MIN": 0.37,
    "SELL_COOLDOWN_TICKS": 5,
}

PRESET_SAFE: Dict[str, Any] = {
    "EMERGENCY_STOP_LOSS": 0.07,
    "EMERGENCY_STOP_MAX_BUY_COUNT": 2,
    "MAX_LOSS_AFTER_5TH": 0.018,
    "DRAWDOWN_THRESHOLDS": [0.0, 0.025, 0.035, 0.045, 0.055],
    "BUY_WEIGHTS": [6.5, 4.5, 3.2, 2.2, 1.8],
    "BUY_COOLDOWN_TICKS": 18,
    "VOL_SPIKE_FACTOR": 2.7,
    "VOL_MA_PERIOD": 22,
    "LATE_RSI_LIMIT": 58,
    "LATE_MACD_LIMIT": -260000,
    "LATE_STOCH_LIMIT": 2.3,
    "LATE_EMA_DISTANCE_MIN": 0.40,
    "BREAKEVEN_EXIT_THRESHOLDS": [0.009, 0.008, 0.007, 0.006, 0.005],
    "RALLY_START_PROFIT": 0.022,
    "RALLY_TRAIL_DROP": 0.009,
    "ATR_PERCENTILE": 45,
    "EMA_DISTANCE_PERCENT_MIN": 0.40,
    "SELL_COOLDOWN_TICKS": 7,
}

PRESET_AGGRESSIVE: Dict[str, Any] = {
    "EMERGENCY_STOP_LOSS": 0.09,
    "EMERGENCY_STOP_MAX_BUY_COUNT": 2,
    "MAX_LOSS_AFTER_5TH": 0.025,
    "DRAWDOWN_THRESHOLDS": [0.0, 0.015, 0.025, 0.035, 0.045],
    "BUY_WEIGHTS": [8.0, 6.0, 4.5, 3.0, 2.5],
    "BUY_COOLDOWN_TICKS": 12,
    "VOL_SPIKE_FACTOR": 2.2,
    "VOL_MA_PERIOD": 18,
    "LATE_RSI_LIMIT": 63,
    "LATE_MACD_LIMIT": -220000,
    "LATE_STOCH_LIMIT": 3.0,
    "LATE_EMA_DISTANCE_MIN": 0.32,
    "BREAKEVEN_EXIT_THRESHOLDS": [0.012, 0.010, 0.009, 0.008, 0.007],
    "RALLY_START_PROFIT": 0.018,
    "RALLY_TRAIL_DROP": 0.012,
    "ATR_PERCENTILE": 35,
    "EMA_DISTANCE_PERCENT_MIN": 0.33,
    "SELL_COOLDOWN_TICKS": 4,
}


# --------------------------------------------------------------------------------------
# Upbit helpers
# --------------------------------------------------------------------------------------

def fetch_upbit_krw_tickers(timeout=10) -> List[str]:
    r = requests.get(UPBIT_MARKETS_URL, params={"isDetails": "false"}, timeout=timeout)
    r.raise_for_status()
    data = r.json()
    tickers: List[str] = []
    for row in data:
        market = row.get("market", "")
        if market.startswith("KRW-"):
            tickers.append(market.split("-")[1])
    tickers.sort()
    return tickers

def fetch_upbit_topn_by_turnover(n: int, timeout=10) -> List[dict]:
    tickers = fetch_upbit_krw_tickers(timeout=timeout)
    markets = [f"KRW-{t}" for t in tickers]

    results: List[tuple] = []
    chunk_size = 100
    for i in range(0, len(markets), chunk_size):
        chunk = markets[i:i + chunk_size]
        r = requests.get(UPBIT_TICKER_URL, params={"markets": ",".join(chunk)}, timeout=timeout)
        r.raise_for_status()
        rows = r.json()
        for row in rows:
            m = row.get("market", "")
            if not m.startswith("KRW-"):
                continue
            ticker = m.split("-")[1]
            turnover = float(row.get("acc_trade_price_24h", 0.0))
            results.append((ticker, turnover))
        time.sleep(0.05)

    results.sort(key=lambda x: x[1], reverse=True)
    top = results[:max(1, int(n))]
    return [{"rank": idx + 1, "ticker": t, "turnover": v} for idx, (t, v) in enumerate(top)]


# --------------------------------------------------------------------------------------
# Backtest runner thread
# --------------------------------------------------------------------------------------

class BacktestRunnerThread(QThread):
    """Run backtest subprocess without crashing the UI.

    IMPORTANT:
    - QThread already has a built-in `finished()` signal (no args). Do NOT use that name.
    - We expose `finished_code(int)` for exit codes, and `log(str)` / `log_line(str)` for logs.
    """
    log = pyqtSignal(str)
    # compatibility alias (some older patches referenced log_line)
    log_line = pyqtSignal(str)
    finished_code = pyqtSignal(int)

    def __init__(self, cmd, cwd=None, parent=None):
        super().__init__(parent)
        self.cmd = cmd
        self.cwd = cwd
        self._stop_requested = False
        self.proc = None

    def request_stop(self):
        self._stop_requested = True
        try:
            if self.proc and self.proc.poll() is None:
                self.proc.terminate()
        except Exception:
            pass

    def _emit_log(self, msg: str):
        try:
            self.log.emit(msg)
        except Exception:
            pass
        try:
            self.log_line.emit(msg)
        except Exception:
            pass

    def run(self):
        import subprocess
        import os
        try:
            self._emit_log(f"[Runner] start: {' '.join(self.cmd)}")
            if self.cwd:
                self._emit_log(f"[Runner] cwd: {self.cwd}")
            # Use text mode for line streaming; fall back gracefully.
            self.proc = subprocess.Popen(
                self.cmd,
                cwd=self.cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding='utf-8',
                errors='replace',
                bufsize=1,
                universal_newlines=True,
            )

            # Stream stdout first (runner prints most info there)
            if self.proc.stdout:
                for line in self.proc.stdout:
                    if self._stop_requested:
                        break
                    line = (line or '').rstrip('\n')
                    if line:
                        self._emit_log(line)

            # Drain stderr at the end (avoid deadlock)
            err = ''
            if self.proc.stderr:
                try:
                    err = self.proc.stderr.read() or ''
                except Exception:
                    err = ''
            if err.strip():
                for ln in err.splitlines():
                    self._emit_log(f"[Runner][STDERR] {ln}")

            rc = self.proc.wait()
            self._emit_log(f"[Runner] done returncode={rc}")
            try:
                self.finished_code.emit(int(rc))
            except Exception:
                pass
        except Exception as e:
            self._emit_log(f"[Runner][ERR] {e}")
            try:
                self.finished_code.emit(99)
            except Exception:
                pass
class DryRunThread(QThread):
    # Dry-run: LIVE / NO ORDER
    # - 실전 1분봉을 가져와서 전략에 주입
    # - 전략이 만든 주문요청(request)만 JSONL로 기록 (실주문 금지)
    # - 옵션: Paper Fill(내부 가상체결)로 strategy.update_result()를 호출해 포지션 흐름을 따라감
    # - 중요: 지표/신호를 위해 최초 1회 warmup(과거 캔들 N개) 주입
    log = pyqtSignal(str)
    status = pyqtSignal(str)

    def __init__(self, smtm_root: str, tickers, interval_sec: int = 10, budget: float = 0.0, paper_fill: bool = False, warmup_count: int = 200, parent=None):
        super().__init__(parent)
        self.smtm_root = smtm_root
        self.tickers = [t.strip().upper() for t in (tickers or []) if t.strip()]
        self.interval_sec = max(3, int(interval_sec))
        self.budget = float(budget or 0.0)
        self.paper_fill = bool(paper_fill)
        self.warmup_count = max(50, int(warmup_count or 200))
        self._running = True
        self._last_kst = {}
        self._strategies = {}
        self._warmed = set()   # tickers warmed up
        self._strategy_code = "BBI-V3-SPEC-V16-VOL"

    def stop(self):
        self._running = False

    def _output_path(self) -> str:
        out_dir = os.path.join(self.smtm_root, "output")
        os.makedirs(out_dir, exist_ok=True)
        return os.path.join(out_dir, "live_dryrun_events.jsonl")

    def _append_event(self, evt: dict) -> None:
        try:
            path = self._output_path()
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(evt, ensure_ascii=False) + "\n")
        except Exception:
            pass

    def _ensure_sys_path(self):
        try:
            import sys
            if self.smtm_root and self.smtm_root not in sys.path:
                sys.path.insert(0, self.smtm_root)
        except Exception:
            pass

    def _fetch_candles(self, ticker: str, count: int = 1) -> list:
        # Returns list (most recent first for Upbit API). We'll reverse when feeding.
        market = f"KRW-{ticker}"
        try:
            self._ensure_sys_path()
            from smtm.data.upbit_data_provider import UpbitDataProvider
            dp = UpbitDataProvider(currency=ticker, interval=60)
            if hasattr(dp, "get_candles"):
                lst = dp.get_candles(count=count)
                return lst if isinstance(lst, list) else []
            if count == 1 and hasattr(dp, "get_latest_candle"):
                c = dp.get_latest_candle()
                return [c] if isinstance(c, dict) else []
        except Exception:
            pass

        import requests
        url = "https://api.upbit.com/v1/candles/minutes/1"
        r = requests.get(url, params={"market": market, "count": int(count)}, timeout=10)
        r.raise_for_status()
        data = r.json()
        return data if isinstance(data, list) else []

    def _fetch_last_candle(self, ticker: str) -> dict:
        lst = self._fetch_candles(ticker, count=1)
        return lst[0] if lst else {}

    def _to_primary_candle(self, c: dict) -> dict:
        kst = c.get("candle_date_time_kst") or c.get("date_time") or c.get("kst")
        return {
            "type": "primary_candle",
            "date_time": kst,
            "opening_price": c.get("opening_price"),
            "high_price": c.get("high_price"),
            "low_price": c.get("low_price"),
            "closing_price": c.get("trade_price"),
            "volume": c.get("candle_acc_trade_volume") if c.get("candle_acc_trade_volume") is not None else c.get("acc_trade_volume"),
            "candle_acc_trade_volume": c.get("candle_acc_trade_volume"),
            "acc_trade_volume": c.get("acc_trade_volume"),
        }

    def _get_strategy(self, ticker: str):
        if ticker in self._strategies:
            return self._strategies[ticker]

        self._ensure_sys_path()
        from smtm.strategy.strategy_factory import StrategyFactory
        s = StrategyFactory.create(self._strategy_code)
        if s is None:
            raise RuntimeError(f"StrategyFactory.create({self._strategy_code}) returned None")

        if hasattr(s, "is_simulation"):
            s.is_simulation = False

        # Budget guard: 0이면 request가 거의/아예 안 나올 수 있음 (BASE_POSITION_SIZE=0)
        init_budget = self.budget
        if init_budget <= 0:
            init_budget = 1_000_000.0
            self.log.emit(f"[DryRun][WARN] budget=0 -> default budget applied: {int(init_budget)} (주문은 여전히 0%)")

        try:
            s.initialize(budget=init_budget)
        except TypeError:
            s.initialize(init_budget)

        self._strategies[ticker] = s
        return s

    def _paper_fill(self, strategy, ticker: str, req: dict, kst: str, price: float):
        try:
            if req.get("type") not in ("buy", "sell"):
                return
            amt = float(req.get("amount") or 0)
            prc = float(req.get("price") or price or 0)
            if amt <= 0 or prc <= 0:
                return

            result = {
                "request": req,
                "state": "done",
                "type": req.get("type"),
                "price": prc,
                "amount": amt,
                "msg": "success",
            }
            if hasattr(strategy, "update_result"):
                strategy.update_result(result)

            self._append_event({
                "ts": datetime.datetime.now().isoformat(timespec="seconds"),
                "type": "paper_fill",
                "ticker": ticker,
                "kst": kst,
                "price": prc,
                "amount": amt,
                "request_id": req.get("id"),
                "side": req.get("type"),
            })
        except Exception as e:
            self.log.emit(f"[DryRun][WARN] paper_fill failed: {ticker}: {e}")

    def _warmup(self, ticker: str):
        if ticker in self._warmed:
            return
        strategy = self._get_strategy(ticker)

        candles = self._fetch_candles(ticker, count=self.warmup_count)
        if not candles:
            self.log.emit(f"[DryRun][WARN] warmup skipped (no candles): {ticker}")
            self._warmed.add(ticker)
            return

        # Upbit API returns recent->old; feed old->recent
        candles = list(reversed(candles))
        fed = 0
        for c in candles:
            if not self._running:
                break
            try:
                info = [self._to_primary_candle(c)]
                strategy.update_trading_info(info)
                fed += 1
            except Exception:
                # warmup errors shouldn't kill dryrun
                continue

        self._warmed.add(ticker)
        self.log.emit(f"[DryRun][Warmup] {ticker}: fed {fed} candles (count={self.warmup_count})")
        self._append_event({
            "ts": datetime.datetime.now().isoformat(timespec="seconds"),
            "type": "warmup_done",
            "ticker": ticker,
            "fed": fed,
            "warmup_count": self.warmup_count,
        })

    def run(self):
        if not self.tickers:
            self.status.emit("DRYRUN: no tickers")
            return

        self.status.emit(f"DRYRUN: starting ({','.join(self.tickers)})")
        self.log.emit(f"[DryRun] start: {','.join(self.tickers)} (주문 없음, 기록만)")
        self._append_event({
            "ts": datetime.datetime.now().isoformat(timespec="seconds"),
            "type": "dryrun_start",
            "tickers": self.tickers,
            "strategy_code": self._strategy_code,
            "budget": self.budget,
            "paper_fill": self.paper_fill,
            "warmup_count": self.warmup_count,
        })

        while self._running:
            for t in list(self.tickers):
                if not self._running:
                    break
                try:
                    # Warmup once per ticker
                    self._warmup(t)

                    c = self._fetch_last_candle(t)
                    if not c:
                        continue

                    kst = c.get("candle_date_time_kst") or c.get("kst") or c.get("datetime")
                    price = c.get("trade_price") or c.get("close") or c.get("price")

                    if kst and self._last_kst.get(t) == kst:
                        continue
                    if kst:
                        self._last_kst[t] = kst

                    self.log.emit(f"[DryRun] {t} kst={kst} price={price}")
                    self.status.emit(f"DRYRUN: running ({t})")
                    self._append_event({
                        "ts": datetime.datetime.now().isoformat(timespec="seconds"),
                        "type": "candle",
                        "ticker": t,
                        "kst": kst,
                        "price": price,
                        "candle": c,
                    })

                    strategy = self._get_strategy(t)
                    info = [self._to_primary_candle(c)]
                    strategy.update_trading_info(info)

                    reqs = strategy.get_request() if hasattr(strategy, "get_request") else None
                    if reqs:
                        if isinstance(reqs, dict):
                            reqs = [reqs]
                        normalized = []
                        for r in reqs:
                            if not isinstance(r, dict):
                                continue
                            if not r.get("id"):
                                r["id"] = f"dryrun-{uuid.uuid4().hex[:12]}"
                            normalized.append(r)

                        self._append_event({
                            "ts": datetime.datetime.now().isoformat(timespec="seconds"),
                            "type": "order_request",
                            "ticker": t,
                            "kst": kst,
                            "strategy_code": self._strategy_code,
                            "requests": normalized,
                        })
                        self.log.emit(f"[DryRun][REQ] {t} -> {len(normalized)} request(s)")

                        if self.paper_fill:
                            for r in normalized:
                                self._paper_fill(strategy, t, r, kst, float(price or 0))

                except Exception as e:
                    self.log.emit(f"[DryRun][ERR] {t}: {e}")
                    self._append_event({
                        "ts": datetime.datetime.now().isoformat(timespec="seconds"),
                        "type": "error",
                        "ticker": t,
                        "error": str(e),
                    })

            for _ in range(self.interval_sec):
                if not self._running:
                    break
                time.sleep(1)

        self.status.emit("DRYRUN: stopped")
        self.log.emit("[DryRun] stopped")
        self._append_event({
            "ts": datetime.datetime.now().isoformat(timespec="seconds"),
            "type": "dryrun_stop",
        })


class TuningMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("BBI V3 Spec v1.6 (Volume) - Tuning UI (Integrated Final)")
        self.resize(1400, 900)

        self.params: Dict[str, Any] = deepcopy(PRESET_BALANCED)
        self.widgets: Dict[str, Any] = {}

        self.runner: Optional[BacktestRunnerThread] = None
        # Live Readonly / DryRun UX guards
        self._ro_debounce_sec = 1.2
        self._ro_last_accounts_ts = 0.0
        self._ro_last_open_orders_ts = 0.0

        self._init_ui()
        self._apply_params_to_widgets()

    # ---------------- UI basics ----------------

    def _append_log(self, text: str):
        if hasattr(self, "bt_log") and self.bt_log is not None:
            # ✅ QPlainTextEdit 전용
            self.bt_log.appendPlainText(text)

    def _set_status(self, text: str, ms: int = 5000):
        if hasattr(self, "status_bar") and self.status_bar is not None:
            self.status_bar.showMessage(text, ms)

    def _init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)

        self.category_list = QListWidget()
        self.category_list.addItems([
            "Risk Control",
            "DCA / Scaling",
            "Volume Filters",
            "Take Profit / Rally",
            "Entry Filters",
            "Cooldown",
            "Backtest & Scan (Step 2-C)",
        ])
        self.category_list.setCurrentRow(0)
        self.category_list.currentRowChanged.connect(self._on_category_changed)

        self.stack = QStackedWidget()
        self._create_risk_page()
        self._create_dca_page()
        self._create_volume_page()
        self._create_tp_page()
        self._create_entry_page()
        self._create_cooldown_page()
        self._create_backtest_page()

        main_layout.addWidget(self.category_list, 1)
        main_layout.addWidget(self.stack, 4)

        self._create_menubar()
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        self._set_status("UI 로드 완료", 3000)

    def _create_menubar(self):
        menubar = QMenuBar()
        self.setMenuBar(menubar)

        file_menu = menubar.addMenu("파일")
        act_load = file_menu.addAction("설정 불러오기")
        act_save = file_menu.addAction("설정 저장하기")
        file_menu.addSeparator()
        act_exit = file_menu.addAction("종료")

        act_load.triggered.connect(self.action_load_settings)
        act_save.triggered.connect(self.action_save_settings)
        act_exit.triggered.connect(self.close)

        preset_menu = menubar.addMenu("프리셋")
        preset_menu.addAction("보수형 (SAFE)").triggered.connect(lambda: self.apply_preset("SAFE"))
        preset_menu.addAction("기본형 (BALANCED)").triggered.connect(lambda: self.apply_preset("BALANCED"))
        preset_menu.addAction("공격형 (AGGRESSIVE)").triggered.connect(lambda: self.apply_preset("AGGRESSIVE"))

    def _on_category_changed(self, index: int):
        self.stack.setCurrentIndex(index)

    # ---------------- Pages ----------------

    def _create_risk_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)

        group_es = QGroupBox("EMERGENCY_STOP_LOSS (1~2차 비상 손절 비율)")
        form_es = QFormLayout(group_es)
        slider_es = QSlider(Qt.Orientation.Horizontal)
        slider_es.setRange(6, 12)
        spin_es = QDoubleSpinBox()
        spin_es.setRange(0.06, 0.12)
        spin_es.setSingleStep(0.005)
        spin_es.setDecimals(3)

        slider_es.valueChanged.connect(lambda v: spin_es.setValue(v / 100.0))
        spin_es.valueChanged.connect(lambda v: (slider_es.setValue(int(v * 100)), self._set_param("EMERGENCY_STOP_LOSS", float(v))))

        form_es.addRow("값 (0.06~0.12):", spin_es)
        form_es.addRow("슬라이더:", slider_es)
        self.widgets["EMERGENCY_STOP_LOSS_spin"] = spin_es

        group_max5 = QGroupBox("MAX_LOSS_AFTER_5TH (5차 이후 확실 손절 비율)")
        form_max5 = QFormLayout(group_max5)
        slider_max5 = QSlider(Qt.Orientation.Horizontal)
        slider_max5.setRange(15, 40)
        spin_max5 = QDoubleSpinBox()
        spin_max5.setRange(0.015, 0.04)
        spin_max5.setSingleStep(0.001)
        spin_max5.setDecimals(3)

        slider_max5.valueChanged.connect(lambda v: spin_max5.setValue(v / 1000.0))
        spin_max5.valueChanged.connect(lambda v: (slider_max5.setValue(int(v * 1000)), self._set_param("MAX_LOSS_AFTER_5TH", float(v))))

        form_max5.addRow("값 (0.015~0.04):", spin_max5)
        form_max5.addRow("슬라이더:", slider_max5)
        self.widgets["MAX_LOSS_AFTER_5TH_spin"] = spin_max5

        group_cnt = QGroupBox("EMERGENCY_STOP_MAX_BUY_COUNT (비상 손절 적용 최대 차수)")
        form_cnt = QFormLayout(group_cnt)
        combo_cnt = QComboBox()
        combo_cnt.addItems(["1", "2", "3"])
        combo_cnt.currentIndexChanged.connect(lambda _: self._set_param("EMERGENCY_STOP_MAX_BUY_COUNT", int(combo_cnt.currentText())))
        form_cnt.addRow("최대 차수:", combo_cnt)
        self.widgets["EMERGENCY_STOP_MAX_BUY_COUNT_combo"] = combo_cnt

        layout.addWidget(group_es)
        layout.addWidget(group_max5)
        layout.addWidget(group_cnt)
        layout.addStretch()

        # ✅ 여기서는 DB 날짜 제한 적용 금지 (Backtest page에서 위젯 생성 후 적용)
        self.stack.addWidget(page)

    def _create_dca_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)

        group_dd = QGroupBox("DRAWDOWN_THRESHOLDS (차수별 최소 드로우다운)")
        vbox_dd = QVBoxLayout(group_dd)
        table_dd = QTableWidget(1, 5)
        table_dd.setHorizontalHeaderLabels(["1차 직전", "2차 직전", "3차 직전", "4차 직전", "5차 직전"])
        self.widgets["DRAWDOWN_THRESHOLDS_table"] = table_dd
        vbox_dd.addWidget(table_dd)

        group_bw = QGroupBox("BUY_WEIGHTS (차수별 물타기 비중)")
        vbox_bw = QVBoxLayout(group_bw)
        table_bw = QTableWidget(1, 5)
        table_bw.setHorizontalHeaderLabels(["1차", "2차", "3차", "4차", "5차"])
        self.widgets["BUY_WEIGHTS_table"] = table_bw
        vbox_bw.addWidget(table_bw)

        btn_save_bw = QPushButton("BUY_WEIGHTS 저장")
        btn_save_bw.clicked.connect(self._save_buy_weights_from_table)
        vbox_bw.addWidget(btn_save_bw)

        group_cd = QGroupBox("BUY_COOLDOWN_TICKS (매수-매수 최소 간격)")
        form_cd = QFormLayout(group_cd)
        spin_cd = QSpinBox()
        spin_cd.setRange(1, 1000)
        spin_cd.valueChanged.connect(lambda v: self._set_param("BUY_COOLDOWN_TICKS", int(v)))
        form_cd.addRow("틱 수:", spin_cd)
        self.widgets["BUY_COOLDOWN_TICKS_spin"] = spin_cd

        layout.addWidget(group_dd)
        layout.addWidget(group_bw)
        layout.addWidget(group_cd)
        layout.addStretch()
        self.stack.addWidget(page)

    def _create_volume_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)

        group_vs = QGroupBox("VOL_SPIKE_FACTOR (볼륨 스파이크 배수)")
        form_vs = QFormLayout(group_vs)
        slider_vs = QSlider(Qt.Orientation.Horizontal)
        slider_vs.setRange(15, 40)
        spin_vs = QDoubleSpinBox()
        spin_vs.setRange(1.5, 4.0)
        spin_vs.setSingleStep(0.1)

        slider_vs.valueChanged.connect(lambda v: spin_vs.setValue(v / 10.0))
        spin_vs.valueChanged.connect(lambda v: (slider_vs.setValue(int(v * 10)), self._set_param("VOL_SPIKE_FACTOR", float(v))))

        form_vs.addRow("값:", spin_vs)
        form_vs.addRow("슬라이더:", slider_vs)
        self.widgets["VOL_SPIKE_FACTOR_spin"] = spin_vs

        group_vp = QGroupBox("VOL_MA_PERIOD (볼륨 평균 기간)")
        form_vp = QFormLayout(group_vp)
        spin_vp = QSpinBox()
        spin_vp.setRange(5, 500)
        spin_vp.valueChanged.connect(lambda v: self._set_param("VOL_MA_PERIOD", int(v)))
        form_vp.addRow("기간:", spin_vp)
        self.widgets["VOL_MA_PERIOD_spin"] = spin_vp

        layout.addWidget(group_vs)
        layout.addWidget(group_vp)
        layout.addStretch()
        self.stack.addWidget(page)

    def _create_tp_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)

        group_tp = QGroupBox("BREAKEVEN_EXIT_THRESHOLDS (차수별 TP)")
        vbox_tp = QVBoxLayout(group_tp)
        table_tp = QTableWidget(1, 5)
        table_tp.setHorizontalHeaderLabels(["1차", "2차", "3차", "4차", "5차"])
        self.widgets["BREAKEVEN_EXIT_THRESHOLDS_table"] = table_tp
        vbox_tp.addWidget(table_tp)

        btn_save_tp = QPushButton("TP 저장")
        btn_save_tp.clicked.connect(self._save_tp_from_table)
        vbox_tp.addWidget(btn_save_tp)

        group_rs = QGroupBox("RALLY_START_PROFIT")
        form_rs = QFormLayout(group_rs)
        spin_rs = QDoubleSpinBox()
        spin_rs.setRange(0.001, 0.2)
        spin_rs.setDecimals(3)
        spin_rs.valueChanged.connect(lambda v: self._set_param("RALLY_START_PROFIT", float(v)))
        form_rs.addRow("값:", spin_rs)
        self.widgets["RALLY_START_PROFIT_spin"] = spin_rs

        group_rt = QGroupBox("RALLY_TRAIL_DROP")
        form_rt = QFormLayout(group_rt)
        spin_rt = QDoubleSpinBox()
        spin_rt.setRange(0.001, 0.2)
        spin_rt.setDecimals(3)
        spin_rt.valueChanged.connect(lambda v: self._set_param("RALLY_TRAIL_DROP", float(v)))
        form_rt.addRow("값:", spin_rt)
        self.widgets["RALLY_TRAIL_DROP_spin"] = spin_rt

        layout.addWidget(group_tp)
        layout.addWidget(group_rs)
        layout.addWidget(group_rt)
        layout.addStretch()
        self.stack.addWidget(page)

    def _create_entry_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)

        group_atr = QGroupBox("ATR_PERCENTILE")
        form_atr = QFormLayout(group_atr)
        spin_atr = QSpinBox()
        spin_atr.setRange(1, 99)
        spin_atr.valueChanged.connect(lambda v: self._set_param("ATR_PERCENTILE", int(v)))
        form_atr.addRow("값:", spin_atr)
        self.widgets["ATR_PERCENTILE_spin"] = spin_atr

        group_ema = QGroupBox("EMA_DISTANCE_PERCENT_MIN")
        form_ema = QFormLayout(group_ema)
        spin_ema = QDoubleSpinBox()
        spin_ema.setRange(0.01, 2.0)
        spin_ema.setDecimals(3)
        spin_ema.valueChanged.connect(lambda v: self._set_param("EMA_DISTANCE_PERCENT_MIN", float(v)))
        form_ema.addRow("값:", spin_ema)
        self.widgets["EMA_DISTANCE_PERCENT_MIN_spin"] = spin_ema

        layout.addWidget(group_atr)
        layout.addWidget(group_ema)
        layout.addStretch()
        self.stack.addWidget(page)

    def _create_cooldown_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)

        group_buy = QGroupBox("BUY_COOLDOWN_TICKS")
        form_buy = QFormLayout(group_buy)
        spin_buy = QSpinBox()
        spin_buy.setRange(1, 2000)
        spin_buy.valueChanged.connect(lambda v: self._set_param("BUY_COOLDOWN_TICKS", int(v)))
        form_buy.addRow("틱 수:", spin_buy)
        self.widgets["BUY_COOLDOWN_TICKS_spin2"] = spin_buy

        group_sell = QGroupBox("SELL_COOLDOWN_TICKS")
        form_sell = QFormLayout(group_sell)
        spin_sell = QSpinBox()
        spin_sell.setRange(0, 2000)
        spin_sell.valueChanged.connect(lambda v: self._set_param("SELL_COOLDOWN_TICKS", int(v)))
        form_sell.addRow("틱 수:", spin_sell)
        self.widgets["SELL_COOLDOWN_TICKS_spin"] = spin_sell

        layout.addWidget(group_buy)
        layout.addWidget(group_sell)
        layout.addStretch()
        self.stack.addWidget(page)

    # ---------------- Backtest page ----------------

    def _create_backtest_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)

        group_scan = QGroupBox("업비트 코인 스캔 / 거래대금 TOP N")
        scan_layout = QVBoxLayout(group_scan)

        row1 = QHBoxLayout()
        self.combo_coin = QComboBox()
        self.combo_coin.setEditable(True)
        self.combo_coin.addItem("BTC")
        self.combo_coin.currentTextChanged.connect(self._on_coin_changed)

        self.spin_topn = QSpinBox()
        self.spin_topn.setRange(5, 200)
        self.spin_topn.setValue(30)

        self.btn_load_topn = QPushButton("Top N 로드")
        self.btn_load_topn.clicked.connect(self._on_load_topn_clicked)

        self.btn_refresh_markets = QPushButton("마켓 목록 새로고침")
        self.btn_refresh_markets.clicked.connect(self._on_refresh_markets_clicked)

        row1.addWidget(QLabel("코인:"))
        row1.addWidget(self.combo_coin, 2)
        row1.addWidget(QLabel("Top N:"))
        row1.addWidget(self.spin_topn)
        row1.addWidget(self.btn_load_topn)
        row1.addWidget(self.btn_refresh_markets)
        scan_layout.addLayout(row1)

        self.table_topn = QTableWidget(0, 3)
        self.table_topn.setHorizontalHeaderLabels(["Rank", "Ticker", "거래대금"])
        self.table_topn.cellClicked.connect(self._on_topn_table_clicked)
        scan_layout.addWidget(self.table_topn)

        layout.addWidget(group_scan)

        group_bt = QGroupBox("백테스트 (Step 2-C: 실제 실행)")
        bt_layout = QVBoxLayout(group_bt)
        form = QFormLayout()

        self.bt_start_date = QDateEdit()
        self.bt_start_date.setCalendarPopup(True)
        self.bt_start_date.setDate(QDate.currentDate().addMonths(-1))

        self.bt_end_date = QDateEdit()
        self.bt_end_date.setCalendarPopup(True)
        self.bt_end_date.setDate(QDate.currentDate())

        # ✅ 이제 위젯이 있으니 DB date range 제한 적용 가능
        self._apply_db_date_limits()

        self.bt_timeframe_combo = QComboBox()
        self.bt_timeframe_combo.addItems(["1m", "3m", "5m", "15m", "1h"])

        self.bt_budget_spin = QSpinBox()
        self.bt_budget_spin.setRange(10_000, 1_000_000_000)
        self.bt_budget_spin.setValue(1_000_000)
        self.bt_budget_spin.setSingleStep(10_000)

        self.bt_data_path_edit = QLineEdit("")
        btn_browse = QPushButton("파일 선택...")
        btn_browse.clicked.connect(self._browse_data_file)
        hbox_data = QHBoxLayout()
        hbox_data.addWidget(self.bt_data_path_edit)
        hbox_data.addWidget(btn_browse)

        self._bt_cmd_template_default = (
            "{python} -m smtm.runner.multi_backtest_runner "
            "--ticker {ticker} --start {start} --end {end} --tf {tf} --budget {budget} "
            "--tuning {tuning} {data_opt} --out {out}"
        )

        self.bt_cmd_template = QLineEdit()
        self.bt_cmd_template.setText(self._bt_cmd_template_default)

        self.bt_results_path = QLineEdit(DEFAULT_RESULTS_JSON)

        form.addRow("시작일:", self.bt_start_date)
        form.addRow("종료일:", self.bt_end_date)
        form.addRow("타임프레임:", self.bt_timeframe_combo)
        form.addRow("예산:", self.bt_budget_spin)
        form.addRow("데이터 파일(옵션):", hbox_data)
        form.addRow("실행 명령 템플릿:", self.bt_cmd_template)
        form.addRow("결과 JSON 경로:", self.bt_results_path)

        bt_layout.addLayout(form)

        row_btns = QHBoxLayout()
        self.bt_run_button = QPushButton("현재 파라미터로 백테스트 실행")
        self.bt_run_button.clicked.connect(self._run_backtest_clicked)

        self.bt_stop_button = QPushButton("중지(프로세스 종료)")
        self.bt_stop_button.clicked.connect(self._stop_backtest_clicked)
        self.bt_stop_button.setEnabled(False)

        self.bt_load_results_button = QPushButton("결과 JSON 로드/요약")
        self.bt_load_results_button.clicked.connect(self._load_results_clicked)

        self.bt_reset_template_button = QPushButton("템플릿 기본값 복원")
        self.bt_reset_template_button.clicked.connect(self._reset_cmd_template_clicked)

        row_btns.addWidget(self.bt_run_button)
        row_btns.addWidget(self.bt_stop_button)
        row_btns.addWidget(self.bt_load_results_button)
        row_btns.addWidget(self.bt_reset_template_button)

        self.bt_open_last_button = QPushButton("마지막 차트/CSV 열기")
        self.bt_open_last_button.clicked.connect(self._open_last_artifacts)
        row_btns.addWidget(self.bt_open_last_button)

        self.bt_open_json_button = QPushButton("결과 JSON 열기")
        self.bt_open_json_button.clicked.connect(lambda: self._open_path_with_default_app(
            os.path.abspath(self.bt_results_path.text().strip() or DEFAULT_RESULTS_JSON)
        ))
        row_btns.addWidget(self.bt_open_json_button)

        bt_layout.addLayout(row_btns)


        # ===== Live Preflight (업비트 실전 점검) =====
        gb_live = QGroupBox("Live Preflight (업비트 실전 점검)")
        live_layout = QVBoxLayout()

        row_live_btns = QHBoxLayout()
        self.bt_live_env_check = QPushButton("1) 환경변수 점검")
        self.bt_live_public_ping = QPushButton("2) 시세 API 테스트")
        self.bt_live_refresh_markets = QPushButton("3) KRW 마켓 갱신")
        self.bt_live_private_account = QPushButton("4) 계좌 조회 테스트(키)")

        row_live_btns.addWidget(self.bt_live_env_check)
        row_live_btns.addWidget(self.bt_live_public_ping)
        row_live_btns.addWidget(self.bt_live_refresh_markets)
        row_live_btns.addWidget(self.bt_live_private_account)

        live_layout.addLayout(row_live_btns)

        # Live Readonly (조회 전용, 주문 없음)
        row_live_ro = QHBoxLayout()
        self.bt_live_ro_accounts = QPushButton("5) 잔고/보유 조회(Readonly)")
        self.bt_live_ro_open_orders = QPushButton("6) 미체결 조회(Readonly)")
        row_live_ro.addWidget(self.bt_live_ro_accounts)
        row_live_ro.addWidget(self.bt_live_ro_open_orders)
        live_layout.addLayout(row_live_ro)

        # LIVE ARM 게이트 (7단계: 아직 주문 버튼 없음. 향후 실전 버튼 연결 전, 이 게이트를 반드시 통과해야 함)
        row_live_arm = QHBoxLayout()
        self.cb_live_arm = QCheckBox("LIVE ARM (실전 주문 허용 게이트)")
        self.cb_live_arm.setChecked(False)
        row_live_arm.addWidget(self.cb_live_arm)

        row_live_arm.addWidget(QLabel("확인 문구:"))
        self.le_live_arm_phrase = QLineEdit()
        self.le_live_arm_phrase.setPlaceholderText("LIVE-ORDER-ENABLE")
        row_live_arm.addWidget(self.le_live_arm_phrase)

        row_live_arm.addWidget(QLabel("1회 주문한도(KRW):"))
        self.le_live_max_order_krw = QLineEdit()
        self.le_live_max_order_krw.setPlaceholderText("예: 30000")
        row_live_arm.addWidget(self.le_live_max_order_krw)

        row_live_arm.addWidget(QLabel("일 손실한도(KRW):"))
        self.le_live_daily_loss_krw = QLineEdit()
        self.le_live_daily_loss_krw.setPlaceholderText("예: 100000")
        row_live_arm.addWidget(self.le_live_daily_loss_krw)

        live_layout.addLayout(row_live_arm)

        self.lb_live_arm_status = QLabel("LIVE ARM: DISARMED (주문 차단)")
        live_layout.addWidget(self.lb_live_arm_status)

        self.te_live_readonly = QPlainTextEdit()
        self.te_live_readonly.setReadOnly(True)
        self.te_live_readonly.setMaximumHeight(120)
        self.lb_live_hint = QLabel("※ 이번 단계는 '점검'만 합니다. (주문/체결 없음)")
        live_layout.addWidget(self.lb_live_hint)


        # READY 상태 표시
        self.lb_live_ready = QLabel("READY: (미평가)")
        live_layout.addWidget(self.lb_live_ready)

        # 프로파일 저장/불러오기 (실전 설정 보관)
        row_live_profile = QHBoxLayout()
        self.bt_live_save_profile = QPushButton("프로파일 저장")
        self.bt_live_load_profile = QPushButton("프로파일 불러오기")
        row_live_profile.addWidget(self.bt_live_save_profile)
        row_live_profile.addWidget(self.bt_live_load_profile)
        live_layout.addLayout(row_live_profile)


        # Dry-run (주문 없이 실전 캔들만 기록)
        row_dryrun = QHBoxLayout()
        row_dryrun.addWidget(QLabel("Dry-run 코인(쉼표):"))
        self.le_dryrun_tickers = QLineEdit()
        self.le_dryrun_tickers.setPlaceholderText("예: BTC,ETH,XRP")
        row_dryrun.addWidget(self.le_dryrun_tickers)

        self.cb_dryrun_paper_fill = QCheckBox("Paper Fill(가상체결)")
        self.cb_dryrun_paper_fill.setChecked(False)
        row_dryrun.addWidget(self.cb_dryrun_paper_fill)

        self.bt_dryrun_start = QPushButton("Dry-run 시작")
        self.bt_dryrun_stop = QPushButton("Dry-run 중지")
        self.bt_dryrun_stop.setEnabled(False)
        row_dryrun.addWidget(self.bt_dryrun_start)
        row_dryrun.addWidget(self.bt_dryrun_stop)
        live_layout.addLayout(row_dryrun)

        self.lb_dryrun_status = QLabel("DRYRUN: (stopped)")
        live_layout.addWidget(self.lb_dryrun_status)

        gb_live.setLayout(live_layout)

        # Step 2-C 영역 레이아웃에 붙이기 (가능한 경우)
        try:
            main_layout.addWidget(gb_live)
        except Exception:
            try:
                layout.addWidget(gb_live)
            except Exception:
                pass

        # ---------------- Output Tabs (Backtest / Live / Artifacts) ----------------
        self.bt_log = QPlainTextEdit()
        self.bt_log.setReadOnly(True)

        # Live 로그는 별도 탭으로 분리 (실주문/체결 없음: readonly)
        # te_live_readonly는 위에서 생성되며, 여기서 탭에 붙입니다.

        self.te_artifacts = QPlainTextEdit()
        self.te_artifacts.setReadOnly(True)
        # Auto-refresh artifacts once UI is ready
        try:
            QTimer.singleShot(0, self._refresh_artifacts_view)
        except Exception:
            pass
        self.te_artifacts.setMaximumBlockCount(1000)

        self.bt_artifacts_refresh = QPushButton("Artifacts 새로고침")
        self.bt_open_output_dir_button = QPushButton("output 폴더 열기")
        self.bt_open_result_dir_button = QPushButton("result 폴더 열기")
        self.bt_open_output_dir_button.clicked.connect(self._open_output_dir)
        self.bt_open_result_dir_button.clicked.connect(self._open_result_dir)
        self.bt_artifacts_refresh.clicked.connect(self._refresh_artifacts_view)

        # 초기 1회: 현재 output/result 상태를 바로 표시
        try:
            self._refresh_artifacts_view()
        except Exception:
            pass

        tabs = QTabWidget()

        # Tab 1: Backtest Console
        w_console = QWidget()
        v_console = QVBoxLayout(w_console)
        v_console.setContentsMargins(0, 0, 0, 0)
        v_console.addWidget(self.bt_log)
        tabs.addTab(w_console, "Backtest Log")

        # Tab 2: Live Console
        w_live = QWidget()
        v_live = QVBoxLayout(w_live)
        v_live.setContentsMargins(0, 0, 0, 0)
        v_live.addWidget(self.te_live_readonly)
        tabs.addTab(w_live, "Live Log")

        # Tab 3: Artifacts Summary
        w_art = QWidget()
        v_art = QVBoxLayout(w_art)
        v_art.setContentsMargins(0, 0, 0, 0)
        row_art = QHBoxLayout()
        row_art.addWidget(self.bt_artifacts_refresh)
        row_art.addWidget(self.bt_open_output_dir_button)
        row_art.addWidget(self.bt_open_result_dir_button)
        row_art.addStretch()
        v_art.addLayout(row_art)
        v_art.addWidget(self.te_artifacts)
        tabs.addTab(w_art, "Artifacts")

        bt_layout.addWidget(QLabel("로그 / 산출물:"))
        bt_layout.addWidget(tabs)

        # 최초 1회 갱신
        self._refresh_artifacts_view()

        layout.addWidget(group_bt)
        layout.addStretch()
        self.stack.addWidget(page)
#***************************************************************************************************

        # Live Preflight 버튼 연결
        self.bt_live_env_check.clicked.connect(self._live_env_check)
        self.bt_live_public_ping.clicked.connect(self._live_public_ping)
        self.bt_live_refresh_markets.clicked.connect(self._live_refresh_markets)
        self.bt_live_private_account.clicked.connect(self._live_private_account_check)
        self.bt_live_ro_accounts.clicked.connect(self._live_ro_accounts)
        self.bt_live_ro_open_orders.clicked.connect(self._live_ro_open_orders)
        self.cb_live_arm.toggled.connect(self._live_arm_toggled)
        self.le_live_arm_phrase.textChanged.connect(self._live_arm_toggled)
        self.le_live_max_order_krw.textChanged.connect(self._live_arm_toggled)
        self.le_live_daily_loss_krw.textChanged.connect(self._live_arm_toggled)


        self.bt_live_save_profile.clicked.connect(self._live_save_profile)
        self.bt_live_load_profile.clicked.connect(self._live_load_profile)


        self.bt_dryrun_start.clicked.connect(self._dryrun_start)
        self.bt_dryrun_stop.clicked.connect(self._dryrun_stop)

        row_btns.addWidget(self.bt_open_output_dir_button)


#***************************************************************************************************


    # ---------------- Param binding ----------------

    def _apply_params_to_widgets(self):
        p = self.params
        self.widgets["EMERGENCY_STOP_LOSS_spin"].setValue(p["EMERGENCY_STOP_LOSS"])
        self.widgets["MAX_LOSS_AFTER_5TH_spin"].setValue(p["MAX_LOSS_AFTER_5TH"])
        self.widgets["EMERGENCY_STOP_MAX_BUY_COUNT_combo"].setCurrentIndex(["1", "2", "3"].index(str(p["EMERGENCY_STOP_MAX_BUY_COUNT"])))

        self._params_to_dd_table()
        self._params_to_bw_table()
        self.widgets["BUY_COOLDOWN_TICKS_spin"].setValue(p["BUY_COOLDOWN_TICKS"])

        self._params_to_tp_table()
        self.widgets["RALLY_START_PROFIT_spin"].setValue(p["RALLY_START_PROFIT"])
        self.widgets["RALLY_TRAIL_DROP_spin"].setValue(p["RALLY_TRAIL_DROP"])

        self.widgets["ATR_PERCENTILE_spin"].setValue(p["ATR_PERCENTILE"])
        self.widgets["EMA_DISTANCE_PERCENT_MIN_spin"].setValue(p["EMA_DISTANCE_PERCENT_MIN"])

        self.widgets["BUY_COOLDOWN_TICKS_spin2"].setValue(p["BUY_COOLDOWN_TICKS"])
        self.widgets["SELL_COOLDOWN_TICKS_spin"].setValue(p["SELL_COOLDOWN_TICKS"])
        self._update_status()

    def _params_to_dd_table(self):
        table = self.widgets["DRAWDOWN_THRESHOLDS_table"]
        vals = self.params.get("DRAWDOWN_THRESHOLDS", [0, 0, 0, 0, 0])
        for i, v in enumerate(vals):
            table.setItem(0, i, QTableWidgetItem(f"{float(v):.3f}"))

    def _params_to_bw_table(self):
        table = self.widgets["BUY_WEIGHTS_table"]
        vals = self.params.get("BUY_WEIGHTS", [0, 0, 0, 0, 0])
        for i, v in enumerate(vals):
            table.setItem(0, i, QTableWidgetItem(f"{float(v):.2f}"))

    def _params_to_tp_table(self):
        table = self.widgets["BREAKEVEN_EXIT_THRESHOLDS_table"]
        vals = self.params.get("BREAKEVEN_EXIT_THRESHOLDS", [0, 0, 0, 0, 0])
        for i, v in enumerate(vals):
            table.setItem(0, i, QTableWidgetItem(f"{float(v) * 100:.3f}"))

    def _set_param(self, key: str, value: Any):
        self.params[key] = value
        self._update_status()

    def _save_buy_weights_from_table(self):
        table = self.widgets["BUY_WEIGHTS_table"]
        vals: List[float] = []
        for col in range(5):
            item = table.item(0, col)
            if item is None:
                QMessageBox.warning(self, "오류", "BUY_WEIGHTS 값이 비었습니다.")
                return
            try:
                vals.append(float(item.text()))
            except Exception:
                QMessageBox.warning(self, "오류", "BUY_WEIGHTS 값이 잘못되었습니다.")
                return
        self.params["BUY_WEIGHTS"] = vals
        self._update_status()

    def _save_tp_from_table(self):
        table = self.widgets["BREAKEVEN_EXIT_THRESHOLDS_table"]
        vals: List[float] = []
        for col in range(5):
            item = table.item(0, col)
            if item is None:
                QMessageBox.warning(self, "오류", "TP 값이 비었습니다.")
                return
            try:
                txt = item.text().replace("%", "")
                v = float(txt)
                vals.append(v / 100.0 if v > 1 else v)
            except Exception:
                QMessageBox.warning(self, "오류", "TP 값이 잘못되었습니다.")
                return
        self.params["BREAKEVEN_EXIT_THRESHOLDS"] = vals
        self._update_status()

    def apply_preset(self, name: str):
        if name == "SAFE":
            self.params = deepcopy(PRESET_SAFE)
            msg = "SAFE 프리셋 적용"
        elif name == "AGGRESSIVE":
            self.params = deepcopy(PRESET_AGGRESSIVE)
            msg = "AGGRESSIVE 프리셋 적용"
        else:
            self.params = deepcopy(PRESET_BALANCED)
            msg = "BALANCED 프리셋 적용"
        self._apply_params_to_widgets()
        self._set_status(msg)

    def action_load_settings(self):
        path, _ = QFileDialog.getOpenFileName(self, "설정 파일 열기", "", "JSON Files (*.json);;All Files (*)")
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.params.update(data)
            self._apply_params_to_widgets()
            self._set_status(f"설정 로드: {path}")
        except Exception as e:
            QMessageBox.critical(self, "오류", f"설정 로드 실패: {e}")

    def action_save_settings(self):
        path, _ = QFileDialog.getSaveFileName(self, "설정 파일 저장", "", "JSON Files (*.json);;All Files (*)")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.params, f, indent=2, ensure_ascii=False)
            self._set_status(f"설정 저장: {path}")
        except Exception as e:
            QMessageBox.critical(self, "오류", f"설정 저장 실패: {e}")

    # ---------------- Scan handlers ----------------

    def _on_refresh_markets_clicked(self):
        try:
            self._set_status("업비트 KRW 마켓 목록 로드 중...", 5000)
            tickers = fetch_upbit_krw_tickers()
            self.combo_coin.clear()
            self.combo_coin.addItems(tickers)
            self._set_status(f"KRW 마켓 {len(tickers)}개 로드 완료", 5000)
        except Exception as e:
            QMessageBox.critical(self, "코인 로드 실패", str(e))
            self._set_status("코인 로드 실패", 5000)

    def _on_load_topn_clicked(self):
        try:
            n = int(self.spin_topn.value())
            self._set_status(f"거래대금 TOP {n} 로드 중...", 5000)

            self.table_topn.setRowCount(0)
            top = fetch_upbit_topn_by_turnover(n)

            self.table_topn.setRowCount(len(top))
            for r, row in enumerate(top):
                self.table_topn.setItem(r, 0, QTableWidgetItem(str(row["rank"])))
                self.table_topn.setItem(r, 1, QTableWidgetItem(row["ticker"]))
                self.table_topn.setItem(r, 2, QTableWidgetItem(f'{row["turnover"]:,.0f}'))

            self.combo_coin.clear()
            self.combo_coin.addItems([x["ticker"] for x in top])

            self._set_status(f"거래대금 TOP {n} 로드 완료", 5000)
        except Exception as e:
            QMessageBox.critical(self, "Top N 로드 실패", str(e))
            self._set_status("Top N 로드 실패", 5000)

    def _on_topn_table_clicked(self, row: int, col: int):
        item = self.table_topn.item(row, 1)
        if not item:
            return
        self.combo_coin.setCurrentText(item.text().strip())

    def _on_coin_changed(self, text: str):
        if text.strip():
            self._set_status(f"선택 코인: {text.strip()}", 1500)

    # ---------------- Backtest wiring ----------------

    def _browse_data_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "시뮬레이션 데이터 파일 선택", "", "All Files (*)")
        if path:
            self.bt_data_path_edit.setText(path)

    def _reset_cmd_template_clicked(self):
        self.bt_cmd_template.setText(self._bt_cmd_template_default)
        self._append_log("[UI] 실행 명령 템플릿을 기본값으로 복원했습니다.")

    def _disable_controls_while_running(self, running: bool):
        self.btn_load_topn.setEnabled(not running)
        self.btn_refresh_markets.setEnabled(not running)
        self.combo_coin.setEnabled(not running)
        self.spin_topn.setEnabled(not running)

        self.bt_run_button.setEnabled(not running)
        self.bt_stop_button.setEnabled(running)
        self.bt_load_results_button.setEnabled(not running)
        self.bt_reset_template_button.setEnabled(not running)

        self.bt_start_date.setEnabled(not running)
        self.bt_end_date.setEnabled(not running)
        self.bt_timeframe_combo.setEnabled(not running)
        self.bt_budget_spin.setEnabled(not running)
        self.bt_data_path_edit.setEnabled(not running)
        self.bt_cmd_template.setEnabled(not running)
        self.bt_results_path.setEnabled(not running)
        self.bt_open_last_button.setEnabled(not running)
        self.bt_open_json_button.setEnabled(not running)
        self.bt_open_output_dir_button.setEnabled(not running)


    def _build_tuning_payload(self) -> Dict[str, Any]:
        return {
            "STRATEGY_CODE": STRATEGY_CODE,
            "PARAMS": deepcopy(self.params),
            "META": {
                "generated_by": "ui_tuning_simulator_integrated_final",
                "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            },
        }

    def _resolve_tuning_path(self) -> str:
        return os.path.join(SMTM_ROOT, TUNING_FILE_NAME)

    def _run_backtest_clicked(self):
        if self.runner is not None and self.runner.isRunning():
            QMessageBox.warning(self, "실행 중", "이미 백테스트가 실행 중입니다.")
            return

        tuning_path = os.path.abspath(self._resolve_tuning_path())
        results_path = os.path.abspath(self.bt_results_path.text().strip() or DEFAULT_RESULTS_JSON)

        ensure_dir(os.path.dirname(results_path))
        ensure_dir(os.path.join(SMTM_ROOT, "output"))
        ensure_dir(os.path.join(SMTM_ROOT, "result"))

        runner_py = os.path.join(SMTM_ROOT, "smtm", "runner", "multi_backtest_runner.py")

        payload = self._build_tuning_payload()
        try:
            atomic_write_json(tuning_path, payload)
        except Exception as e:
            QMessageBox.critical(self, "튜닝 파일 생성 실패", str(e))
            return

        ticker = self.combo_coin.currentText().strip()
        if not ticker:
            QMessageBox.warning(self, "입력 오류", "코인을 선택하세요.")
            return

        start = qdate_to_yyyy_mm_dd(self.bt_start_date.date())
        end = qdate_to_yyyy_mm_dd(self.bt_end_date.date())
        tf = self.bt_timeframe_combo.currentText().strip()
        budget = str(int(self.bt_budget_spin.value()))
        data_file = self.bt_data_path_edit.text().strip()

        data_opt = ""
        if data_file:
            data_file = os.path.abspath(data_file)
            data_opt = f'--data "{data_file}"'

        template = self.bt_cmd_template.text().strip()
        if not template:
            QMessageBox.warning(self, "입력 오류", "실행 명령 템플릿이 비었습니다.")
            return

        ctx = {
            "python": sys.executable,
            "root": SMTM_ROOT,
            "ticker": ticker,
            "dryrun_tickers": (self.le_dryrun_tickers.text().strip() if hasattr(self, "le_dryrun_tickers") else ""),
            "dryrun_paper_fill": (bool(self.cb_dryrun_paper_fill.isChecked()) if hasattr(self, "cb_dryrun_paper_fill") else False),
            "start": start,
            "end": end,
            "tf": tf,
            "budget": budget,
            "tuning": tuning_path,
            "data": data_file,
            "data_opt": data_opt,
            "out": results_path,
        }

        try:
            cmd_str = template.format(**ctx)
            import shlex
            cmd = shlex.split(cmd_str, posix=(os.name != "nt"))
        except Exception as e:
            QMessageBox.critical(self, "명령 생성 실패", f"{e}\n\n템플릿:\n{template}")
            return

        self.bt_log.clear()
        self._append_log(f"[UI] SMTM_ROOT = {SMTM_ROOT}")
        self._append_log(f"[UI] sys.executable = {sys.executable}")
        self._append_log(f"[UI] runner_py exists = {file_exists(runner_py)}  ({runner_py})")
        self._append_log(f"[Step 2-C] tuning json 생성: {tuning_path}")
        self._append_log(f"[Step 2-C] 결과 파일: {results_path}")
        self._append_log(f"[Step 2-C] 실행 명령: {' '.join(cmd)}")

        self._set_status("백테스트 실행 중입니다...", 5000)
        self._disable_controls_while_running(True)

        self.runner = BacktestRunnerThread(cmd=cmd, cwd=SMTM_ROOT)
        self.runner.log.connect(self._append_log)
        self.runner.finished_code.connect(self._on_runner_finished)
        self.runner.start()

    def _stop_backtest_clicked(self):
        if self.runner is None:
            return
        self._append_log("[Step 2-C] 사용자 요청으로 프로세스를 종료합니다...")
        self._set_status("프로세스 종료 중...", 3000)
        self.runner.stop()

    def _on_runner_finished(self, exit_code: int):
        self._append_log(f"[Step 2-C] 종료: exit_code={exit_code}")
        self._disable_controls_while_running(False)

        results_path = os.path.abspath(self.bt_results_path.text().strip() or DEFAULT_RESULTS_JSON)
        if results_path and os.path.exists(results_path):
            self._append_log(f"[Step 2-C] 결과 JSON 발견: {results_path}")
            self._append_log(self._summarize_results_file(results_path))
            self._set_status("백테스트 종료 (결과 요약 로드 완료)", 5000)
        else:
            self._append_log(f"[Step 2-C] 결과 JSON 없음: {results_path}")
            self._set_status("백테스트 종료", 5000)

        self.runner = None

        self._preflight_state = {'env_ok': False, 'public_ok': False, 'markets_ok': False, 'private_ok': False, 'private_blocked': False, 'last': None}
        setattr(self, 'dryrun_thread', None)
    def _summarize_results_file(self, path: str) -> str:
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            return f"[요약 실패] 결과 JSON 읽기 실패: {e}"

        lines = ["[결과 요약]"]
        if isinstance(data, dict) and "results" in data and isinstance(data["results"], list):
            items = data["results"]
            lines.append(f"- 항목 수: {len(items)}")
            for key in ("profit_rate", "pnl_rate", "return", "roi"):
                if items and isinstance(items[0], dict) and key in items[0]:
                    sorted_items = sorted(
                        [x for x in items if isinstance(x, dict) and key in x],
                        key=lambda x: float(x.get(key, -999999)),
                        reverse=True,
                    )
                    top3 = sorted_items[:3]
                    lines.append(f"- TOP3 by {key}:")
                    for r, it in enumerate(top3, 1):
                        sym = it.get("ticker") or it.get("symbol") or it.get("market") or it.get("currency") or "?"
                        val = it.get(key)
                        lines.append(f"  {r}) {sym}: {val}")
                    return "\n".join(lines)

            sample = items[0] if items else {}
            lines.append(f"- (키 자동요약 실패) 첫 항목 keys: {list(sample.keys()) if isinstance(sample, dict) else type(sample)}")
            return "\n".join(lines)

        if isinstance(data, dict):
            lines.append(f"- dict keys: {list(data.keys())[:20]}")
            return "\n".join(lines)

        if isinstance(data, list):
            lines.append(f"- list length: {len(data)}")
            if data and isinstance(data[0], dict):
                lines.append(f"- first keys: {list(data[0].keys())}")
            return "\n".join(lines)

        return "[결과 요약] 알 수 없는 JSON 구조"
#*************************************************************************************************기존
    """
    def _open_path_with_default_app(self, path: str):
        path = os.path.abspath(path)
        if not os.path.exists(path):
            QMessageBox.information(self, "안내", f"파일이 존재하지 않습니다:\n{path}")
            return

        try:
            if os.name == "nt":
                os.startfile(path)  # Windows
            elif platform.system() == "Darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception as e:
            QMessageBox.critical(self, "오류", f"파일 열기 실패: {e}\n{path}")
    """
#**********************************************************************************************************기존
#*********************************************************************************************************변경
    def _open_path_with_default_app(self, path: str) -> None:
        path = os.path.abspath(path)
        try:
            if os.name == "nt":
                os.startfile(path)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception as e:
            QMessageBox.critical(self, "열기 실패", f"{path}\n\n{e}")
    # ===== Live Preflight handlers =====
    def _ensure_smtm_sys_path(self) -> None:
        """smtm 패키지 import가 실패하지 않도록 sys.path에 SMTM_ROOT를 보장한다."""
        try:
            if SMTM_ROOT and SMTM_ROOT not in sys.path:
                sys.path.insert(0, SMTM_ROOT)
        except Exception:
            pass
    def _live_update_ready_label(self) -> None:
        """Preflight 결과 기반 READY 상태를 갱신."""
        st = getattr(self, "_preflight_state", {}) or {}
        public_ok = bool(st.get("public_ok"))
        markets_ok = bool(st.get("markets_ok"))
        ready_public = public_ok and markets_ok

        private_ok = bool(st.get("private_ok"))
        private_blocked = bool(st.get("private_blocked"))

        if ready_public:
            msg = "READY: OK (public)"
        else:
            reasons = []
            if not public_ok:
                reasons.append("public_ping")
            if not markets_ok:
                reasons.append("markets")
            msg = "READY: NOT READY (" + ",".join(reasons) + ")"

        if private_ok:
            msg += " | private: OK"
        elif private_blocked:
            msg += " | private: DISABLED"
        else:
            msg += " | private: (not checked)"

        try:
            self.lb_live_ready.setText(msg)
        except Exception:
            pass


    def _live_profile_path(self) -> str:
        return os.path.join(SMTM_ROOT, "output", "live_profile.json")


    def _live_save_profile(self) -> None:
        """현재 UI 입력 + Preflight 결과를 output/live_profile.json에 저장."""
        try:
            ensure_dir(os.path.join(SMTM_ROOT, "output"))
        except Exception:
            pass

        try:
            ticker = self.le_ticker.text().strip().upper()
        except Exception:
            ticker = "BTC"

        st = getattr(self, "_preflight_state", {}) or {}
        payload = {
            "version": 1,
            "saved_at": datetime.datetime.now().isoformat(timespec="seconds"),
            "ticker": ticker,
            "preflight": st,
            # 향후 리스크/실전 설정이 추가되면 여기에 확장
        }
        path = self._live_profile_path()
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            self._append_log(f"[Live][Profile] saved: {path}")
        except Exception as e:
            self._append_log(f"[Live][Profile][ERR] save failed: {e}")


    def _live_load_profile(self) -> None:
        """output/live_profile.json에서 프로파일을 읽어 UI 입력/READY 표시를 복원."""
        path = self._live_profile_path()
        if not os.path.isfile(path):
            self._append_log(f"[Live][Profile][WARN] profile not found: {path}")
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                payload = json.load(f)
            ticker = (payload.get("ticker") or "BTC").strip().upper()
            dry = (payload.get('dryrun_tickers') or '').strip()
            pf = bool(payload.get('dryrun_paper_fill') or False)
            try:
                self.le_ticker.setText(ticker)
                if hasattr(self, 'le_dryrun_tickers') and dry:
                    self.le_dryrun_tickers.setText(dry)
                if hasattr(self, 'cb_dryrun_paper_fill'):
                    self.cb_dryrun_paper_fill.setChecked(bool(pf))
            except Exception:
                pass
            st = payload.get("preflight") or {}
            self._preflight_state = st
            self._live_update_ready_label()
            self._append_log(f"[Live][Profile] loaded: {path} (ticker={ticker})")
        except Exception as e:
            self._append_log(f"[Live][Profile][ERR] load failed: {e}")
    def _dryrun_start(self) -> None:
        try:
            txt = self.lb_live_ready.text() if hasattr(self, "lb_live_ready") else ""
            if "READY: OK (public)" not in txt:
                self._append_log("[DryRun][BLOCK] READY: OK (public) 상태에서만 시작할 수 있습니다.")
                return

            if getattr(self, 'dryrun_thread', None) is not None:
                self._append_log("[DryRun][WARN] already running")
                return

            raw = self.le_dryrun_tickers.text().strip() if hasattr(self, "le_dryrun_tickers") else ""
            if not raw:
                raw = self.le_ticker.text().strip().upper() if hasattr(self, "le_ticker") else "BTC"
                if hasattr(self, "le_dryrun_tickers"):
                    self.le_dryrun_tickers.setText(raw)

            tickers = [t.strip().upper() for t in raw.split(",") if t.strip()]
            if not tickers:
                self._append_log("[DryRun][ERR] tickers empty")
                return

            self.bt_dryrun_start.setEnabled(False)
            self.bt_dryrun_stop.setEnabled(True)
            self.lb_dryrun_status.setText("DRYRUN: starting...")

            budget = 0.0
            try:
                budget = float(self.le_budget.text().strip()) if hasattr(self, 'le_budget') else 0.0
            except Exception:
                budget = 0.0
            paper_fill = bool(self.cb_dryrun_paper_fill.isChecked()) if hasattr(self, 'cb_dryrun_paper_fill') else False

            self.dryrun_thread = DryRunThread(smtm_root=SMTM_ROOT, tickers=tickers, interval_sec=10, budget=budget, paper_fill=paper_fill, warmup_count=200)
            self.dryrun_thread.log.connect(self._append_log)
            self.dryrun_thread.status.connect(self._dryrun_set_status)
            self.dryrun_thread.finished.connect(self._dryrun_on_finished)
            self.dryrun_thread.start()
        except Exception as e:
            self._append_log(f"[DryRun][FATAL] start failed: {e}")
            self._append_log(traceback.format_exc())
            setattr(self, 'dryrun_thread', None)
            try:
                self.bt_dryrun_start.setEnabled(True)
                self.bt_dryrun_stop.setEnabled(False)
                self.lb_dryrun_status.setText("DRYRUN: (stopped)")
            except Exception:
                pass


    def _dryrun_stop(self) -> None:
        try:
            if getattr(self, 'dryrun_thread', None) is None:
                return
            self._append_log("[DryRun] stop requested")
            self.dryrun_thread.stop()
        except Exception as e:
            self._append_log(f"[DryRun][ERR] stop failed: {e}")


    def _dryrun_set_status(self, msg: str) -> None:
        try:
            self.lb_dryrun_status.setText(msg)
        except Exception:
            pass


    def _dryrun_on_finished(self) -> None:
        setattr(self, 'dryrun_thread', None)
        try:
            self.bt_dryrun_start.setEnabled(True)
            self.bt_dryrun_stop.setEnabled(False)
            self.lb_dryrun_status.setText("DRYRUN: (stopped)")
        except Exception:
            pass







    def _live_env_check(self) -> None:
        """업비트 실전 운용에 필요한 환경변수/설정 존재 여부만 점검 (주문/체결 없음)."""
        st = getattr(self, "_preflight_state", None)
        if not isinstance(st, dict):
            self._preflight_state = {'env_ok': False, 'public_ok': False, 'markets_ok': False, 'private_ok': False, 'private_blocked': False, 'last': None}
            st = self._preflight_state

        keys = {
            "UPBIT_OPEN_API_ACCESS_KEY": os.environ.get("UPBIT_OPEN_API_ACCESS_KEY"),
            "UPBIT_OPEN_API_SECRET_KEY": os.environ.get("UPBIT_OPEN_API_SECRET_KEY"),
            "UPBIT_OPEN_API_SERVER_URL": os.environ.get("UPBIT_OPEN_API_SERVER_URL"),
        }
        self._append_log("[Live][Preflight] env check:")
        all_ok = True
        for k, v in keys.items():
            bad = (not v) or ("upbit_" in v) or ("upbit_server_url" in v)
            all_ok = all_ok and (not bad)
            self._append_log(f"  - {k}: {'MISSING/DEFAULT' if bad else 'SET'}")
        if (not keys["UPBIT_OPEN_API_SERVER_URL"]) or ("upbit_server_url" in (keys["UPBIT_OPEN_API_SERVER_URL"] or "")):
            self._append_log("[Live][Preflight][WARN] UPBIT_OPEN_API_SERVER_URL이 설정되지 않았습니다. 예: https://api.upbit.com")

        st["env_ok"] = all_ok
        st["last"] = datetime.datetime.now().isoformat(timespec="seconds")
        self._live_update_ready_label()
        self._append_log("[Live][Preflight] done")


    def _live_public_ping(self) -> None:
        """업비트 공개 API(1분봉 1개) 호출로 네트워크/엔드포인트 정상 여부 확인."""
        st = getattr(self, "_preflight_state", None)
        if not isinstance(st, dict):
            self._preflight_state = {'env_ok': False, 'public_ok': False, 'markets_ok': False, 'private_ok': False, 'private_blocked': False, 'last': None}
            st = self._preflight_state

        try:
            ticker = self.le_ticker.text().strip().upper()
        except Exception:
            ticker = "BTC"
        market = f"KRW-{ticker}"
        url = "https://api.upbit.com/v1/candles/minutes/1"
        try:
            r = requests.get(url, params={"market": market, "count": 1}, timeout=10)
            r.raise_for_status()
            data = r.json()
            if isinstance(data, list) and data:
                kst = data[0].get("candle_date_time_kst")
                price = data[0].get("trade_price")
                self._append_log(f"[Live][Preflight] public ping OK: {market} kst={kst} price={price}")
                st["public_ok"] = True
            else:
                self._append_log(f"[Live][Preflight][WARN] public ping: empty response ({market})")
                st["public_ok"] = False
        except Exception as e:
            self._append_log(f"[Live][Preflight][ERR] public ping failed: {e}")
            st["public_ok"] = False

        st["last"] = datetime.datetime.now().isoformat(timespec="seconds")
        self._live_update_ready_label()


    def _live_refresh_markets(self) -> None:
        """KRW 마켓 캐시를 강제 갱신한다. (output/upbit_markets_krw.json)"""
        self._ensure_smtm_sys_path()
        st = getattr(self, "_preflight_state", None)
        if not isinstance(st, dict):
            self._preflight_state = {'env_ok': False, 'public_ok': False, 'markets_ok': False, 'private_ok': False, 'private_blocked': False, 'last': None}
            st = self._preflight_state

        try:
            from smtm.data.upbit_markets import krw_market_map
            m = krw_market_map(force_refresh=True)
            self._append_log(f"[Live][Preflight] KRW market refreshed: {len(m)} tickers (cached to output/)")
            st["markets_ok"] = True
        except Exception as e:
            self._append_log(f"[Live][Preflight][ERR] refresh markets failed: {e}")
            st["markets_ok"] = False

        st["last"] = datetime.datetime.now().isoformat(timespec="seconds")
        self._live_update_ready_label()


    def _live_private_account_check(self) -> None:
        """개인키가 설정된 경우에만 계좌 조회를 시도한다 (주문 없음)."""
        self._ensure_smtm_sys_path()
        st = getattr(self, "_preflight_state", None)
        if not isinstance(st, dict):
            self._preflight_state = {'env_ok': False, 'public_ok': False, 'markets_ok': False, 'private_ok': False, 'private_blocked': False, 'last': None}
            st = self._preflight_state

        try:
            from smtm.trader.upbit_trader import UpbitTrader
        except Exception as e:
            self._append_log(f"[Live][Preflight][ERR] import UpbitTrader failed: {e}")
            st["private_ok"] = False
            st["private_blocked"] = False
            st["last"] = datetime.datetime.now().isoformat(timespec="seconds")
            self._live_update_ready_label()
            return

        try:
            currency = self.le_ticker.text().strip().upper()
        except Exception:
            currency = "BTC"

        self._append_log(f"[Live][Preflight] private account check: currency={currency}")

        ak = os.environ.get("UPBIT_OPEN_API_ACCESS_KEY", "")
        sk = os.environ.get("UPBIT_OPEN_API_SECRET_KEY", "")
        su = os.environ.get("UPBIT_OPEN_API_SERVER_URL", "")
        bad = (not ak) or (not sk) or (not su) or ("upbit_" in ak) or ("upbit_" in sk) or ("upbit_server_url" in su)
        if bad:
            self._append_log("[Live][Preflight][BLOCK] API 키/URL이 설정되지 않아 계좌 조회를 실행하지 않습니다.")
            self._append_log("  - .env 또는 환경변수에 UPBIT_OPEN_API_* 값을 설정하세요.")
            st["private_ok"] = False
            st["private_blocked"] = True
            st["last"] = datetime.datetime.now().isoformat(timespec="seconds")
            self._live_update_ready_label()
            return

        try:
            trader = UpbitTrader(currency=currency, budget=0)
            info = trader.get_account_info()
            if info is None:
                self._append_log("[Live][Preflight][ERR] account info returned None")
                st["private_ok"] = False
            else:
                bal = info.get("balance")
                dt = info.get("date_time")
                quote = info.get("quote", {})
                self._append_log(f"[Live][Preflight] account OK: balance={bal} date_time={dt} quote={quote}")
                st["private_ok"] = True
            st["private_blocked"] = False
        except Exception as e:
            self._append_log(f"[Live][Preflight][ERR] account check failed: {e}")
            st["private_ok"] = False
            st["private_blocked"] = False

        st["last"] = datetime.datetime.now().isoformat(timespec="seconds")
        self._live_update_ready_label()

    def _live_ro_get_trader(self, currency: str):
        """Readonly 전용 UpbitTrader 생성. 키/URL 미설정이면 None 반환."""
        self._ensure_smtm_sys_path()
        ak = os.environ.get("UPBIT_OPEN_API_ACCESS_KEY", "")
        sk = os.environ.get("UPBIT_OPEN_API_SECRET_KEY", "")
        su = os.environ.get("UPBIT_OPEN_API_SERVER_URL", "")
        bad = (not ak) or (not sk) or (not su) or ("upbit_" in ak) or ("upbit_" in sk) or ("upbit_server_url" in su)
        if bad:
            self._append_log("[Live][Readonly][BLOCK] API 키/URL이 설정되지 않아 조회를 실행하지 않습니다.")
            self._append_log("  - .env 또는 환경변수에 UPBIT_OPEN_API_* 값을 설정하세요.")
            return None
        try:
            from smtm.trader.upbit_trader import UpbitTrader
        except Exception as e:
            self._append_log(f"[Live][Readonly][ERR] import UpbitTrader failed: {e}")
            return None
        try:
            return UpbitTrader(currency=currency)
        except Exception as e:
            self._append_log(f"[Live][Readonly][ERR] UpbitTrader init failed: {e}")
            return None

    def _live_ro_accounts(self) -> None:
        """잔고/보유 조회(Readonly)."""
        currency = "BTC"
        try:
            currency = self.le_ticker.text().strip().upper()
        except Exception:
            pass
        self._append_log(f"[Live][Readonly] accounts: currency={currency}")
        t = self._live_ro_get_trader(currency)
        if t is None:
            return
        try:
            data = t._query_account()
            try:
                self.te_live_readonly.setPlainText(json.dumps(data, ensure_ascii=False, indent=2))
            except Exception:
                pass
            self._append_log(f"[Live][Readonly] accounts OK: items={len(data) if isinstance(data, list) else 'n/a'}")
        except Exception as e:
            self._append_log(f"[Live][Readonly][ERR] accounts failed: {e}")
#*********************************************************************************
    def _live_ro_open_orders(self):
        """실전(Readonly) 미체결 주문 조회"""
        try:
            t = getattr(self, "_live_trader", None)
            if t is None:
                self._append_log("[Live][Readonly][ERR] trader 미초기화")
                return

            # 호출 디바운스
            now = time.time()
            last = getattr(self, "_ro_last_open_orders_ts", 0)
            if now - last < 2.0:
                return
            self._ro_last_open_orders_ts = now

            orders = None

            # 1) 신형 인터페이스 (_query_orders)
            if hasattr(t, "_query_orders"):
                try:
                    orders = t._query_orders(state="wait")
                except Exception as e:
                    self._append_log(f"[Live][Readonly][ERR] _query_orders 실패: {e}")
                    orders = None

            # 2) 구형 인터페이스 (_query_order_list)
            if orders is None and hasattr(t, "_query_order_list"):
                try:
                    # uuids는 반드시 필요 → 빈 리스트라도 전달
                    orders = t._query_order_list([], is_done_state=False)
                except Exception as e:
                    self._append_log(f"[Live][Readonly][ERR] _query_order_list 실패: {e}")
                    return

            if orders is None:
                self._append_log("[Live][Readonly] open_orders 없음")
                return

            self._append_log(f"[Live][Readonly] open_orders OK: items={len(orders)}")

        except Exception as e:
            self._append_log(f"[Live][Readonly][ERR] open_orders 예외: {e}")
            self._append_log(traceback.format_exc())

#*********************************************************************************************************
    def _live_arm_toggled(self) -> None:
        """주문 게이트 상태 표시(7단계). 아직 주문 실행 로직은 연결하지 않음."""
        import time
        now = time.time()
        last = getattr(self, '_ro_last_open_orders_ts', 0.0)
        if (now - last) < getattr(self, '_ro_debounce_sec', 1.2):
            self._set_status('요청이 너무 빠릅니다. 잠시 후 다시 시도하세요.', 2500)
            return
        setattr(self, '_ro_last_open_orders_ts', now)

        armed = False
        try:
            armed = bool(self.cb_live_arm.isChecked())
        except Exception:
            pass
        phrase = ""
        try:
            phrase = (self.le_live_arm_phrase.text() or "").strip()
        except Exception:
            pass
        max_order = ""
        try:
            max_order = (self.le_live_max_order_krw.text() or "").strip()
        except Exception:
            pass
        daily_loss = ""
        try:
            daily_loss = (self.le_live_daily_loss_krw.text() or "").strip()
        except Exception:
            pass

        ok = armed and (phrase == "LIVE-ORDER-ENABLE") and (max_order.isdigit()) and (daily_loss.isdigit())
        msg = "LIVE ARM: DISARMED (주문 차단)"
        if ok:
            msg = "LIVE ARM: READY (게이트 통과: 주문 허용 가능 상태)"
        try:
            self.lb_live_arm_status.setText(msg)
        except Exception:
            pass


    def _open_output_dir(self) -> None:
        out_dir = os.path.join(SMTM_ROOT, "output")
        ensure_dir(out_dir)
        self._open_path_with_default_app(out_dir)

    def _open_result_dir(self) -> None:
        res_dir = os.path.join(SMTM_ROOT, "result")
        ensure_dir(res_dir)
        self._open_path_with_default_app(res_dir)



#*********************************************************************************************************변경


    def _read_last_result_item(self) -> Optional[dict]:
        """
        결과 JSON에서 results[0]을 읽어 마지막 실행 결과 item(dict)을 반환.
        """
        results_path = os.path.abspath(self.bt_results_path.text().strip() or DEFAULT_RESULTS_JSON)
        if not os.path.exists(results_path):
            return None
        try:
            with open(results_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and isinstance(data.get("results"), list) and data["results"]:
                if isinstance(data["results"][0], dict):
                    return data["results"][0]
            return None
        except Exception:
            return None

    def _open_last_artifacts(self):
        """
        output JSON의 chart_path / windows_csv_path 기반으로 마지막 산출물 열기
        """
        item = self._read_last_result_item()
        if not item:
            QMessageBox.information(self, "안내", "결과 JSON을 찾을 수 없거나 비어있습니다.")
            return

        chart_path = (item.get("chart_path") or "").strip()
        csv_path = (item.get("windows_csv_path") or "").strip()

        if not chart_path and not csv_path:
            QMessageBox.information(self, "안내", "결과 JSON에 chart_path / windows_csv_path가 없습니다.")
            return

        # 우선 차트 → CSV 순으로 연다(원하시면 반대로도 가능)
        if chart_path:
            self._open_path_with_default_app(chart_path)
        if csv_path:
            self._open_path_with_default_app(csv_path)

#***************************************************************************************************************

    def _open_path_with_default_app(self, path: str):
        path = os.path.abspath(path)
        if not os.path.exists(path):
            QMessageBox.information(self, "안내", f"파일이 존재하지 않습니다:\n{path}")
            return

        try:
            if os.name == "nt":
                os.startfile(path)  # Windows
            elif platform.system() == "Darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception as e:
            QMessageBox.critical(self, "오류", f"파일 열기 실패: {e}\n{path}")

    def _read_last_result_item(self) -> Optional[dict]:
        results_path = os.path.abspath(self.bt_results_path.text().strip() or DEFAULT_RESULTS_JSON)
        if not os.path.exists(results_path):
            return None
        try:
            with open(results_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and isinstance(data.get("results"), list) and data["results"]:
                if isinstance(data["results"][0], dict):
                    return data["results"][0]
            return None
        except Exception:
            return None

    def _open_last_artifacts(self):
        item = self._read_last_result_item()
        if not item:
            QMessageBox.information(self, "안내", "결과 JSON을 찾을 수 없거나 비어있습니다.")
            return

        chart_path = (item.get("chart_path") or "").strip()
        csv_path = (item.get("windows_csv_path") or "").strip()

        if not chart_path and not csv_path:
            QMessageBox.information(self, "안내", "결과 JSON에 chart_path / windows_csv_path가 없습니다.")
            return

        if chart_path:
            self._open_path_with_default_app(chart_path)
        if csv_path:
            self._open_path_with_default_app(csv_path)


#**************************************************************************************************************
    def _load_results_clicked(self):
        path = self.bt_results_path.text().strip()
        if not path:
            QMessageBox.information(self, "안내", "결과 JSON 경로가 비었습니다.")
            return
        path = os.path.abspath(path)
        if not os.path.exists(path):
            QMessageBox.information(self, "안내", f"파일이 존재하지 않습니다:\n{path}")
            return
        self._append_log(self._summarize_results_file(path))
        self._set_status("결과 요약 로드 완료", 3000)

    def _update_status(self):
        warnings: List[str] = []
        try:
            total_weight = sum(self.params.get("BUY_WEIGHTS", []))
            if total_weight * 0.03 > 0.7:
                warnings.append("물타기에 사용되는 총 비중이 70%를 초과합니다.")
        except Exception:
            pass

        msg = "설정 정상. 적용 가능." if not warnings else ("경고: " + " / ".join(warnings))
        self._set_status(msg, 2500)

    # ---------------- DB date limit ----------------

    def _apply_db_date_limits(self):
        # 방어: 위젯 생성 전 호출되면 그냥 스킵
        if not hasattr(self, "bt_start_date") or not hasattr(self, "bt_end_date"):
            return

        mn_d, mx_d = self._get_upbit_db_date_range()
        if not mn_d or not mx_d:
            self._append_log("[UI][DB] date range not available (skip limit)")
            return

        self._append_log(f"[UI][DB] upbit range: {mn_d} ~ {mx_d}")

        qmin = QDate.fromString(mn_d, "yyyy-MM-dd")
        qmax = QDate.fromString(mx_d, "yyyy-MM-dd")
        if not qmin.isValid() or not qmax.isValid():
            self._append_log("[UI][DB] invalid QDate parsed (skip limit)")
            return

        self.bt_start_date.setMinimumDate(qmin)
        self.bt_start_date.setMaximumDate(qmax)
        self.bt_end_date.setMinimumDate(qmin)
        self.bt_end_date.setMaximumDate(qmax)

        end = self.bt_end_date.date()
        if end > qmax:
            end = qmax
        if end < qmin:
            end = qmin
        self.bt_end_date.setDate(end)

        start = self.bt_start_date.date()
        if start > end:
            start = end.addDays(-7)
        if start < qmin:
            start = qmin
        self.bt_start_date.setDate(start)

        self._set_status(f"DB 범위 적용: {mn_d} ~ {mx_d}", 5000)

    def _get_upbit_db_date_range(self) -> Tuple[Optional[str], Optional[str]]:
        """
        smtm.db(upbit 테이블)에서 min/max(date_time)를 읽어서 'YYYY-MM-DD' 반환
        """
        try:
            db_path = os.path.join(SMTM_ROOT, "smtm.db")
            if not os.path.exists(db_path):
                self._append_log(f"[UI][DB] not found: {db_path}")
                return None, None

            con = sqlite3.connect(db_path)
            cur = con.cursor()
            cur.execute("SELECT MIN(date_time), MAX(date_time) FROM upbit")
            mn, mx = cur.fetchone()
            con.close()

            if not mn or not mx:
                return None, None

            mn_d = str(mn).split(" ")[0]
            mx_d = str(mx).split(" ")[0]
            return mn_d, mx_d

        except Exception as e:
            self._append_log(f"[UI][DB][ERR] range read failed: {e}")
            return None, None


    def _refresh_artifacts_view(self) -> None:

        """Scan output/result folders and update the Artifacts view.

        This must be robust even when folders are empty or missing.
        """
        try:
            smtm_root = SMTM_ROOT
        except Exception:
            smtm_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

        # Candidate folders (some users historically used 'results' or a typo 'rusult')
        result_dir_candidates = [
            os.path.join(smtm_root, "result"),
            os.path.join(smtm_root, "results"),
            os.path.join(smtm_root, "rusult"),
        ]
        output_dir = os.path.join(smtm_root, "output")

        result_dir = None
        for d in result_dir_candidates:
            if os.path.isdir(d):
                result_dir = d
                break
        if result_dir is None:
            # don't create directories here; just report
            result_dir = result_dir_candidates[0]

        def _safe_glob(base_dir: str, patterns: list[str]) -> list[str]:
            paths: list[str] = []
            if not base_dir or (not os.path.isdir(base_dir)):
                return paths
            import glob
            for pat in patterns:
                paths.extend(glob.glob(os.path.join(base_dir, pat)))
            # dedupe while keeping order
            seen = set()
            out = []
            for p in paths:
                if p not in seen:
                    seen.add(p)
                    out.append(p)
            return out

        def _latest(paths: list[str]) -> Optional[str]:
            if not paths:
                return None
            # choose by mtime, fallback to lexicographic
            best = None
            best_m = None
            for p in paths:
                try:
                    m = os.path.getmtime(p)
                except Exception:
                    m = None
                if best is None:
                    best, best_m = p, m
                    continue
                if best_m is None and m is not None:
                    best, best_m = p, m
                elif m is not None and best_m is not None and m > best_m:
                    best, best_m = p, m
                elif m is None and best_m is None and str(p) > str(best):
                    best, best_m = p, m
            return best

        def _fmt_mtime(p: str) -> str:
            try:
                ts = os.path.getmtime(p)
                from datetime import datetime as _dt
                return _dt.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                return "-"

        def _line(label: str, p: Optional[str]) -> str:
            if not p:
                return f"- {label}: (none)  [-]"
            return f"- {label}: {p}  [{_fmt_mtime(p)}]"

        # Discover files
        chart = _latest(_safe_glob(result_dir, ["chart_*.png", "chart-*.png", "*.png"]))
        win_csv = _latest(_safe_glob(result_dir, ["windows_*.csv", "windows-*.csv", "*.csv"]))
        sim_png = _latest(_safe_glob(output_dir, ["SIM-*.png"]))
        sim_csv = _latest(_safe_glob(output_dir, ["SIM-*.csv"]))
        win_sim_csv = _latest(_safe_glob(output_dir, ["windows_SIM-*.csv", "windows-SIM-*.csv"]))

        # results json (most recent json in output; prefer multi_backtest_results.json)
        json_candidates = _safe_glob(output_dir, ["multi_backtest_results.json", "*backtest*.json", "*.json"])
        results_json = None
        if json_candidates:
            # prefer exact name if it exists
            exact = os.path.join(output_dir, "multi_backtest_results.json")
            if exact in json_candidates and os.path.isfile(exact):
                results_json = exact
            else:
                results_json = _latest(json_candidates)

        self._latest_artifacts = {
            "result_chart": chart,
            "result_windows_csv": win_csv,
            "output_sim_png": sim_png,
            "output_sim_csv": sim_csv,
            "output_windows_sim_csv": win_sim_csv,
            "output_results_json": results_json,
            "result_dir": result_dir,
            "output_dir": output_dir,
        }

        # Compose message for UI (always show something)
        msg_lines = []
        msg_lines.append("[ARTIFACT] scanned")
        msg_lines.append(f"  - result_dir: {result_dir} ({'exists' if os.path.isdir(result_dir) else 'missing'})")
        msg_lines.append(f"  - output_dir: {output_dir} ({'exists' if os.path.isdir(output_dir) else 'missing'})")
        try:
            if os.path.isdir(result_dir):
                msg_lines.append(f"  - result_dir files: {len(os.listdir(result_dir))}")
            if os.path.isdir(output_dir):
                msg_lines.append(f"  - output_dir files: {len(os.listdir(output_dir))}")
        except Exception:
            pass
        msg_lines.append("")
        msg_lines.append(_line("result_chart", chart))
        msg_lines.append(_line("result_windows_csv", win_csv))
        msg_lines.append(_line("output_sim_png", sim_png))
        msg_lines.append(_line("output_sim_csv", sim_csv))
        msg_lines.append(_line("output_windows_sim_csv", win_sim_csv))
        msg_lines.append(_line("output_results_json", results_json))

        msg = "\n".join(msg_lines)

        try:
            self.te_artifacts.setPlainText(msg)
        except Exception:
            # As a fallback, append to backtest log so user still sees it
            try:
                self._append_log(msg)
            except Exception:
                pass

