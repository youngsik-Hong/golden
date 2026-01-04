"""
Analyzer용 GraphGenerator

- Analyzer.analyzer.Analyzer 에서 사용합니다.
- info_list 의 primary_candle 들을 모아서 OHLCV DataFrame 을 만든 뒤
  custom_graph_generator.CandleGraphGenerator 를 사용해
  캔들 + 보조지표 그래프를 저장합니다.

Patch-1
  - 하루 단위(target_date) + 워밍업(pre days) 구조

Patch-2
  - 1분봉 캔들을 10개씩 묶어서 "10틱 캔들"로 재구성하여 시각화에 사용

Patch-3 (이번 보완)
  - candle 파싱을 안전하게(Volume 키 다양성 대응)
  - 러너가 기대하는 산출물 경로/파일명(result/chart_..., result/windows_...)도 함께 생성
    → multi_backtest_runner의 CLI fallback 방지(→ WinError 32 로그 충돌도 크게 감소)
"""

import os
import re
from typing import List, Dict, Any, Optional, Tuple

import numpy as np
import pandas as pd

from ..log_manager import LogManager
from .custom_graph_generator import CandleGraphGenerator


class GraphGenerator:
    # Analyzer 기본 출력 (기존 호환)
    OUTPUT_FOLDER = "output/"
    # Runner 산출물 폴더(러너가 이쪽을 찾는 것으로 보임)
    RESULT_FOLDER = "result/"

    GRAPH_MAX_COUNT = 1440
    RSI_ENABLE = False
    RSI = (30, 70, 14)

    PRE_DAYS_FOR_INDICATORS = 5
    CANDLE_AGG_NUM = 10  # 1분봉 N개 묶음(기본 10)

    def __init__(self, sma_info: Tuple[int, int, int] = (10, 40, 120)):
        self.logger = LogManager.get_logger("GraphGenerator")
        self.sma_info = sma_info

    def draw_graph(
        self,
        info_list: List[Dict[str, Any]],
        result_list: List[Dict[str, Any]],
        score_list: List[Dict[str, Any]],
        filename: str,
        is_fullpath: bool = False,
        spot_list: Optional[List[Dict[str, Any]]] = None,
        line_graph_list: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """
        Analyzer.create_report 에서 호출.

        - info_list에서 1분봉 OHLCV 생성 → 10틱 캔들로 집계
        - output/<filename>.png 저장 (기존 방식)
        - 추가로 result/chart_...png 및 result/windows_...csv 생성 (러너 fallback 방지)
        """
        # (현재는 score_list/spot_list/line_graph_list는 그래프 생성에 직접 사용하지 않음)
        del score_list, spot_list, line_graph_list

        try:
            df_1m = self._build_df_1m_from_info(info_list)
            if df_1m is None or df_1m.empty:
                self.logger.warning("GraphGenerator.draw_graph: no candle data, skip")
                return filename

            # 10틱(10분) 캔들로 집계(시각화용)
            df = self._aggregate_candles(df_1m, self.CANDLE_AGG_NUM)

            # --- 표시 대상 날짜(D) 결정 ---
            last_ts = df.index.max()
            if not isinstance(last_ts, pd.Timestamp):
                last_ts = pd.to_datetime(last_ts, errors="coerce")
            if pd.isna(last_ts):
                self.logger.warning("GraphGenerator.draw_graph: invalid last timestamp, skip")
                return filename

            target_date = last_ts.normalize()
            day_start = target_date
            day_end = target_date + pd.Timedelta(days=1)

            # --- 워밍업 포함 슬라이스 ---
            hist_start = day_start - pd.Timedelta(days=self.PRE_DAYS_FOR_INDICATORS)
            sliced = df.loc[hist_start:day_end]
            if sliced.empty:
                sliced = df.sort_index()

            # --- output 저장 경로 ---
            if is_fullpath:
                out_path = filename
                if not out_path.lower().endswith(".png"):
                    out_path += ".png"
                out_dir = os.path.dirname(out_path) or "."
                os.makedirs(out_dir, exist_ok=True)
            else:
                os.makedirs(self.OUTPUT_FOLDER, exist_ok=True)
                out_path = os.path.join(self.OUTPUT_FOLDER, f"{filename}.png")

            # 캔들 + 보조지표 그래프 생성
            # term_seconds는 기존처럼 60 고정(부작용 최소화). 캔들은 이미 집계된 df를 사용.
            currency = self._infer_currency(filename, result_list) or "BTC"
            gg = CandleGraphGenerator(currency=currency, term_seconds=60)

            trade_list = self._build_trades_from_result_list(result_list)

            gg.create_candle_chart(
                df=sliced,
                filename=out_path,
                trades=trade_list,
                show_bbands=True,
                bb_window=20,
                bb_k=2.0,
                buy_color="#A020F0",
                sell_color="#FF0000",
                candle_up_color=None,
                candle_down_color=None,
                prefer_close_for_markers=True,
                target_date=target_date,
            )

            self.logger.info(f"GraphGenerator.draw_graph: graph saved to {out_path}")

            # =========================================================
            # (중요) Runner 산출물도 함께 생성: result/chart_..., result/windows_...
            #   - 러너가 artifacts missing 으로 CLI fallback 돌리는 걸 방지
            # =========================================================
            self._emit_runner_artifacts(filename=filename, currency=currency, df_1m=df_1m, chart_src_path=out_path)

            return out_path

        except Exception as e:
            self.logger.error(f"GraphGenerator.draw_graph failed: {e}", exc_info=True)
            return filename

    # ======================================================================
    # Runner artifacts
    # ======================================================================
    def _emit_runner_artifacts(self, filename: str, currency: str, df_1m: pd.DataFrame, chart_src_path: str) -> None:
        """
        filename이 SIM-... 형태일 때, 러너가 찾는 산출물 이름으로 결과를 추가 생성한다.

        기대 포맷(관측된 CLI 산출물):
          result/chart_{TICKER}_{STRATEGY}_{YYMMDD}_{YYMMDD}.png
          result/windows_{TICKER}_{STRATEGY}_{YYMMDD}_{YYMMDD}.csv

        filename 예:
          SIM-BBI-V3-SPEC-V16-VOL-250203.000000-250204.000000
        """
        try:
            parsed = self._parse_sim_filename(filename)
            if not parsed:
                return

            strategy_slug, from_ymd, to_ymd = parsed
            tkr = self._normalize_ticker(currency)

            os.makedirs(self.RESULT_FOLDER, exist_ok=True)

            # chart target
            chart_name = f"chart_{tkr}_{strategy_slug}_{from_ymd}_{to_ymd}.png"
            chart_dst_path = os.path.join(self.RESULT_FOLDER, chart_name)

            # windows csv target
            win_name = f"windows_{tkr}_{strategy_slug}_{from_ymd}_{to_ymd}.csv"
            win_dst_path = os.path.join(self.RESULT_FOLDER, win_name)

            # 1) 차트 파일 복사(이미 저장된 output png를 result로)
            #    (copy2: 메타데이터 포함)
            try:
                import shutil
                if os.path.exists(chart_src_path) and not os.path.exists(chart_dst_path):
                    shutil.copy2(chart_src_path, chart_dst_path)
            except Exception:
                # 복사 실패해도 CSV는 만들 수 있으니 계속 진행
                pass

            # 2) windows CSV 생성 (1분봉 기반으로 export)
            if df_1m is not None and not df_1m.empty:
                # 러너에서 생성한 CSV 컬럼과 완전 동일하진 않아도, 최소한 시간/ohlcv는 들어가게
                out_df = df_1m.copy().sort_index()
                out_df = out_df.reset_index().rename(columns={"date_time": "DateTime"})
                # DateTime 컬럼명 통일
                if "date_time" in out_df.columns:
                    out_df = out_df.rename(columns={"date_time": "DateTime"})
                elif "index" in out_df.columns:
                    out_df = out_df.rename(columns={"index": "DateTime"})

                if not os.path.exists(win_dst_path):
                    out_df.to_csv(win_dst_path, index=False, encoding="utf-8-sig")

        except Exception:
            # 러너 산출물은 best-effort
            return

    @staticmethod
    def _normalize_ticker(currency: str) -> str:
        # "KRW-BTC" 같은 형태면 BTC만 사용
        if not currency:
            return "BTC"
        c = currency.upper()
        if "-" in c:
            c = c.split("-")[-1]
        return c

    @staticmethod
    def _parse_sim_filename(filename: str) -> Optional[Tuple[str, str, str]]:
        """
        SIM-<STRATEGY>-<FROM>.<...>-<TO>.<...> 에서
        strategy_slug, from_ymd, to_ymd를 추출해 반환.

        반환 예:
          ("BBI-V3-SPEC-V16-VOL", "250203", "250204")
        """
        if not filename:
            return None

        # 확장자 제거
        base = os.path.basename(filename)
        base = re.sub(r"\.png$", "", base, flags=re.I)

        if not base.startswith("SIM-"):
            return None

        # SIM-BBI-V3-SPEC-V16-VOL-250203.000000-250204.000000
        m = re.match(r"^SIM-(.+)-(\d{6})\.\d+-(\d{6})\.\d+$", base)
        if not m:
            return None

        strategy_slug = m.group(1)
        from_ymd = m.group(2)
        to_ymd = m.group(3)
        return strategy_slug, from_ymd, to_ymd

    # ======================================================================
    # Candle building
    # ======================================================================
    @staticmethod
    def _to_float(v: Any) -> Optional[float]:
        if v is None:
            return None
        try:
            if isinstance(v, bool):
                return None
            if isinstance(v, str) and v.strip() == "":
                return None
            return float(v)
        except Exception:
            return None

    @staticmethod
    def _pick_first(d: Dict[str, Any], keys: List[str]) -> Any:
        for k in keys:
            if k in d and d.get(k) is not None:
                return d.get(k)
        return None

    @staticmethod
    def _extract_primary_candle(info: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        info 항목에서 candle dict를 최대한 추출.
        지원:
          1) {"primary_candle": {...}}
          2) {"items":[{"type":"primary_candle", ...}, ...]}
          3) info 자체가 candle dict
        """
        if not isinstance(info, dict):
            return None

        if isinstance(info.get("primary_candle"), dict):
            return info["primary_candle"]

        items = info.get("items")
        if isinstance(items, list):
            for it in items:
                if isinstance(it, dict) and it.get("type") == "primary_candle":
                    return it

        # 평탄화 케이스
        if "date_time" in info and (
            "opening_price" in info or "Open" in info or "open" in info
        ):
            return info

        return None

    def _build_df_1m_from_info(self, info_list: List[Dict[str, Any]]) -> Optional[pd.DataFrame]:
        """
        info_list에서 1분봉 OHLCV를 안전하게 구성한다.
        (기존의 float(item.get("acc_volume")) 고정 때문에 rows가 전부 스킵되는 문제 방지)
        """
        if not info_list:
            return None

        rows: List[Dict[str, Any]] = []
        for info in info_list:
            candle = None
            try:
                candle = self._extract_primary_candle(info)
                if not candle or not isinstance(candle, dict):
                    continue

                dt_str = self._pick_first(candle, ["date_time", "timestamp", "time"])
                if not dt_str:
                    continue

                o = self._to_float(self._pick_first(candle, ["opening_price", "open", "Open"]))
                h = self._to_float(self._pick_first(candle, ["high_price", "high", "High"]))
                l = self._to_float(self._pick_first(candle, ["low_price", "low", "Low"]))
                c = self._to_float(self._pick_first(candle, ["closing_price", "close", "Close"]))

                # volume 후보들(환경별로 다름)
                v = self._to_float(
                    self._pick_first(
                        candle,
                        [
                            "acc_volume",
                            "volume",
                            "acc_trade_volume",
                            "candle_acc_trade_volume",
                            "trade_volume",
                            "Volume",
                        ],
                    )
                )

                if o is None or h is None or l is None or c is None:
                    continue
                if v is None:
                    v = 0.0

                rows.append(
                    {
                        "date_time": dt_str,
                        "Open": o,
                        "High": h,
                        "Low": l,
                        "Close": c,
                        "Volume": v,
                    }
                )
            except Exception:
                continue

        if not rows:
            return None

        df = pd.DataFrame(rows)
        df["date_time"] = pd.to_datetime(df["date_time"], errors="coerce")
        df = df.dropna(subset=["date_time"]).set_index("date_time").sort_index()
        df = df[["Open", "High", "Low", "Close", "Volume"]]
        return df

    @staticmethod
    def _aggregate_candles(df: pd.DataFrame, n: int = 10) -> pd.DataFrame:
        """
        1분봉 DataFrame을 n개씩 묶어 새로운 캔들로 만든다.
        시간 리샘플이 아니라 '행 순서 기반' 그룹이라
        1분 캔들이 비는 케이스가 있어도 안정적으로 동작.
        """
        if df is None or df.empty:
            return df
        if n <= 1:
            return df

        values = df.sort_index().copy()
        length = len(values)
        if length == 0:
            return values

        group_idx = np.arange(length) // int(n)
        grouped = values.groupby(group_idx)

        agg = grouped.agg(
            {
                "Open": "first",
                "High": "max",
                "Low": "min",
                "Close": "last",
                "Volume": "sum",
            }
        )

        last_index = grouped.apply(lambda g: g.index[-1])
        agg.index = last_index.values
        return agg

    # ======================================================================
    # Trades / Currency
    # ======================================================================
    @staticmethod
    def _build_trades_from_result_list(
        result_list: List[Dict[str, Any]]
    ) -> Optional[List[Dict[str, Any]]]:
        if not result_list:
            return None

        trades: List[Dict[str, Any]] = []
        for r in result_list:
            try:
                dt_str = r.get("date_time")
                side = str(r.get("side") or r.get("type") or "").upper()
                price = r.get("price") or r.get("avg_price") or r.get("exec_price")

                if not dt_str or price is None:
                    continue
                if side not in ("BUY", "SELL"):
                    continue

                trades.append({"timestamp": dt_str, "side": side, "price": float(price)})
            except Exception:
                continue

        return trades or None

    def _infer_currency(self, filename: str, result_list: List[Dict[str, Any]]) -> Optional[str]:
        # 1) result_list에서 시장/티커 흔적이 있으면 우선 사용
        try:
            for r in (result_list or [])[:20]:
                if not isinstance(r, dict):
                    continue
                for k in ("market", "ticker", "symbol", "currency"):
                    v = r.get(k)
                    if isinstance(v, str) and v:
                        return v.replace("KRW-", "").upper()
        except Exception:
            pass

        # 2) filename에서 추정 (chart_BTC..., windows_BTC..., SIM-...는 보통 currency 인자 따로)
        try:
            base = os.path.basename(filename).upper()
            # chart_BTC_... / windows_BTC_...
            m = re.match(r"^(?:CHART|WINDOWS)_([A-Z0-9\-]+)_", base)
            if m:
                return m.group(1).replace("KRW-", "").upper()

            # 대표 티커만 빠르게 탐색
            for t in ("BTC", "ETH", "XRP", "SOL", "ADA", "DOGE", "DOT", "AVAX", "TRX", "LINK", "BNB"):
                if t in base:
                    return t
        except Exception:
            pass

        return None
