import argparse
from argparse import RawTextHelpFormatter
import sys
import os
from typing import Optional, List, Dict

import pandas as pd

from .controller.simulator import Simulator
from .controller.controller import Controller
from .controller.mass_simulator import MassSimulator
from .log_manager import LogManager
from .__init__ import __version__
from .analyzer.custom_graph_generator import CandleGraphGenerator as GraphGenerator


# 텔레그램은 선택적으로 import
try:
    from .controller.telegram_controller import TelegramController
except ImportError:
    try:
        from .controller.telegram.telegram_controller import TelegramController
    except ImportError:
        TelegramController = None




def _build_df_from_simulator(sim) -> Optional[pd.DataFrame]:
    """
    smtm의 표준 구조(Analyzer -> DataRepository.info_list)를 그대로 이용해
    OHLCV DataFrame을 구성합니다.
    """
    op = getattr(sim, "operator", None)
    if op is None:
        return None
    analyzer = getattr(op, "analyzer", None)
    if analyzer is None:
        return None
    repo = getattr(analyzer, "data_repository", None)
    if repo is None:
        return None

    info_list = getattr(repo, "info_list", None)
    if not info_list:
        return None

    rows = []
    for item in info_list:
        try:
            if item.get("type") != "primary_candle":
                continue
            dt_str = item.get("date_time")
            if not dt_str:
                continue
            row = {
                "date_time": dt_str,
                "Open": float(item.get("opening_price")),
                "High": float(item.get("high_price")),
                "Low": float(item.get("low_price")),
                "Close": float(item.get("closing_price")),
                "Volume": float(item.get("acc_volume")),
            }
            rows.append(row)
        except Exception:
            continue

    if not rows:
        return None

    df = pd.DataFrame(rows)
    df["date_time"] = pd.to_datetime(df["date_time"], errors="coerce")
    df = df.dropna(subset=["date_time"]).set_index("date_time").sort_index()
    return df[["Open", "High", "Low", "Close", "Volume"]]


def _build_trades_from_simulator(sim) -> Optional[List[Dict]]:
    """
    Analyzer.DataRepository.result_list에서 매수/매도 체결 내역을 추출합니다.
    """
    op = getattr(sim, "operator", None)
    if op is None:
        return None
    analyzer = getattr(op, "analyzer", None)
    if analyzer is None:
        return None
    repo = getattr(analyzer, "data_repository", None)
    if repo is None:
        return None

    result_list = getattr(repo, "result_list", None)
    if not result_list:
        return None

    out: List[Dict] = []
    for r in result_list:
        try:
            dt_str = r.get("date_time")
            side = str(r.get("side") or r.get("type") or "").upper()
            price = r.get("price") or r.get("avg_price") or r.get("exec_price")
            if not dt_str or side not in ("BUY", "SELL") or price is None:
                continue
            out.append({
                "timestamp": dt_str,
                "side": side,
                "price": float(price),
            })
        except Exception:
            continue

    return out or None

#***********************************************************************************************

def _render_chart_if_possible(sim, args):
    """
    시뮬레이션이 끝난 뒤, 사용 가능한 OHLCV/트레이드 데이터를 자동으로 찾아
    커스텀 차트(캔들 + BB + 매수/매도 + RSI + MACD + Stoch)를 PNG로 저장.
    """
    term_seconds = int(round(args.term))
    if term_seconds < 60:
        term_seconds = 60

    # 1) 시뮬레이터에서 OHLCV DataFrame 구성
    df = _build_df_from_simulator(sim)
    if df is None or df.empty:
        print("[INFO] Chart skipped: could not auto-detect OHLCV data.")
        return

    # 2) 시뮬레이터에서 트레이드(매수/매도 로그) 추출
    trades = _build_trades_from_simulator(sim)

    # 3) 저장 폴더 준비
    os.makedirs("result", exist_ok=True)

    # 4) 실행 기간/전략/코인 기반으로 파일명 자동 생성
    #
    #   예) --from_dash_to 251011.000000-251012.000000
    #   -> start_tag = "251011", end_tag = "251012"
    #
    try:
        from_str, to_str = str(args.from_dash_to).split("-")
    except Exception:
        # 혹시라도 형식이 다르다면 안전하게 fallback
        from_str, to_str = "unknown_from", "unknown_to"

    def _short_tag(s: str) -> str:
        # "251011.000000" -> "251011"
        if "." in s:
            s = s.split(".")[0]
        return s.strip()

    start_tag = _short_tag(from_str)
    end_tag = _short_tag(to_str)

    currency = (getattr(args, "currency", "CUR") or "CUR").upper()
    strategy = (getattr(args, "strategy", "STR") or "STR").upper()

    # 최종 파일명 예:
    #   chart_BTC_SMA_251011_251012.png
    filename = f"chart_{currency}_{strategy}_{start_tag}_{end_tag}.png"
    out_path = os.path.join("result", filename)

    # 5) 그래프 생성기 호출 (현재 프로젝트에서 사용 중인 GraphGenerator 그대로 사용)
    gg = GraphGenerator(currency=args.currency, term_seconds=term_seconds)

    try:
        gg.create_candle_chart(
            df=df,
            trades=trades,                       # 거래 로그 없으면 None 가능
            filename=out_path,
            show_bbands=bool(args.bb),
            bb_window=int(args.bb_window),
            bb_k=float(args.bb_k),
            buy_color=args.buy_color or "#A020F0",
            sell_color=args.sell_color or "#FF0000",
            candle_up_color=(args.candle_up or None),
            candle_down_color=(args.candle_down or None),
            prefer_close_for_markers=True,
        )
        print(f"[OK] Chart saved: {out_path}")
    except Exception as e:
        print(f"[WARN] Chart rendering failed: {e}")


#*****************************************************************************************************

if __name__ == "__main__":
    DEFAULT_MODE = 6

    parser = argparse.ArgumentParser(
        description="""
smtm - Algorithm-based Crypto Trading System

mode:
    0: Simulation with interative mode
    1: Single simulation
    2: Interactive mode Real trading system
    3: Telegram chatbot trading system
    4: Mass simulation
    5: Making config files for mass simulation
""",
        formatter_class=RawTextHelpFormatter,
    )

    # 공통
    parser.add_argument("--mode", type=int, default=DEFAULT_MODE,
                        help="0: interactive sim, 1: single sim, 2: real, 3: telegram, 4: mass, 5: make mass config")
    parser.add_argument("--budget", type=int, default=10000, help="budget (KRW)")
    parser.add_argument("--term", type=float, default=60.0, help="trading tick interval (seconds, >=60)")
    parser.add_argument("--strategy", default="BNH", help="BNH|SMA|RSI|SAS|HEY|...")
    parser.add_argument("--trader", default="0", help="trader 0: Upbit, 1: Bithumb")
    parser.add_argument("--currency", default="BTC", help="trading currency e.g. BTC")
    parser.add_argument("--log", default=None, help="log file name")
    parser.add_argument("--from_dash_to",
                        default="201220.170000-201220.180000",
                        help="simulation period ex) 201220.170000-201220.180000")

    # 텔레그램
    parser.add_argument("--demo", type=int, default=0, help="use demo trader (0|1)")
    parser.add_argument("--token", default=None, help="telegram chat-bot token")
    parser.add_argument("--chatid", default=None, help="telegram chat id")

    # 대량 시뮬레이션
    parser.add_argument("--config", default="", help="mass simulation config file")
    parser.add_argument("--process", type=int, default=-1,
                        help="process count for mass simulation. -1 to use cpu count")
    parser.add_argument("--title", default="SMA_2H_week", help="mass simulation title")
    parser.add_argument("--file", default=None, help="generated config file name")
    parser.add_argument("--offset", type=int, default=120, help="mass simulation period offset (minutes)")

    # 그래프 옵션
    parser.add_argument("--bb", type=int, default=1, help="볼린저밴드 표시(1/0)")
    parser.add_argument("--bb_window", type=int, default=20)
    parser.add_argument("--bb_k", type=float, default=2.0)
    parser.add_argument("--buy_color", type=str, default="#A020F0")   # 보라
    parser.add_argument("--sell_color", type=str, default="#FF0000")  # 빨강
    parser.add_argument("--candle_up", type=str, default="")
    parser.add_argument("--candle_down", type=str, default="")

    parser.add_argument("--version", action="version", version=f"smtm version: {__version__}")

    args = parser.parse_args()

    if args.log is not None:
        LogManager.change_log_file(args.log)

    if args.term < 60:
        print("[ERROR] --term 는 최소 60(1분봉) 이상이어야 합니다. 예: 60, 300, 900, 3600")
        sys.exit(1)

    if args.mode == DEFAULT_MODE:
        parser.print_help()
        sys.exit(0)

    if args.mode in (0, 1):
        simulator = Simulator(
            budget=args.budget,
            interval=args.term,
            strategy=args.strategy,
            currency=args.currency,
            from_dash_to=args.from_dash_to,
        )

        if args.mode == 0:
            simulator.main()
        else:
            simulator.run_single()
            _render_chart_if_possible(simulator, args)

    elif args.mode == 2:
        controller = Controller(
            budget=args.budget,
            interval=args.term,
            strategy=args.strategy,
            currency=args.currency,
            is_bithumb=(args.trader == "1"),
        )
        controller.main()

    elif args.mode == 3:
        if TelegramController is None:
            print("[ERROR] Telegram controller module not found.")
            sys.exit(1)
        try:
            tcb = TelegramController(token=args.token, chat_id=args.chatid)
        except Exception:
            print("Please check your telegram chat-bot token")
            sys.exit(1)
        tcb.main(demo=(args.demo == 1))

    elif args.mode == 4:
        if args.config == "":
            parser.print_help()
            sys.exit(1)
        mass = MassSimulator()
        mass.run(args.config, args.process)

    elif args.mode == 5:
        result = MassSimulator.make_config_json(
            title=args.title,
            budget=args.budget,
            strategy_code=args.strategy,
            currency=args.currency,
            from_dash_to=args.from_dash_to,
            offset_min=args.offset,
            filepath=args.file,
        )
        print(f"{result} is generated")
