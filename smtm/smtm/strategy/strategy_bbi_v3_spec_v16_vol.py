import copy
import math
from datetime import datetime

import json
import os

import numpy as np
import pandas as pd

try:
    from smtm.strategy.strategy import Strategy
    from smtm.log_manager import LogManager
    from smtm.date_converter import DateConverter
except ImportError:
    import sys
    sys.path.insert(0, '/home/claude/smtm')
    from strategy.strategy import Strategy
    from log_manager import LogManager
    from date_converter import DateConverter


class StrategyBBI_V3_Spec_V16_Vol(Strategy):
    """
    BBI V3 Spec v1.6 (Volume 버전)

    - 기본 구조: V15 + 리스크 기반 TP + 비상 손절 + 급등 트레일링
    - 추가: 볼륨 스파이크 기반 3차 이상(3~5차) 보수적 물타기
        * 1, 2차: 기존과 동일 (볼륨 안 씀)
        * 3차 이상: DRAWDOWN 조건 + 지표 조건 + 볼륨 스파이크 있을 때만 매수
    """

    NAME = "BBI V3 Spec v1.6 (Volume)"
    CODE = "BBI-V3-SPEC-V16-VOL"

    ISO = "%Y-%m-%dT%H:%M:%S"
    COMMISSION = 0.0005

    # 튜닝 파일 경로 (PyQt UI에서 저장하는 JSON)
    TUNING_FILE = "bbi_v16_vol_tuning.json"

    # ====== 지표 기준 ======
    RSI_LIMIT = 60
    MACD_LIMIT = -250000
    STOCH_LIMIT = 2.5

    WINDOW_SIZE = 10
    TIME_WINDOW_FOR_BUY = 10  # BB 터치 후 10틱 이내만 매수

    # ====== 쿨다운 ======
    BUY_COOLDOWN_TICKS = 15   # 매수-매수 간 최소 15틱
    SELL_COOLDOWN_TICKS = 5   # 전량 매도 후 5틱 동안 신규 1차 매수 금지

    # ====== ATR / EMA 필터 ======
    ATR_PERIOD = 14
    ATR_PERCENTILE = 40
    ATR_HISTORY_SIZE = 100

    EMA_PERIOD = 21
    EMA_DISTANCE_PERCENT_MIN = 0.37

    # ====== 늦은 차수(3~5차) 보수적 진입 파라미터 ======
    LATE_RSI_LIMIT = 60
    LATE_MACD_LIMIT = -250000
    LATE_STOCH_LIMIT = 2.5
    LATE_EMA_DISTANCE_MIN = 0.37

    # ====== 차수별 평단 손실률 조건 (DCA 필터) ======
    # index = 현재 buy_count (0 = 1차 직전, 1 = 2차 직전, 2 = 3차 직전 ...)
    DRAWDOWN_THRESHOLDS = [0.0, 0.02, 0.03, 0.04, 0.05]

    # ====== 자금 관리 ======
    POSITION_SIZE_PERCENT = 0.03
    MAX_BUY_COUNT = 5

    BUY_WEIGHTS = [7.0, 5.0, 3.6, 2.4, 2.0]  # 1~5차 비중

    # ====== 리스크 기반 TP (차수별 익절) ======
    BREAKEVEN_EXIT = 0.01  # 기본값(백업용)

    # index = buy_count - 1
    BREAKEVEN_EXIT_THRESHOLDS = [0.01, 0.009, 0.008, 0.007, 0.006]

    PROFIT_STAGE_1 = 0.012
    SELL_RATIO_STAGE_1 = 0.50

    TP2_PROFIT_MIN = 0.02
    TP2_PROFIT_MAX = 0.03

    TP3_START_PROFIT = 0.03
    TP3_TRAIL_DROP = 0.02
    TP3_HOLD_BARS = 5

    # ====== 손절 관련 ======
    STOP_LOSS = 0.04              # (일반 손절은 사용 안 함, 비상/5차 손절만 사용)
    STOP_LOSS_MIN_BUY_COUNT = 1

    EMERGENCY_STOP_LOSS = 0.08    # 1~2차 비상 손절 (-8%)
    EMERGENCY_STOP_MAX_BUY_COUNT = 2

    MAX_LOSS_AFTER_5TH = 0.02     # 5차 이후 -2% 손절

    # ====== 급등 트레일링 ======
    RALLY_START_PROFIT = 0.02     # +2% 이상이면 급등 구간 진입
    RALLY_TRAIL_DROP = 0.01       # 급등 최고가 대비 -1% 이탈 시 전량 매도

    # ====== 볼륨 스파이크 파라미터 ======
    VOL_MA_PERIOD = 20            # 최근 20개 캔들 평균 거래량
    VOL_SPIKE_FACTOR = 2.5        # 평균의 2.5배 이상이면 스파이크
    VOL_MIN_SAMPLES = 10          # 평균 계산에 필요한 최소 유효 샘플 수

    # ===== 수량 정밀도 =====
    AMOUNT_DECIMALS = 6
    AMOUNT_SCALE = 10 ** AMOUNT_DECIMALS

    def __init__(self):
        super().__init__()

        self.logger = LogManager.get_logger(__class__.__name__)

        self.is_intialized = False
        self.is_simulation = False

        self.data = []
        self.result = []
        self.request = None

        self.budget = 0
        self.balance = 0
        self.min_price = 0

        self.BASE_POSITION_SIZE = 0

        self.buy_count = 0
        self.buy_prices = []
        self.buy_amounts = []
        self.total_amount = 0
        self.average_price = 0

        self.trailing_active = False
        self.max_price_after_target = 0

        self.atr_values = []

        self.in_window = False
        self.window_start_idx = None

        self.flag_rsi = False
        self.flag_macd = False
        self.flag_stoch = False

        self.did_buy_this_window = False

        self.last_buy_idx = -999
        self.last_sell_idx = -999

        self.stage_1_done = False
        self.stage_2_done = False
        self.remaining_ratio = 1.0

        self.tp3_active = False
        self.tp3_start_idx = -1
        self.tp3_high_price = 0.0

        # 급등 트레일링 상태
        self.rally_active = False
        self.rally_high_price = 0.0

        # 볼륨 히스토리
        self.volumes = []

        self.waiting_requests = {}
        self.add_spot_callback = None

    # =====================================================================
    # 튜닝 파라미터 로딩
    # =====================================================================

    def _apply_tuning_params(self):
        """
        PyQt 튜닝 UI에서 저장한 JSON 파일(bbi_v16_vol_tuning.json)을 읽어
        동일한 이름의 속성이 있으면 self.<key> 값으로 덮어쓴다.
        """
        path = self.TUNING_FILE
        if not os.path.exists(path):
            return

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            self.logger.error(f"[TUNING] Failed to load {path}: {e}")
            return

        if not isinstance(data, dict):
            self.logger.error(f"[TUNING] Invalid format in {path} (expected dict)")
            return

        applied_keys = []
        for key, value in data.items():
            if hasattr(self, key):
                setattr(self, key, value)
                applied_keys.append(key)

        if applied_keys:
            self.logger.info(
                f"[TUNING] Applied params from {path}: {', '.join(applied_keys)}"
            )
        else:
            self.logger.info(
                f"[TUNING] No matching keys found in {path} to apply."
            )

    # =====================================================================
    # 수량 보정
    # =====================================================================

    def _normalize_amount(self, amount: float) -> float:
        return math.floor(amount * self.AMOUNT_SCALE) / self.AMOUNT_SCALE

    # =====================================================================
    # 초기화
    # =====================================================================

    def initialize(
        self,
        budget,
        min_price=5000,
        add_spot_callback=None,
        add_line_callback=None,
        alert_callback=None,
    ):
        if self.is_intialized:
            return

        self.is_intialized = True

        # NOTE:
        # - 시뮬레이션/실전 구분은 외부(Controller/Simulator)에서 결정합니다.
        # - Simulator 경로에서는 strategy.is_simulation=True 로 설정한 뒤 initialize()를 호출합니다.
        # - 실전 경로에서는 strategy.is_simulation=False 로 설정한 뒤 initialize()를 호출합니다.
        # - initialize()에서 강제로 True/False로 덮어쓰지 않습니다. (실전에서 시뮬 전용 동작 방지)

        self.budget = budget
        self.balance = budget
        self.min_price = min_price

        # ★ 여기서 튜닝 파라미터 적용
        self._apply_tuning_params()

        self.BASE_POSITION_SIZE = int(budget * self.POSITION_SIZE_PERCENT)

        self.logger.info(
            f"[INIT] Budget: {budget:,}, "
            f"BASE_POSITION_SIZE: {self.BASE_POSITION_SIZE:,} "
            f"({self.POSITION_SIZE_PERCENT*100:.1f}%), "
            f"MAX_BUY: {self.MAX_BUY_COUNT}, Min order: {min_price:,}"
        )

        self.add_spot_callback = add_spot_callback

        self.logger.info(f"Strategy initialized with budget: {self.budget}")
        self.logger.info(f"Simulation mode: {self.is_simulation}")

    # =====================================================================
    # 새 캔들 업데이트
    # =====================================================================

    def update_trading_info(self, info):
        if not self.is_intialized:
            return

        candle = None
        for item in info:
            if item.get("type") == "primary_candle":
                candle = item
                break

        if candle is None:
            return

        self.data.append(copy.deepcopy(candle))

        # 볼륨 기록 (volume 키가 없으면 acc_trade_volume/candle_acc_trade_volume도 시도)
        vol = None
        for k in ("volume", "candle_acc_trade_volume", "acc_trade_volume"):
            if k in candle:
                try:
                    vol = float(candle[k])
                except (TypeError, ValueError):
                    vol = None
                break
        self.volumes.append(vol)

        self._update_indicators_for_last_candle()

        idx = len(self.data) - 1

        if self.total_amount > 0:
            self._check_sell_conditions(idx)

        if self.request is None:
            self._process_window(idx)

    # =====================================================================
    # 지표 계산
    # =====================================================================

    def _update_indicators_for_last_candle(self):
        n = len(self.data)
        if n == 0:
            return

        closes = pd.Series([d["closing_price"] for d in self.data], dtype="float")
        highs = pd.Series([d["high_price"] for d in self.data], dtype="float")
        lows = pd.Series([d["low_price"] for d in self.data], dtype="float")

        c = self.data[-1]

        c["bb_lower"] = None
        c["rsi"] = None
        c["macd"] = None
        c["stoch_k"] = None

        if n >= 20:
            ma20 = closes.rolling(20).mean()
            std20 = closes.rolling(20).std()
            bb_lower_series = ma20 - 2 * std20
            c["bb_lower"] = float(bb_lower_series.iloc[-1])

        if n >= 14:
            delta = closes.diff()
            gain = delta.clip(lower=0)
            loss = -delta.clip(upper=0)
            avg_gain = gain.rolling(14).mean()
            avg_loss = loss.rolling(14).mean()
            rs = avg_gain / avg_loss.replace(to_replace=0, value=np.nan)
            rsi_series = 100 - (100 / (1 + rs))
            c["rsi"] = float(rsi_series.iloc[-1])

        if n >= 26:
            ema12 = closes.ewm(span=12, adjust=False).mean()
            ema26 = closes.ewm(span=26, adjust=False).mean()
            macd_line = ema12 - ema26
            c["macd"] = float(macd_line.iloc[-1])

        if n >= 14:
            low14 = lows.rolling(14).min()
            high14 = highs.rolling(14).max()
            denom = (high14 - low14).replace(to_replace=0, value=np.nan)
            raw_k = (closes - low14) / denom * 100
            smooth_k = raw_k.rolling(3).mean()
            c["stoch_k"] = float(smooth_k.iloc[-1])

        if n >= self.ATR_PERIOD + 1:
            prev_closes = closes.shift(1)
            tr1 = highs - lows
            tr2 = (highs - prev_closes).abs()
            tr3 = (lows - prev_closes).abs()
            tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
            atr_series = tr.rolling(self.ATR_PERIOD).mean()
            current_atr = float(atr_series.iloc[-1])
            c["atr"] = current_atr

            self.atr_values.append(current_atr)
            if len(self.atr_values) > self.ATR_HISTORY_SIZE:
                self.atr_values.pop(0)
        else:
            c["atr"] = None

        if n >= self.EMA_PERIOD:
            ema_series = closes.ewm(span=self.EMA_PERIOD, adjust=False).mean()
            c["ema"] = float(ema_series.iloc[-1])
        else:
            c["ema"] = None

    # =====================================================================
    # 3차 이상(3~5차) 보수적 진입 필터
    # =====================================================================

    def _check_late_buy_filters(self, candle) -> bool:
        rsi = candle.get("rsi")
        macd = candle.get("macd")
        stoch = candle.get("stoch_k")
        ema = candle.get("ema")
        close = candle.get("closing_price")

        if rsi is None or macd is None or stoch is None or ema is None or close is None:
            self.logger.info("[LATE-BUY BLOCK] Indicator is None.")
            return False

        if rsi > self.LATE_RSI_LIMIT:
            self.logger.info(
                f"[LATE-BUY BLOCK] RSI {rsi:.2f} > {self.LATE_RSI_LIMIT}"
            )
            return False

        if macd > self.LATE_MACD_LIMIT:
            self.logger.info(
                f"[LATE-BUY BLOCK] MACD {macd:,.0f} > {self.LATE_MACD_LIMIT}"
            )
            return False

        if stoch > self.LATE_STOCH_LIMIT:
            self.logger.info(
                f"[LATE-BUY BLOCK] Stoch {stoch:.2f} > {self.LATE_STOCH_LIMIT}"
            )
            return False

        ema_dist = (ema - close) / ema * 100
        if ema_dist < self.LATE_EMA_DISTANCE_MIN:
            self.logger.info(
                f"[LATE-BUY BLOCK] EMA distance {ema_dist:.2f}% "
                f"< {self.LATE_EMA_DISTANCE_MIN}%"
            )
            return False

        self.logger.info(
            f"[LATE-BUY OK] RSI={rsi:.2f}, MACD={macd:,.0f}, "
            f"Stoch={stoch:.2f}, EMA_DIST={ema_dist:.2f}%"
        )
        return True

    # =====================================================================
    # 볼륨 스파이크 판단
    # =====================================================================

    def _is_volume_spike(self, idx: int) -> bool:
        """
        현재 idx에서 볼륨 스파이크 여부 판단.
        - volume 데이터가 없거나 샘플 부족 시 False
        """
        if idx < 0 or idx >= len(self.volumes):
            return False

        current_vol = self.volumes[idx]
        if current_vol is None or current_vol <= 0:
            return False

        start = max(0, idx - self.VOL_MA_PERIOD + 1)
        window = self.volumes[start:idx + 1]
        window = [v for v in window if v is not None and v > 0]

        if len(window) < self.VOL_MIN_SAMPLES:
            return False

        avg_vol = float(np.mean(window))
        if avg_vol <= 0:
            return False

        if current_vol >= avg_vol * self.VOL_SPIKE_FACTOR:
            self.logger.info(
                f"[VOL] Volume spike detected at idx={idx}: "
                f"vol={current_vol:.0f}, avg={avg_vol:.0f}, "
                f"factor={current_vol/avg_vol:.2f}x"
            )
            return True

        return False

    # =====================================================================
    # 차수별 동적 익절 임계값
    # =====================================================================

    def _get_dynamic_breakeven_exit(self) -> float:
        if self.buy_count <= 0:
            return self.BREAKEVEN_EXIT

        idx = self.buy_count - 1
        if idx >= len(self.BREAKEVEN_EXIT_THRESHOLDS):
            idx = len(self.BREAKEVEN_EXIT_THRESHOLDS) - 1

        return self.BREAKEVEN_EXIT_THRESHOLDS[idx]

    # =====================================================================
    # 매도 조건 (비상 손절 + 급등 트레일링 + 적응형 TP)
    # =====================================================================

    def _check_sell_conditions(self, idx):
        if self.total_amount <= 0 or self.average_price <= 0:
            return

        candle = self.data[idx]
        current_price = float(candle["closing_price"])
        profit = (current_price - self.average_price) / self.average_price  # 수익률

        # 1) 5차 이후 최대 손실 (-2%) 손절
        if self.buy_count >= self.MAX_BUY_COUNT:
            drop_from_avg = (self.average_price - current_price) / self.average_price
            if drop_from_avg >= self.MAX_LOSS_AFTER_5TH:
                self.logger.info(
                    f"[SELL] Max loss after 5th: "
                    f"drop={drop_from_avg*100:.2f}% "
                    f">= {self.MAX_LOSS_AFTER_5TH*100:.2f}%"
                )
                self._issue_sell_all(idx, "MAX_LOSS_AFTER_5TH")
                return

        # 2) 1~2차 비상 손절 (-8%)
        if (
            self.buy_count <= self.EMERGENCY_STOP_MAX_BUY_COUNT
            and profit <= -self.EMERGENCY_STOP_LOSS
        ):
            self.logger.info(
                f"[SELL] EMERGENCY_STOP: profit={profit*100:.2f}% "
                f"<= -{self.EMERGENCY_STOP_LOSS*100:.1f}% "
                f"(buy_count={self.buy_count})"
            )
            self._issue_sell_all(idx, "EMERGENCY_STOP")
            return

        # 3) 급등 트레일링 (RALLY)
        if profit >= self.RALLY_START_PROFIT:
            if not self.rally_active:
                self.rally_active = True
                self.rally_high_price = current_price
                self.logger.info(
                    f"[RALLY] Enter rally mode: "
                    f"profit={profit*100:.2f}% "
                    f">= {self.RALLY_START_PROFIT*100:.2f}%"
                )
            else:
                if current_price > self.rally_high_price:
                    self.rally_high_price = current_price

            trail_stop = self.rally_high_price * (1 - self.RALLY_TRAIL_DROP)
            if current_price <= trail_stop:
                self.logger.info(
                    f"[SELL] RALLY_TRAIL_STOP: "
                    f"price={current_price:,.0f}, "
                    f"trail_stop={trail_stop:,.0f}, "
                    f"high={self.rally_high_price:,.0f}, "
                    f"profit={profit*100:.2f}%"
                )
                self._issue_sell_all(idx, "RALLY_TRAIL_STOP")
                return
        else:
            # 수익이 0 미만으로 떨어지면 랠리 모드 종료
            if self.rally_active and profit < 0:
                self.logger.info(
                    f"[RALLY] Exit rally mode: profit back below 0 "
                    f"({profit*100:.2f}%)."
                )
                self.rally_active = False
                self.rally_high_price = 0.0

        # 4) 차수별 동적 익절 (랠리 모드가 아닐 때만)
        dynamic_exit = self._get_dynamic_breakeven_exit()
        if (not self.rally_active) and profit >= dynamic_exit:
            self.logger.info(
                f"[SELL] DYNAMIC_EXIT: profit={profit*100:.2f}% "
                f">= {dynamic_exit*100:.2f}% "
                f"(buy_count={self.buy_count})"
            )
            self._issue_sell_all(idx, "DYNAMIC_BREAKEVEN_EXIT")
            self.tp3_active = False
            self.stage_1_done = False
            self.stage_2_done = False
            self.remaining_ratio = 1.0
            self.rally_active = False
            self.rally_high_price = 0.0
            return

        # 아래 TP1/TP2/TP3 로직은 유지
        if self.tp3_active:
            if current_price > self.tp3_high_price:
                self.tp3_high_price = current_price

            trail_stop = self.tp3_high_price * (1 - self.TP3_TRAIL_DROP)
            if current_price <= trail_stop:
                self.logger.info(
                    f"[SELL] TP3 Trailing Stop: "
                    f"price={current_price:,.0f}, "
                    f"trail_stop={trail_stop:,.0f}, "
                    f"high={self.tp3_high_price:,.0f}"
                )
                self._issue_sell_all(idx, "TP3_TRAIL_STOP")
                self.tp3_active = False
                self.stage_1_done = False
                self.stage_2_done = False
                self.remaining_ratio = 1.0
                self.rally_active = False
                self.rally_high_price = 0.0
                return

            if (idx - self.tp3_start_idx) >= self.TP3_HOLD_BARS \
               and profit >= self.TP3_START_PROFIT:
                self.logger.info(
                    f"[SELL] TP3 Time Exit: "
                    f"bars={idx - self.tp3_start_idx}, "
                    f"profit={profit*100:.2f}%"
                )
                self._issue_sell_all(idx, "TP3_TIME_EXIT")
                self.tp3_active = False
                self.stage_1_done = False
                self.stage_2_done = False
                self.remaining_ratio = 1.0
                self.rally_active = False
                self.rally_high_price = 0.0
                return

            return

        if (not self.stage_1_done) and profit >= self.PROFIT_STAGE_1:
            self.logger.info(
                f"[SELL] TP1: profit={profit*100:.2f}% "
                f">= {self.PROFIT_STAGE_1*100:.2f}% "
                f"(Sell {self.SELL_RATIO_STAGE_1*100:.0f}%)"
            )
            ratio = self.SELL_RATIO_STAGE_1
            self._issue_sell_partial(idx, ratio, "TP1")
            self.stage_1_done = True
            self.remaining_ratio -= ratio
            return

        if self.stage_1_done and self.TP2_PROFIT_MIN <= profit < self.TP3_START_PROFIT:
            self.logger.info(
                f"[SELL] TP2: profit={profit*100:.2f}% in "
                f"[{self.TP2_PROFIT_MIN*100:.2f}%, {self.TP2_PROFIT_MAX*100:.2f}%]"
            )
            self._issue_sell_all(idx, "TP2_FULL_EXIT")
            self.stage_1_done = False
            self.stage_2_done = False
            self.tp3_active = False
            self.remaining_ratio = 0.0
            self.rally_active = False
            self.rally_high_price = 0.0
            return

        if self.stage_1_done and profit >= self.TP3_START_PROFIT:
            self.logger.info(
                f"[TP3] Enter: profit={profit*100:.2f}% "
                f">= {self.TP3_START_PROFIT*100:.2f}%"
            )
            self.tp3_active = True
            self.tp3_start_idx = idx
            self.tp3_high_price = current_price
            return

    # =====================================================================
    # 윈도우 / 매수 로직
    # =====================================================================

    def _process_window(self, idx):
        candle = self.data[idx]

        bb_lower = candle.get("bb_lower")
        rsi = candle.get("rsi")
        macd = candle.get("macd")
        stoch = candle.get("stoch_k")
        atr = candle.get("atr")
        ema = candle.get("ema")

        if bb_lower is None or rsi is None or macd is None or stoch is None:
            return
        if atr is None or ema is None:
            return

        close = candle["closing_price"]
        low = candle["low_price"]

        # 1) 윈도우 시작 조건
        if (not self.in_window) and low <= bb_lower:
            # 전량 매도 후 쿨다운
            if self.total_amount == 0 and self.last_sell_idx >= 0:
                if (idx - self.last_sell_idx) < self.SELL_COOLDOWN_TICKS:
                    cooldown_remaining = self.SELL_COOLDOWN_TICKS - (idx - self.last_sell_idx)
                    self.logger.info(
                        f"[COOLDOWN-SELL] 전량 매도 후 쿨다운 중 "
                        f"(남은 {cooldown_remaining}틱)"
                    )
                    return

            # ATR 필터
            if len(self.atr_values) >= 50:
                atr_threshold = np.percentile(self.atr_values, self.ATR_PERCENTILE)
                if atr < atr_threshold:
                    self.logger.info(
                        f"[BLOCKED] Window blocked by ATR: {atr:,.0f} < "
                        f"threshold {atr_threshold:,.0f}"
                    )
                    return

            # EMA 거리 필터
            ema_distance_percent = (ema - close) / ema * 100
            if ema_distance_percent < self.EMA_DISTANCE_PERCENT_MIN:
                self.logger.info(
                    f"[BLOCKED] Window blocked by EMA: distance "
                    f"{ema_distance_percent:.2f}% < {self.EMA_DISTANCE_PERCENT_MIN}%"
                )
                return

            if self.buy_count >= self.MAX_BUY_COUNT:
                return

            if self.balance < self.BASE_POSITION_SIZE:
                return

            # 윈도우 시작
            self.in_window = True
            self.window_start_idx = idx

            self.flag_rsi = False
            self.flag_macd = False
            self.flag_stoch = False
            self.did_buy_this_window = False

            atr_threshold = (
                np.percentile(self.atr_values, self.ATR_PERCENTILE)
                if len(self.atr_values) >= 50
                else 0
            )
            ema_distance = (ema - close) / ema * 100

            self.logger.info(
                f"[WINDOW] Window started at idx {idx}, price={close:,.0f}"
            )
            self.logger.info(
                f"  [OK] ATR: {atr:,.0f} >= {atr_threshold:,.0f}"
            )
            self.logger.info(
                f"  [OK] EMA distance: {ema_distance:.2f}% >= "
                f"{self.EMA_DISTANCE_PERCENT_MIN}%"
            )
            self.logger.info(
                f"  [INFO] Target: RSI<={self.RSI_LIMIT}, "
                f"MACD<={self.MACD_LIMIT}, Stoch<={self.STOCH_LIMIT}"
            )

        # 2) 윈도우 내부 처리
        if self.in_window:
            if rsi <= self.RSI_LIMIT:
                if not self.flag_rsi:
                    self.logger.info(f"  [OK] RSI: {rsi:.2f} <= {self.RSI_LIMIT}")
                self.flag_rsi = True
            if macd <= self.MACD_LIMIT:
                if not self.flag_macd:
                    self.logger.info(f"  [OK] MACD: {macd:,.0f} <= {self.MACD_LIMIT}")
                self.flag_macd = True
            if stoch <= self.STOCH_LIMIT:
                if not self.flag_stoch:
                    self.logger.info(f"  [OK] Stoch: {stoch:.2f} <= {self.STOCH_LIMIT}")
                self.flag_stoch = True

            if self.flag_rsi and self.flag_macd and self.flag_stoch:
                elapsed_ticks = idx - self.window_start_idx

                if elapsed_ticks > self.TIME_WINDOW_FOR_BUY:
                    self.logger.info(
                        f"[TIMEOUT] Time window exceeded! "
                        f"{elapsed_ticks} > {self.TIME_WINDOW_FOR_BUY}"
                    )
                    self._reset_window()
                    return

                # 차수별 매수 금액 + 쿨다운
                if self.buy_count < self.MAX_BUY_COUNT:
                    weight = self.BUY_WEIGHTS[self.buy_count]
                    buy_budget = int(self.BASE_POSITION_SIZE * weight)

                    can_buy = (
                        self.balance >= buy_budget
                        and (idx - self.last_buy_idx) >= self.BUY_COOLDOWN_TICKS
                    )
                else:
                    can_buy = False

                if can_buy:
                    # 3차 이상: 보수적 지표 필터
                    if self.buy_count >= 2:
                        if not self._check_late_buy_filters(candle):
                            return

                    # 2차 이상: 평단 손실률(DRAWDOWN) 필터
                    if self.buy_count > 0 and self.average_price > 0:
                        if close >= self.average_price:
                            self.logger.info(
                                f"[BLOCKED] 매수 직전 차단: "
                                f"현재가 {close:,.0f} >= 평단가 {self.average_price:,.0f}"
                            )
                            return

                        drawdown = (self.average_price - close) / self.average_price
                        idx_dd = min(self.buy_count, len(self.DRAWDOWN_THRESHOLDS) - 1)
                        dd_threshold = self.DRAWDOWN_THRESHOLDS[idx_dd]

                        if drawdown < dd_threshold:
                            self.logger.info(
                                f"[BLOCKED] DRAWDOWN filter: "
                                f"drawdown={drawdown*100:.2f}% "
                                f"< threshold {dd_threshold*100:.2f}% "
                                f"(buy_count={self.buy_count})"
                            )
                            return
                        else:
                            self.logger.info(
                                f"[ALLOW] DRAWDOWN OK: "
                                f"drawdown={drawdown*100:.2f}% "
                                f">= {dd_threshold*100:.2f}% "
                                f"(buy_count={self.buy_count})"
                            )

                        # ✅ 3차 이상부터는 볼륨 스파이크 필요
                        if self.buy_count >= 2:
                            if not self._is_volume_spike(idx):
                                self.logger.info(
                                    "[BLOCKED] Volume spike not detected for "
                                    f"late DCA (buy_count={self.buy_count})."
                                )
                                return
                            else:
                                self.logger.info(
                                    "[ALLOW] Volume spike confirmed for "
                                    f"late DCA (buy_count={self.buy_count})."
                                )

                    elif self.buy_count == 0:
                        self.logger.info("[ALLOW] 1st BUY: no drawdown filter applied.")

                    self.logger.info(
                        f"[BUY] ALL CONDITIONS MET! Time OK "
                        f"({elapsed_ticks} <= {self.TIME_WINDOW_FOR_BUY}), "
                        f"cooldown OK ({idx - self.last_buy_idx} >= {self.BUY_COOLDOWN_TICKS}). "
                        f"Buy #{self.buy_count + 1} at {close:,.0f}"
                    )
                    self._issue_buy(idx)
                    self.last_buy_idx = idx

                    if self.buy_count >= self.MAX_BUY_COUNT:
                        self.logger.info(
                            f"[DONE] Max buy count reached ({self.buy_count}). "
                            "Window closed."
                        )
                        self._reset_window()
                        return

            end_idx = self.window_start_idx + self.WINDOW_SIZE - 1
            if idx >= end_idx:
                self.logger.info(
                    f"[CLOSED] Window closed at idx {idx}. "
                    f"Flags: RSI={self.flag_rsi}, MACD={self.flag_macd}, "
                    f"Stoch={self.flag_stoch}, Buy count={self.buy_count}"
                )
                self._reset_window()

    def _reset_window(self):
        self.in_window = False
        self.window_start_idx = None

        self.flag_rsi = False
        self.flag_macd = False
        self.flag_stoch = False
        self.did_buy_this_window = False

    # =====================================================================
    # 매수 주문
    # =====================================================================

    def _issue_buy(self, buy_idx):
        if self.buy_count >= self.MAX_BUY_COUNT:
            return

        candle = self.data[buy_idx]
        price = float(candle["closing_price"])

        weight = self.BUY_WEIGHTS[self.buy_count]
        buy_budget = int(self.BASE_POSITION_SIZE * weight)

        if self.balance < buy_budget:
            self.logger.warning(
                f"[BLOCKED] Issue Buy: balance {self.balance:,} < buy_budget {buy_budget:,}"
            )
            return

        buy_budget_after_fee = buy_budget * (1 - self.COMMISSION)

        raw_amount = buy_budget_after_fee / price
        amount = self._normalize_amount(raw_amount)

        if amount <= 0:
            return

        if price * amount < self.min_price:
            self.logger.warning(f"Order amount too small: {price * amount}")
            return

        self.buy_prices.append(price)
        self.buy_amounts.append(amount)
        self.buy_count += 1

        if self.add_spot_callback:
            self.add_spot_callback(candle["date_time"], price)

        self.logger.info(
            f"Buy #{self.buy_count} (weight {weight:.1f}): "
            f"{amount:.{self.AMOUNT_DECIMALS}f} at {price:,.0f}"
        )

        self.request = {
            "id": DateConverter.timestamp_id(),
            "type": "buy",
            "price": price,
            "amount": amount,
        }

    # =====================================================================
    # 매도 주문
    # =====================================================================

    def _issue_sell_partial(self, sell_idx, ratio, reason=""):
        if self.total_amount <= 0:
            return
        candle = self.data[sell_idx]
        price = float(candle["closing_price"])

        raw_amount = self.total_amount * ratio
        amount = self._normalize_amount(raw_amount)

        if amount > self.total_amount:
            amount = self.total_amount
        if amount <= 0:
            return

        if self.add_spot_callback:
            self.add_spot_callback(candle["date_time"], price)

        profit = (price - self.average_price) / self.average_price * 100
        self.logger.info(
            f"Sell {ratio*100:.0f}%: {amount:.{self.AMOUNT_DECIMALS}f} at {price:,.0f} "
            f"({reason}, {profit:+.2f}%)"
        )

        self.request = {
            "id": DateConverter.timestamp_id(),
            "type": "sell",
            "price": price,
            "amount": amount,
        }

    def _issue_sell_all(self, sell_idx, reason=""):
        if self.total_amount <= 0:
            return
        candle = self.data[sell_idx]
        price = float(candle["closing_price"])

        amount = self._normalize_amount(self.total_amount)
        if amount <= 0:
            return

        if self.add_spot_callback:
            self.add_spot_callback(candle["date_time"], price)

        profit = (price - self.average_price) / self.average_price * 100
        self.logger.info(
            f"Sell ALL: {amount:.{self.AMOUNT_DECIMALS}f} at {price:,.0f} "
            f"({reason}, {profit:+.2f}%)"
        )

        self.request = {
            "id": DateConverter.timestamp_id(),
            "type": "sell",
            "price": price,
            "amount": amount,
        }

    # =====================================================================
    # 체결 결과 처리
    # =====================================================================

    def update_result(self, result):
        if not self.is_intialized:
            return

        try:
            request = result["request"]

            if result["state"] == "requested":
                self.waiting_requests[request["id"]] = result
                self.logger.info(f"Order requested: {request['id']}")
                return

            if result["state"] == "done" and request["id"] in self.waiting_requests:
                del self.waiting_requests[request["id"]]

            price = float(result["price"])
            raw_amount = float(result["amount"])
            amount = self._normalize_amount(raw_amount)

            total = price * amount
            fee = total * self.COMMISSION

            if result.get("msg") == "success":
                if result["type"] == "buy":
                    self.balance -= round(total + fee)
                    prev_amount = self.total_amount

                    self.total_amount = self._normalize_amount(self.total_amount + amount)

                    if prev_amount <= 0:
                        self.average_price = price
                    else:
                        self.average_price = (
                            (self.average_price * prev_amount) + total
                        ) / max(self.total_amount, 1e-12)

                    self.logger.info(
                        f"[FILLED] BUY #{self.buy_count}: "
                        f"{amount:.{self.AMOUNT_DECIMALS}f} at {price:,.0f} "
                        f"(avg: {self.average_price:,.0f}, "
                        f"total_amount: {self.total_amount:.{self.AMOUNT_DECIMALS}f})"
                    )

                elif result["type"] == "sell":
                    self.balance += round(total - fee)
                    self.total_amount = self._normalize_amount(self.total_amount - amount)

                    if self.total_amount < 1e-8:
                        # 포지션 완전 종료 → 상태 초기화 + 쿨다운 시작
                        self.total_amount = 0
                        self.buy_count = 0
                        self.buy_prices = []
                        self.buy_amounts = []
                        self.average_price = 0

                        self.stage_1_done = False
                        self.stage_2_done = False
                        self.remaining_ratio = 1.0
                        self.trailing_active = False
                        self.max_price_after_target = 0
                        self.tp3_active = False
                        self.tp3_start_idx = -1
                        self.tp3_high_price = 0.0

                        self.rally_active = False
                        self.rally_high_price = 0.0

                        current_idx = len(self.data) - 1
                        self.last_sell_idx = current_idx
                        self.last_buy_idx = -999

                        if self.in_window:
                            self.logger.info("[FORCE_CLOSE] Window closed due to sell.")
                            self._reset_window()

                        self.logger.info(
                            f"[SUCCESS] Position closed. Balance: {self.balance:,}"
                        )
                        self.logger.info(
                            f"[COOLDOWN-SELL] 전량 매도 완료. idx={current_idx}, "
                            f"쿨다운 {self.SELL_COOLDOWN_TICKS}틱 시작."
                        )
                    else:
                        self.logger.info(
                            f"[SUCCESS] Partial sell: {amount:.{self.AMOUNT_DECIMALS}f} "
                            f"at {price:,.0f}"
                        )
                        self.logger.info(
                            f"Remaining: {self.total_amount:.{self.AMOUNT_DECIMALS}f}"
                        )

            self.result.append(copy.deepcopy(result))

        except (KeyError, TypeError, ValueError) as err:
            self.logger.error(f"update_result error: {err}")

    # =====================================================================
    # 주문 반환
    # =====================================================================

    def get_request(self):
        if not self.is_intialized:
            return None

        # 시뮬레이션이면 "데이터 마지막 캔들 시각"을 요청 시각으로 유지
        if self.is_simulation and self.data:
            last_dt = datetime.strptime(self.data[-1]["date_time"], self.ISO)
            now = last_dt.isoformat()
        else:
            now = datetime.now().strftime(self.ISO)

        # 주문이 없으면:
        # - 시뮬레이션: noop(0/0) buy를 반환해서 turn 진행을 유지
        # - 실전: None 반환
        if self.request is None:
            if self.is_simulation:
                return [
                    {
                        "id": DateConverter.timestamp_id(),
                        "type": "buy",
                        "price": 0,
                        "amount": 0,
                        "date_time": now,
                    }
                ]
            return None

        req = copy.deepcopy(self.request)
        req["date_time"] = now
        self.request = None

        # 실전일 때만 "REQ 로그"를 남기고 싶으면 아래처럼 조건을 걸어도 됩니다.
        # (현재는 공통 로그 유지)
        self.logger.info(
            f"[REQ] {req['type'].upper()} order: "
            f"{req['amount']:.{self.AMOUNT_DECIMALS}f} at {req['price']:,.0f}"
        )

        final_requests = []

        # 대기 주문 취소는 실전에서 의미가 큼
        # 시뮬레이션에서는 대기주문이 사실상 없도록 구성되어 있다면,
        # 아래 블록을 is_simulation 체크로 스킵해도 됩니다.
        for request_id in list(self.waiting_requests.keys()):
            self.logger.info(f"Cancel pending request: {request_id}")
            final_requests.append(
                {
                    "id": request_id,
                    "type": "cancel",
                    "price": 0,
                    "amount": 0,
                    "date_time": now,
                }
            )

        final_requests.append(req)
        return final_requests
