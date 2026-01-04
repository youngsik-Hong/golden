import os
from typing import Optional, List, Dict

import matplotlib
# GUI 안 띄우고 파일로만 저장하는 백엔드
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
import mplfinance as mpf
import matplotlib.dates as mdates
import logging


# ------------------------------------------------
#  보조지표 계산 함수들
# ------------------------------------------------
def compute_bbands(df: pd.DataFrame, window: int = 20, k: float = 2.0) -> pd.DataFrame:
    """종가 기준 볼린저밴드 계산."""
    out = df.copy()
    mid = out["Close"].rolling(window, min_periods=window).mean()
    std = out["Close"].rolling(window, min_periods=window).std(ddof=0)
    out["BB_MID"] = mid
    out["BB_UPPER"] = mid + k * std
    out["BB_LOWER"] = mid - k * std
    return out


def compute_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """RSI(14) 계산 (Wilder 방식 지수평활)."""
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(alpha=1.0 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, adjust=False).mean()

    rs = avg_gain / (avg_loss.replace(0, np.nan))
    rsi = 100 - (100 / (1 + rs))
    return rsi


def compute_macd(close: pd.Series,
                 fast: int = 12,
                 slow: int = 26,
                 signal: int = 9) -> pd.DataFrame:
    """
    MACD(12,26,9) 계산.
    반환: DataFrame(columns=['MACD','SIGNAL','HIST'])
    """
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    macd = ema_fast - ema_slow
    signal_line = macd.ewm(span=signal, adjust=False).mean()
    hist = macd - signal_line

    return pd.DataFrame(
        {
            "MACD": macd,
            "SIGNAL": signal_line,
            "HIST": hist,
        },
        index=close.index,
    )


def compute_stoch(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    k_period: int = 14,
    d_period: int = 3,
) -> pd.DataFrame:
    """
    Stochastic Oscillator 계산.
    %K, %D 반환.
    """
    lowest_low = low.rolling(window=k_period, min_periods=k_period).min()
    highest_high = high.rolling(window=k_period, min_periods=k_period).max()

    stoch_k = (close - lowest_low) / (highest_high - lowest_low) * 100.0
    stoch_d = stoch_k.rolling(window=d_period, min_periods=d_period).mean()

    return pd.DataFrame(
        {"K": stoch_k, "D": stoch_d},
        index=close.index,
    )


# ------------------------------------------------
#  데이터 리샘플 & 트레이드 마커
# ------------------------------------------------
def _resample_for_plot(df: pd.DataFrame, agg_minutes: int = 5) -> pd.DataFrame:
    """
    시각화 용도로 1분봉을 n분봉으로 합칩니다.
    (시뮬레이션 로직에는 영향 X)
    """
    if agg_minutes <= 1:
        return df

    df_res = df.copy()
    rule = f"{agg_minutes}min"
    df_res = df_res.resample(rule).agg(
        {
            "Open": "first",
            "High": "max",
            "Low": "min",
            "Close": "last",
            "Volume": "sum",
        }
    )
    df_res = df_res.dropna(subset=["Open", "High", "Low", "Close"])
    return df_res


def _build_trade_series(
    plot_df: pd.DataFrame,
    trades: List[Dict],
    prefer_close_for_markers: bool = True,
):
    """
    trades 리스트를 받아서
    - 매수: 보라색 '^'
    - 매도: 빨간색 'v'
    에 대응하는 y 값 Series 두 개를 생성.
    """
    if trades is None or len(trades) == 0:
        return None, None

    idx = plot_df.index
    buy_y = pd.Series(np.nan, index=idx)
    sell_y = pd.Series(np.nan, index=idx)

    for t in trades:
        try:
            if isinstance(t, dict):
                ts_raw = (
                    t.get("timestamp")
                    or t.get("date_time")
                    or t.get("time")
                    or t.get("created_at")
                )
                side = t.get("side") or t.get("type") or t.get("position") or t.get("action")
                price = (
                    t.get("price")
                    or t.get("avg_price")
                    or t.get("fill_price")
                    or t.get("exec_price")
                    or t.get("close")
                )
            else:
                ts_raw = getattr(t, "timestamp", None)
                side = getattr(t, "side", None)
                price = getattr(t, "price", None)

            if ts_raw is None or side is None:
                continue

            ts = pd.to_datetime(ts_raw, errors="coerce")
            if pd.isna(ts):
                continue

            # 가장 가까운 캔들에 붙이기
            loc = idx.get_indexer([ts], method="nearest")
            if len(loc) == 0 or loc[0] < 0:
                continue
            bar_ts = idx[loc[0]]

            if not prefer_close_for_markers and price is not None:
                try:
                    y_val = float(price)
                except Exception:
                    y_val = float(plot_df.loc[bar_ts, "Close"])
            else:
                y_val = float(plot_df.loc[bar_ts, "Close"])

            side_str = str(side).upper()
            if any(k in side_str for k in ["BUY", "LONG", "B", "매수"]):
                buy_y.loc[bar_ts] = y_val
            elif any(k in side_str for k in ["SELL", "SHORT", "S", "매도"]):
                sell_y.loc[bar_ts] = y_val
        except Exception:
            continue

    if buy_y.notna().sum() == 0:
        buy_y = None
    if sell_y.notna().sum() == 0:
        sell_y = None

    return buy_y, sell_y


# ------------------------------------------------
#  메인 클래스
# ------------------------------------------------
class CandleGraphGenerator:
    """
    - 메인 캔들 + 볼린저밴드
    - 매수/매도 마커
    - 서브지표: Volume, RSI, MACD, Stochastic
    """

    def __init__(self, currency: str = "BTC", term_seconds: int = 60):
        self.currency = currency
        self.term_seconds = int(term_seconds)

    def _ensure_datetime_index(self, df: pd.DataFrame) -> pd.DataFrame:
        """인덱스를 DatetimeIndex로 강제 변환."""
        if isinstance(df.index, pd.DatetimeIndex):
            return df

        for col in ("date_time", "datetime", "timestamp", "ts"):
            if col in df.columns:
                idx = pd.to_datetime(df[col], errors="coerce")
                df = df.copy()
                df.index = idx
                break

        if not isinstance(df.index, pd.DatetimeIndex):
            idx_try = pd.to_datetime(df.index, errors="coerce")
            if isinstance(idx_try, pd.DatetimeIndex):
                df = df.copy()
                df.index = idx_try

        if not isinstance(df.index, pd.DatetimeIndex):
            raise ValueError("DataFrame index must be DatetimeIndex for plotting")

        return df

    def _make_style(
        self,
        candle_up_color: Optional[str] = None,
        candle_down_color: Optional[str] = None,
    ):
        """캔들 색상 스타일 생성."""
        if candle_up_color or candle_down_color:
            mc = mpf.make_marketcolors(
                up=(candle_up_color or "#26A69A"),
                down=(candle_down_color or "#F45B69"),
                wick="inherit",
                edge="inherit",
                volume="inherit",
            )
            return mpf.make_mpf_style(marketcolors=mc)
        return "charles"

    # ------------------------------------------------
    #  메인 엔트리
    # ------------------------------------------------
    # ------------------------------------------------
    #  메인 엔트리: 10틱 캔들 차트 + 보조지표
    # ------------------------------------------------
    def create_candle_chart(
        self,
        df: pd.DataFrame,
        filename: str,
        trades: Optional[List[Dict]] = None,
        show_bbands: bool = True,
        bb_window: int = 20,
        bb_k: float = 2.0,
        buy_color: str = "#00DD00",            # 초록색(매수) - Option A
        sell_color: str = "#FF0000",           # 빨간색(매도) - Option A
        candle_up_color: Optional[str] = None,
        candle_down_color: Optional[str] = None,
        prefer_close_for_markers: bool = True,
        target_date: Optional[pd.Timestamp] = None,
        show_yellow_windows: bool = True,      # 노란색 배경 표시 - 연하게
        rsi_threshold: float = 30.0,           # RSI 기준선 값
        macd_threshold: float = -200000.0,     # MACD 기준선 값
        stoch_threshold: float = 20.0,         # Stoch 기준선 값
        marker_size: int = 250,                # 매수/매도 마커 크기 (크게)
    ):
        """
        캔들 차트 + 보조지표 (Option A - 깔끔한 버전)
        + 볼린저 하단 돌파 spot
        + 10캔들 윈도우 구간 표시 (녹색만, 노란색은 선택적)
        + 윈도우 안 RSI/MACD/Stoch hit 마커
        + 윈도우별 rsi_min / macd_min / stoch_min 대표 마커(◆, 크기 1/2로 축소)
        + 윈도우 요약값(rsi_min, stoch_min, macd_min) CSV/로그 출력
        + rsi_min <= rsi_threshold & macd_min <= macd_threshold 인 윈도우를 "매수 후보"로 진하게 강조
        + RSI/MACD/Stoch 패널에 기준선 표시

        - df: (지금은 10틱으로 집계된) OHLCV 데이터프레임
        - trades: 전략 체결 내역 (매수/매도 마커용)
        - target_date:
            * None 이면 df 전체를 그림
            * 날짜가 들어오면 해당 날짜(D)의 00:00~24:00 데이터만 표시
              (지표 계산은 여전히 df 전체를 사용 → 워밍업 유지)
        - show_yellow_windows: True면 노란색 배경 표시, False면 녹색만 (Option A)
        - rsi_threshold: RSI 기준선 값 (기본 30.0)
        - macd_threshold: MACD 기준선 값 (기본 -200000.0)
        - stoch_threshold: Stoch 기준선 값 (기본 20.0)
        - marker_size: 매수/매도 마커 크기 (기본 150)
        """
        import os
        import logging
        import numpy as np

        logger = logging.getLogger(__name__)

        # ★ 매수 후보 윈도우 기준값 (파라미터로 받음)
        C_RSI_MIN_THRESHOLD = rsi_threshold
        C_MACD_MIN_THRESHOLD = macd_threshold

        # 1) 인덱스 정리
        df = self._ensure_datetime_index(df)

        needed = ["Open", "High", "Low", "Close", "Volume"]
        for col in needed:
            if col not in df.columns:
                raise ValueError(f"DataFrame must have column '{col}'")

        # 2) 전체 히스토리 정렬 (워밍업 포함)
        full_df = df.sort_index()

        # 3) 표시할 날짜 구간 결정
        day_start = day_end = None
        if target_date is not None:
            day_start = pd.to_datetime(target_date).normalize()
            day_end = day_start + pd.Timedelta(days=1)
            plot_df = full_df.loc[day_start:day_end].copy()
            if plot_df.empty:
                # 혹시 슬라이스가 비면 전체를 사용
                plot_df = full_df.copy()
                day_start = day_end = None
        else:
            plot_df = full_df.copy()

        # 항상 인덱스 기준으로 정렬
        plot_df = plot_df.sort_index()

        apds: List = []

        # 🎯 윈도우(10캔들) 구간: 시간 대신 "캔들 인덱스" 범위를 담는다.
        #   예: (5, 14) → 5번째 캔들부터 14번째 캔들까지 윈도우
        window_ranges: List[Tuple[int, int]] = []

        # 나중에 지표 hit 계산에 사용할 윈도우 마스크 (캔들 단위)
        window_mask = pd.Series(False, index=plot_df.index)

        # 지표 시리즈(후반 요약 계산에 필요)
        rsi: Optional[pd.Series] = None
        macd_df: Optional[pd.DataFrame] = None
        stoch_df: Optional[pd.DataFrame] = None

        # 후보 윈도우 인덱스들 (1-based window_index)
        candidate_window_indices: Set[int] = set()

        # ------------------------------------------------
        # 4) 볼린저 밴드 + 하단 돌파 spot + 윈도우 구간 계산
        # ------------------------------------------------
        fill_between_price = None
        lower_break_series = None  # 하단 돌파 위치(mark용)

        if show_bbands:
            try:
                bb_df = compute_bbands(full_df, window=bb_window, k=bb_k)
                bb_plot = bb_df.loc[plot_df.index]

                # 중심선 / 상단 / 하단 밴드
                apds.append(
                    mpf.make_addplot(
                        bb_plot["BB_MID"],
                        width=1.2,
                        color="#1f77b4",
                    )
                )
                apds.append(
                    mpf.make_addplot(
                        bb_plot["BB_UPPER"],
                        width=0.8,
                        color="#888888",
                    )
                )
                apds.append(
                    mpf.make_addplot(
                        bb_plot["BB_LOWER"],
                        width=0.8,
                        color="#888888",
                    )
                )

                # 밴드 사이 영역 살짝 채우기
                fill_between_price = dict(
                    y1=bb_plot["BB_LOWER"].values,
                    y2=bb_plot["BB_UPPER"].values,
                    alpha=0.18,
                )

                # --- 하단 밴드 돌파 조건 ---
                cond_break = (
                    (plot_df["Close"] <= bb_plot["BB_LOWER"])
                    & bb_plot["BB_LOWER"].notna()
                )
                # spot 은 캔들의 "저가" 위치에 찍음
                lower_break_series = plot_df["Low"].where(cond_break)

                # --- 윈도우 시작 조건: '처음으로' 하단 밴드를 내려간 시점 ---
                #   이전 캔들은 하단 위, 이번 캔들은 하단 이하
                cond_start = cond_break & (~cond_break.shift(1, fill_value=False))

                # 각 시작점마다 10캔들 윈도우 구간 계산 (인덱스 번호로 저장)
                window_len = 10  # 윈도우 길이(캔들 개수)
                idx_list = plot_df.index.to_list()
                for ts in plot_df.index[cond_start]:
                    try:
                        pos = idx_list.index(ts)  # ts 에 해당하는 캔들 번호
                    except ValueError:
                        continue
                    end_pos = min(pos + window_len - 1, len(idx_list) - 1)
                    window_ranges.append((pos, end_pos))

                # window_ranges 를 기반으로 캔들 단위 마스크 생성
                if window_ranges:
                    mask = window_mask.copy()
                    for (s_i, e_i) in window_ranges:
                        s_i = max(0, s_i)
                        e_i = min(len(idx_list) - 1, e_i)
                        if s_i <= e_i:
                            mask.iloc[s_i : e_i + 1] = True
                    window_mask = mask

            except Exception as e:
                logger.warning("[WARN] compute_bbands failed: %s", e)

        # ------------------------------------------------
        # 5) 매수/매도 마커 (전략 체결 내역)
        # ------------------------------------------------
        if trades is not None and len(trades) > 0:
            # target_date가 있으면 그 날의 체결만 사용
            if day_start is not None and day_end is not None:
                filtered_trades = []
                for t in trades:
                    try:
                        ts = pd.to_datetime(
                            t.get("timestamp")
                            or t.get("date_time")
                            or t.get("time")
                            or t.get("created_at")
                        )
                        if day_start <= ts < day_end:
                            filtered_trades.append(t)
                    except Exception:
                        continue
                trades_use = filtered_trades
            else:
                trades_use = trades

            if trades_use:
                try:
                    buy_s, sell_s = _build_trade_series(
                        plot_df,
                        trades_use,
                        prefer_close_for_markers=prefer_close_for_markers,
                    )
                    if buy_s is not None:
                        apds.append(
                            mpf.make_addplot(
                                buy_s,
                                type="scatter",
                                markersize=marker_size,  # 파라미터 사용 (기본 150)
                                marker="^",              # 삼각형 위
                                color=buy_color,
                                panel=0,
                                secondary_y=False,
                            )
                        )
                    if sell_s is not None:
                        apds.append(
                            mpf.make_addplot(
                                sell_s,
                                type="scatter",
                                markersize=marker_size,  # 파라미터 사용 (기본 150)
                                marker="v",              # 삼각형 아래
                                color=sell_color,
                                panel=0,
                                secondary_y=False,
                            )
                        )
                except Exception as e:
                    logger.warning("[WARN] _build_trade_series failed: %s", e)

        # ------------------------------------------------
        # 6) RSI(14) 패널 (panel=2) + 윈도우 안 hit & 윈도우별 rsi_min 마커
        # ------------------------------------------------
        rsi_min_series = None
        try:
            rsi_full = compute_rsi(full_df["Close"], period=14)
            rsi = rsi_full.loc[plot_df.index]

            apds.append(
                mpf.make_addplot(
                    rsi,
                    panel=2,
                    color="#0000FF",
                    width=1.0,
                    ylabel="RSI(14)",
                )
            )
            # Option A: 주요 기준선만 표시 (파라미터 기반)
            # 70선 (상단)
            line_70 = pd.Series(70.0, index=rsi.index)
            apds.append(
                mpf.make_addplot(
                    line_70,
                    panel=2,
                    color="#BBBBBB",
                    width=0.8,
                    linestyle="--",
                )
            )
            # rsi_threshold 기준선 (강조) - Option A
            line_threshold = pd.Series(rsi_threshold, index=rsi.index)
            apds.append(
                mpf.make_addplot(
                    line_threshold,
                    panel=2,
                    color="#FF0000",  # 빨간색으로 강조
                    width=1.5,         # 두껍게
                    linestyle="--",
                )
            )

            # ★ RSI hit 마커 제거 - 차트가 너무 복잡해짐
            # rsi_mask = window_mask.reindex(rsi.index, fill_value=False)
            # rsi_hit = rsi.where((rsi <= rsi_threshold) & rsi_mask)
            # apds.append(
            #     mpf.make_addplot(
            #         rsi_hit,
            #         panel=2,
            #         type="scatter",
            #         markersize=25,
            #         marker="o",
            #         color="#AA00FF",  # 보라색 점 = RSI hit
            #     )
            # )

            # ★ RSI 다이아몬드 마커 제거 - 차트가 너무 복잡해짐
            # rsi_min_series = pd.Series(np.nan, index=rsi.index)
            # if window_ranges:
            #     for (s_i, e_i) in window_ranges:
            #         sub = rsi.iloc[s_i : e_i + 1].dropna()
            #         if sub.empty:
            #             continue
            #         min_idx = sub.idxmin()
            #         rsi_min_series.loc[min_idx] = sub.min()
            # apds.append(
            #     mpf.make_addplot(
            #         rsi_min_series,
            #         panel=2,
            #         type="scatter",
            #         markersize=16,   # 기존 55 → 절반 정도
            #         marker="D",
            #         color="#FF00FF",   # 진한 핑크 다이아 = 윈도우 rsi_min
            #     )
            # )

        except Exception as e:
            logger.warning("[WARN] compute_rsi failed: %s", e)

        # ------------------------------------------------
        # 7) MACD 패널 (panel=3) + 윈도우 안 hit & 윈도우별 macd_min 마커
        # ------------------------------------------------
        macd_min_series = None
        try:
            macd_full = compute_macd(full_df["Close"])
            macd_df = macd_full.loc[plot_df.index]

            apds.append(
                mpf.make_addplot(
                    macd_df["MACD"],
                    panel=3,
                    color="#FF9900",
                    width=1.5,
                    ylabel="MACD",
                )
            )
            apds.append(
                mpf.make_addplot(
                    macd_df["SIGNAL"],
                    panel=3,
                    color="#0066CC",
                    width=1.2,
                )
            )
            apds.append(
                mpf.make_addplot(
                    macd_df["HIST"],
                    type="bar",
                    panel=3,
                    color=["#FF6666" if v >= 0 else "#66CC66" for v in macd_df["HIST"]],
                    alpha=0.6,
                )
            )
            
            # Option A: macd_threshold 기준선 추가
            line_macd_threshold = pd.Series(macd_threshold, index=macd_df.index)
            apds.append(
                mpf.make_addplot(
                    line_macd_threshold,
                    panel=3,
                    color="#FF0000",  # 빨간색으로 강조
                    width=1.5,         # 두껍게
                    linestyle="--",
                )
            )

            # ★ MACD hit 마커 제거 - 차트가 너무 복잡해짐
            # macd_mask = window_mask.reindex(macd_df.index, fill_value=False)
            # macd_hit = macd_df["MACD"].where(
            #     (macd_df["MACD"] <= macd_threshold) & macd_mask
            # )
            # apds.append(
            #     mpf.make_addplot(
            #         macd_hit,
            #         panel=3,
            #         type="scatter",
            #         markersize=25,
            #         marker="o",
            #         color="#00AA55",  # 초록 점 = MACD hit
            #     )
            # )

            # ★ MACD 다이아몬드 마커 제거 - 차트가 너무 복잡해짐
            # macd_min_series = pd.Series(np.nan, index=macd_df.index)
            # if window_ranges:
            #     for (s_i, e_i) in window_ranges:
            #         sub = macd_df["MACD"].iloc[s_i : e_i + 1].dropna()
            #         if sub.empty:
            #             continue
            #         min_idx = sub.idxmin()
            #         macd_min_series.loc[min_idx] = sub.min()
            # apds.append(
            #     mpf.make_addplot(
            #         macd_min_series,
            #         panel=3,
            #         type="scatter",
            #         markersize=16,   # 기존 55 → 절반 정도
            #         marker="D",
            #         color="#008833",   # 진한 초록 다이아 = 윈도우 macd_min
            #     )
            # )

        except Exception as e:
            logger.warning("[WARN] compute_macd failed: %s", e)

        # ------------------------------------------------
        # 8) Stochastic 패널 (panel=4) + 윈도우 안 hit & 윈도우별 stoch_min 마커
        # ------------------------------------------------
        stoch_min_series = None
        try:
            stoch_full = compute_stoch(
                full_df["High"],
                full_df["Low"],
                full_df["Close"],
                k_period=14,
                d_period=3,
            )
            stoch_df = stoch_full.loc[plot_df.index]

            apds.append(
                mpf.make_addplot(
                    stoch_df["K"],
                    panel=4,
                    color="#FF33AA",
                    width=1.2,
                    ylabel="Stoch",
                )
            )
            apds.append(
                mpf.make_addplot(
                    stoch_df["D"],
                    panel=4,
                    color="#3333FF",
                    width=1.2,
                )
            )
            # Option A: 주요 기준선만 표시 (파라미터 기반)
            # 80선 (상단)
            line_80 = pd.Series(80.0, index=stoch_df.index)
            apds.append(
                mpf.make_addplot(
                    line_80,
                    panel=4,
                    color="#BBBBBB",
                    width=0.8,
                    linestyle="--",
                )
            )
            # stoch_threshold 기준선 (강조) - Option A
            line_stoch_threshold = pd.Series(stoch_threshold, index=stoch_df.index)
            apds.append(
                mpf.make_addplot(
                    line_stoch_threshold,
                    panel=4,
                    color="#FF0000",  # 빨간색으로 강조
                    width=1.5,         # 두껍게
                    linestyle="--",
                )
            )

            # ★ Stoch hit 마커 제거 - 차트가 너무 복잡해짐
            # stoch_mask = window_mask.reindex(stoch_df.index, fill_value=False)
            # stoch_hit = stoch_df["K"].where(
            #     (stoch_df["K"] <= stoch_threshold) & stoch_mask
            # )
            # apds.append(
            #     mpf.make_addplot(
            #         stoch_hit,
            #         panel=4,
            #         type="scatter",
            #         markersize=25,
            #         marker="o",
            #         color="#FF0088",  # 핫핑크 점 = Stoch hit
            #     )
            # )

            # ★ Stoch 다이아몬드 마커 제거 - 차트가 너무 복잡해짐
            # stoch_min_series = pd.Series(np.nan, index=stoch_df.index)
            # if window_ranges:
            #     for (s_i, e_i) in window_ranges:
            #         sub = stoch_df["K"].iloc[s_i : e_i + 1].dropna()
            #         if sub.empty:
            #             continue
            #         min_idx = sub.idxmin()
            #         stoch_min_series.loc[min_idx] = sub.min()
            # apds.append(
            #     mpf.make_addplot(
            #         stoch_min_series,
            #         panel=4,
            #         type="scatter",
            #         markersize=16,   # 기존 55 → 절반 정도
            #         marker="D",
            #         color="#FF0055",   # 더 진한 핫핑크 다이아 = 윈도우 stoch_min
            #     )
            # )

        except Exception as e:
            logger.warning("[WARN] compute_stoch failed: %s", e)


        # ------------------------------------------------
        # 9) 윈도우 요약값(rsi_min, stoch_min, macd_min) 계산 & CSV/로그 출력
        #    + rsi_min / macd_min 기준으로 후보 윈도우 식별
        #    + 후보 윈도우당 1개 "매수 시점" 계산 (macd_min 이후 반등 캔들)
        # ------------------------------------------------
        window_summaries: List[Dict] = []
        candidate_buy_points: List[Dict] = []  # 윈도우별 가상 매수 시점

        try:
            if window_ranges and (rsi is not None) and (macd_df is not None) and (stoch_df is not None):
                idx_list = list(plot_df.index)

                for win_idx, (s_i, e_i) in enumerate(window_ranges, start=1):
                    # 인덱스 범위 보정
                    s_i = max(0, min(s_i, len(idx_list) - 1))
                    e_i = max(0, min(e_i, len(idx_list) - 1))
                    if s_i > e_i:
                        continue

                    win_index = idx_list[s_i : e_i + 1]
                    win_start = win_index[0]
                    win_end = win_index[-1]

                    sub_rsi = rsi.loc[win_index].dropna() if rsi is not None else None
                    sub_macd = macd_df["MACD"].loc[win_index].dropna() if macd_df is not None else None
                    sub_stoch = stoch_df["K"].loc[win_index].dropna() if stoch_df is not None else None

                    if sub_rsi is None or sub_macd is None or sub_stoch is None:
                        continue
                    if sub_rsi.empty or sub_macd.empty or sub_stoch.empty:
                        continue

                    # --- 윈도우 요약값 ---
                    rsi_min_val = float(sub_rsi.min())
                    rsi_min_time = sub_rsi.idxmin()
                    macd_min_val = float(sub_macd.min())
                    macd_min_time = sub_macd.idxmin()
                    stoch_min_val = float(sub_stoch.min())
                    stoch_min_time = sub_stoch.idxmin()

                    # ★ 매수 후보 윈도우 판별
                    is_candidate = (
                        (rsi_min_val <= C_RSI_MIN_THRESHOLD)
                        and (macd_min_val <= C_MACD_MIN_THRESHOLD)
                    )
                    if is_candidate:
                        candidate_window_indices.add(win_idx)

                    # 요약값 저장
                    window_summaries.append(
                        dict(
                            window_index=win_idx,
                            start_time=win_start,
                            end_time=win_end,
                            rsi_min=rsi_min_val,
                            rsi_min_time=rsi_min_time,
                            stoch_min=stoch_min_val,
                            stoch_min_time=stoch_min_time,
                            macd_min=macd_min_val,
                            macd_min_time=macd_min_time,
                            is_candidate=is_candidate,
                        )
                    )

                    # ------------------------------------------------
                    # ★ 후보 윈도우라면 "가상 매수 시점" 계산
                    #   - 기준: macd_min_time 이후
                    #   - 조건: Close[t] > Close[t-1] AND MACD[t] > MACD[t-1]
                    #   - 없으면 macd_min_time 자체를 사용
                    # ------------------------------------------------
                    if is_candidate:
                        buy_time = macd_min_time

                        # macd_min_time 이 윈도우 인덱스 내에서 몇 번째인지 찾기
                        try:
                            pos_min = win_index.index(macd_min_time)
                        except ValueError:
                            pos_min = 0

                        # macd_min 이후 같은 윈도우 안에서 반등 캔들 탐색
                        found = False
                        for j in range(pos_min + 1, len(win_index)):
                            cur_t = win_index[j]
                            prev_t = win_index[j - 1]

                            # 안전 체크: 인덱스 존재 여부
                            if cur_t not in plot_df.index or prev_t not in plot_df.index:
                                continue
                            if cur_t not in macd_df.index or prev_t not in macd_df.index:
                                continue

                            close_cur = float(plot_df.loc[cur_t, "Close"])
                            close_prev = float(plot_df.loc[prev_t, "Close"])
                            macd_cur = float(macd_df.loc[cur_t, "MACD"])
                            macd_prev = float(macd_df.loc[prev_t, "MACD"])

                            # 가격 & MACD 동시 반등
                            if (close_cur > close_prev) and (macd_cur > macd_prev):
                                buy_time = cur_t
                                found = True
                                break

                        # buy_time 시점의 가격
                        if buy_time in plot_df.index:
                            buy_price = float(plot_df.loc[buy_time, "Close"])
                        else:
                            buy_price = float(sub_macd.index[0] in plot_df.index and plot_df.loc[sub_macd.index[0], "Close"] or plot_df["Close"].iloc[s_i])

                        candidate_buy_points.append(
                            dict(
                                window_index=win_idx,
                                buy_time=buy_time,
                                buy_price=buy_price,
                            )
                        )

            # --- CSV / 로그 출력 ---
            if window_summaries:
                summary_df = pd.DataFrame(window_summaries)

                # 저장 파일명: chart_...png -> windows_....csv
                base = os.path.basename(filename)
                dir_ = os.path.dirname(filename)
                if base.lower().endswith(".png"):
                    core = base[:-4]  # .png 제거
                else:
                    core = base
                if core.startswith("chart_"):
                    core = "windows_" + core[len("chart_") :]
                else:
                    core = "windows_" + core
                csv_name = core + ".csv"
                csv_path = os.path.join(dir_, csv_name)

                summary_df.to_csv(csv_path, index=False, encoding="utf-8-sig")

                logger.info("[BBI-V3] Window summary CSV saved: %s", csv_path)
                for row in window_summaries:
                    tag = "CAND" if row["is_candidate"] else "NORM"
                    logger.info(
                        "[BBI-V3][%s] Win%02d %s ~ %s | rsi_min=%.2f @ %s | stoch_min=%.2f @ %s | macd_min=%.0f @ %s",
                        tag,
                        row["window_index"],
                        row["start_time"],
                        row["end_time"],
                        row["rsi_min"],
                        row["rsi_min_time"],
                        row["stoch_min"],
                        row["stoch_min_time"],
                        row["macd_min"],
                        row["macd_min_time"],
                    )

            # --- 그래프용 "가상 매수 시점" 시리즈 생성 & addplot ---
            if candidate_buy_points:
                buy_series = pd.Series(np.nan, index=plot_df.index)
                for bp in candidate_buy_points:
                    t = bp["buy_time"]
                    p = bp["buy_price"]
                    if t in buy_series.index:
                        # 윈도우가 겹쳐도, 더 낮은 가격(더 좋은 진입)을 우선으로 남김
                        if np.isnan(buy_series.loc[t]) or p < buy_series.loc[t]:
                            buy_series.loc[t] = p

                apds.append(
                    mpf.make_addplot(
                        buy_series,
                        panel=0,
                        type="scatter",
                        markersize=70,
                        marker="^",
                        color="#00FF00",   # 밝은 초록색 화살표 = 후보 윈도우 가상 매수 시점
                        secondary_y=False,
                    )
                )

        except Exception as e:
            logger.warning("[WARN] window summary export / buy-point calc failed: %s", e)

        # ------------------------------------------------
        # 10) 볼린저 하단 돌파 spot(주황 원) 추가 (가격 패널)
        # ------------------------------------------------
        if lower_break_series is not None:
            try:
                apds.append(
                    mpf.make_addplot(
                        lower_break_series,
                        type="scatter",
                        markersize=40,
                        marker="o",
                        color="#FFA500",   # 주황색 동그라미 = 하단 돌파 spot
                        panel=0,
                        secondary_y=False,
                    )
                )
            except Exception as e:
                logger.warning("[WARN] lower_break spot addplot failed: %s", e)

        # ------------------------------------------------
        # 11) 실제 차트 그리기
        # ------------------------------------------------
        style = self._make_style(candle_up_color, candle_down_color)

        if fill_between_price is None:
            fb = dict(
                y1=plot_df["Low"].values,
                y2=plot_df["High"].values,
                alpha=0.02,
            )
        else:
            fb = fill_between_price

        fig, axlist = mpf.plot(
            plot_df,
            type="candle",
            volume=True,
            addplot=apds if apds else None,
            style=style,
            figratio=(16, 9),
            figscale=1.2,
            returnfig=True,
            panel_ratios=(4, 1, 1.5, 1.5, 1.5),
            fill_between=fb,
            warn_too_much_data=50000,
        )

        # ------------------------------------------------
        # 12) ★ 윈도우(10캔들) 구간을 배경 밴드로 표시 (Clean 버전)
        #     - 모든 윈도우: 연노랑 (매우 연하게, alpha=0.05)
        #     - 매수 후보 윈도우: 녹색으로 강조 (alpha=0.35)
        #       (rsi_min <= rsi_threshold & macd_min <= macd_threshold)
        # ------------------------------------------------
        if window_ranges:
            for win_idx, (start_i, end_i) in enumerate(window_ranges, start=1):
                for ax in axlist:
                    # 기본 윈도우 표시 (연노랑 - 매우 연하게)
                    if show_yellow_windows:
                        ax.axvspan(
                            start_i,
                            end_i + 1,        # 끝 캔들까지 포함
                            color="#FFFF00",   # 연노랑
                            alpha=0.05,        # 매우 연하게 (0.10 → 0.05)
                            zorder=0,
                        )
                    # 매수 후보 윈도우라면 녹색으로 강조
                    if win_idx in candidate_window_indices:
                        ax.axvspan(
                            start_i,
                            end_i + 1,
                            color="#00CC00",  # 녹색
                            alpha=0.35,       # 적당히 진하게 (0.50 → 0.35)
                            zorder=0,
                        )

        fig.savefig(filename, bbox_inches="tight")
        plt.close(fig)