import time
from datetime import datetime

from .log_manager import LogManager
from .operator import Operator
from typing import Any, Dict, Optional


class SimulationOperator(Operator):
    PERIODIC_RECORD_INFO = (360, -1)
    PERIODIC_RECORD_INTERVAL_TURN = 300

    def __init__(self, periodic_record_enable=False):
        super().__init__()
        self.logger = LogManager.get_logger(__class__.__name__)
        self.turn = 0
        self.budget = 0
        self.current_turn = 0
        self.last_periodic_turn = 0
        self.periodic_record_enable = periodic_record_enable
        self.last_report = None

    def _execute_trading(self, task):
        del task
        self.logger.info(
            f"############# Simulation trading START (turn={self.turn + 1})"
        )
        self.is_timer_running = False

        try:
            self.current_turn += 1

            # ==========================================================
            # 1) 시세 데이터 가져오기
            # ==========================================================
            trading_info = self.data_provider.get_info()

            if trading_info is None:
                if self.current_turn <= 1:
                    self.logger.warning(
                        "[WARN] get_info() returned None on first turn. Retrying..."
                    )
                    self.turn += 1
                    self._start_timer()
                    return

                self.logger.warning(
                    f"[WARN] get_info() returned None at turn={self.current_turn}. "
                    "No more data → simulation end."
                )
                try:
                    self.last_report = self.analyzer.create_report(tag=self.tag)
                except Exception as err:
                    self.logger.error(f"failed to create final report: {err}")
                    self.last_report = None

                self.state = "simulation_terminated"
                self.logger.info("Simulation terminated normally (no more data).")
                return

            # ==========================================================
            # ★ signal_time 추출 (전략이 보는 캔들 시각)
            # ==========================================================
            signal_dt = None
            try:
                if isinstance(trading_info, list):
                    for item in trading_info:
                        if isinstance(item, dict) and item.get("type") == "primary_candle":
                            signal_dt = item.get("date_time")
                            break
            except Exception:
                signal_dt = None

            # ==========================================================
            # 2) 전략/분석기에 시세 전달
            # ==========================================================
            self.strategy.update_trading_info(trading_info)
            self.analyzer.put_trading_info(trading_info)

            def send_request_callback(result):
                if result in ("pass", "error!"):
                    return

                if isinstance(result, dict) and result.get("msg") == "game-over":
                    last_info = self.data_provider.get_info()
                    if last_info is not None:
                        self.analyzer.put_trading_info(last_info)

                    try:
                        self.last_report = self.analyzer.create_report(tag=self.tag)
                    except Exception as err:
                        self.logger.error(
                            f"failed to create final report at game-over: {err}"
                        )
                        self.last_report = None

                    self.state = "simulation_terminated"
                    self.logger.info("Simulation terminated by 'game-over' message.")
                    return

                self.strategy.update_result(result)
                self.analyzer.put_result(result)

            # ==========================================================
            # 3) 전략에서 주문 요청 받아 트레이더로 전달
            # ==========================================================
            target_request = self.strategy.get_request()

            order_dt = None

            if target_request is None:
                self.logger.info(
                    "No trading request at turn %s",
                    self.turn + 1,
                )
            else:
                if isinstance(target_request, dict):
                    request_list = [target_request]
                elif isinstance(target_request, list):
                    request_list = target_request
                else:
                    self.logger.error(
                        "Invalid target_request type %s",
                        type(target_request),
                    )
                    request_list = None

                if request_list:
                    try:
                        order_dt = request_list[-1].get("date_time")
                    except Exception:
                        order_dt = None

                    # ★ 정합성 증거 로그
                    self.logger.info(
                        f"[SYNC] turn={self.turn + 1} "
                        f"signal_dt={signal_dt} order_dt={order_dt}"
                    )

                    self.trader.send_request(request_list, send_request_callback)
                    self.analyzer.put_requests(request_list)

            # ==========================================================
            # 4) 주기적 기록
            # ==========================================================
            if self.periodic_record_enable:
                self._periodic_internal_get_score()

        except Exception as err:
            self.logger.error(f"executing fail: {err}", exc_info=True)

        self.turn += 1
        self._start_timer()

    # 이하 기존 코드 동일

    def get_score(self, callback, index_info=None, graph_tag=None):
        """
        현재 수익률을 인자로 전달받은 콜백함수를 통해 전달한다
        Pass the current yield to the callback function passed as an argument

        index_info: 수익률 구간 정보
            (
                interval: 구간의 길이로 turn의 갯수 예) 180: interval이 60인 경우 180분
                index: 구간의 인덱스 예) -1: 최근 180분, 0: 첫 180분
            )
        """
        if self.state != "running":
            self.logger.debug("already terminated return last report")
            if self.last_report is not None:
                callback(self.last_report["summary"])
            else:
                callback(None)
            return

        def get_score_callback(task):
            now = datetime.now()
            if graph_tag is not None:
                graph_filename = (
                    f"{self.OUTPUT_FOLDER}gs{round(time.time())}-{graph_tag}.jpg"
                )
            else:
                dt = now.strftime("%m%dT%H%M")
                graph_filename = f"{self.OUTPUT_FOLDER}gs{round(time.time())}-{dt}.jpg"

            try:
                idx_info = task["index_info"]
                task["callback"](
                    self.analyzer.get_return_report(
                        graph_filename=graph_filename, index_info=idx_info
                    )
                )
            except TypeError as err:
                self.logger.error(f"invalid callback: {err}", exc_info=True)

        self.worker.post_task(
            {
                "runnable": get_score_callback,
                "callback": callback,
                "index_info": index_info,
            }
        )

    def _periodic_internal_get_score(self):
        if (
            self.current_turn - self.last_periodic_turn
            < self.PERIODIC_RECORD_INTERVAL_TURN
        ):
            return

        def internal_get_score_callback(score):
            # score[4] = 그래프 파일 경로
            if score is not None:
                self.logger.info(f"save score graph to {score[4]}")

        self.get_score(
            internal_get_score_callback,
            index_info=self.PERIODIC_RECORD_INFO,
            graph_tag=f"P{self.current_turn:06d}",
        )
        self.last_periodic_turn = self.current_turn


import importlib
import inspect
from typing import Tuple, Optional, Type

def _try_import_strategy(module_name: str, class_name: str):
    try:
        mod = importlib.import_module(module_name)
        cls = getattr(mod, class_name, None)
        if cls is None:
            return None
        if inspect.isabstract(cls):
            return None
        return cls
    except Exception:
        return None

def _resolve_strategy_class(strategy_code: str):
    """
    STRATEGY_CODE에 맞는 '구체 Strategy 클래스'를 찾는다.
    - 여기 후보 리스트는 정석적으로 '명시적'이어야 한다(자동 전체 스캔은 부작용 가능).
    - 프로젝트에 실제 존재하는 전략 클래스명에 맞춰 하나만 성공하면 OK.
    """
    candidates = [
        # ✅ (가장 우선) BBI V16 VOL 전용 전략이 있다면 여기에 정확히 넣으세요.
        ("smtm.strategy.strategy_bbi_v16_vol", "StrategyBbiV16Vol"),
        ("smtm.strategy.strategy_bbi_v3_v16_vol", "StrategyBbiV3V16Vol"),
        ("smtm.strategy.bbi_v16_vol", "BbiV16VolStrategy"),
        # ✅ fallback 예시 (실제 존재하면 동작)
        ("smtm.strategy.strategy_sma_0", "StrategySma0"),
    ]

    for mod, cls_name in candidates:
        cls = _try_import_strategy(mod, cls_name)
        if cls is not None:
            return cls, (mod, cls_name)

    raise RuntimeError(
        f"STRATEGY_CODE={strategy_code} 에 해당하는 구체 Strategy 클래스를 찾지 못했습니다.\n"
        f"simulation_operator.py의 candidates 목록에 '실제 존재하는 전략 모듈/클래스'를 1개 추가하세요."
    )

# --- PATCH: Step 3-B' entrypoint for UI backtest runner -----------------
from datetime import datetime
from typing import Any, Dict, Optional

def _tf_to_term_seconds(tf: str) -> int:
    tf = (tf or "").strip().lower()
    m = {
        "1m": 60,
        "3m": 180,
        "5m": 300,
        "15m": 900,
        "1h": 3600,
        "60m": 3600,
    }
    if tf in m:
        return m[tf]
    if tf.endswith("m") and tf[:-1].isdigit():
        return int(tf[:-1]) * 60
    if tf.endswith("h") and tf[:-1].isdigit():
        return int(tf[:-1]) * 3600
    return 60

def _yyyy_mm_dd_to_dash_tag(s: str) -> str:
    # "2025-12-18" -> "251218.000000"
    dt = datetime.strptime(s, "%Y-%m-%d")
    return dt.strftime("%y%m%d") + ".000000"

def run_single_backtest(
    ticker: str,
    start: str,     # "YYYY-MM-DD"
    end: str,       # "YYYY-MM-DD"
    tf: str,        # "1m", "3m", ...
    budget: int,
    tuning_params: Optional[Dict[str, Any]] = None,
    data_path: Optional[str] = None,
) -> Dict[str, Any]:
    """
    UI Step2-C/Step3-B'가 호출하는 '단일 백테스트' 엔트리포인트.
    - 기존 Simulator를 그대로 사용해서 프로젝트 구조를 보존
    """
    term_seconds = _tf_to_term_seconds(tf)
    from_dash_to = f"{_yyyy_mm_dd_to_dash_tag(start)}-{_yyyy_mm_dd_to_dash_tag(end)}"

    # tuning_params에서 STRATEGY_CODE를 우선 사용
    strategy_code = None
    if isinstance(tuning_params, dict):
        strategy_code = tuning_params.get("STRATEGY_CODE") or tuning_params.get("strategy_code")
    if not strategy_code:
        strategy_code = "BBI-V3-SPEC-V16-VOL"

    from smtm.controller.simulator import Simulator

    sim = Simulator(
        budget=int(budget),
        interval=float(term_seconds),
        strategy=str(strategy_code),
        currency=str(ticker).upper(),
        from_dash_to=from_dash_to,
    )

    sim.run_single()

    # 결과 추출(있으면)
    report = getattr(getattr(sim, "operator", None), "last_report", None) or {}
    summary = None
    try:
        summary = report.get("summary", None) if isinstance(report, dict) else None
    except Exception:
        summary = None

    roi = 0.0
    min_return = 0.0
    max_return = 0.0
    trades = 0

    # summary tuple 형태 대응
    try:
        if isinstance(summary, (list, tuple)) and len(summary) >= 8:
            roi = float(summary[2])
            min_return = float(summary[6])
            max_return = float(summary[7])
    except Exception:
        pass

    # 체결 수 대략
    try:
        repo = getattr(getattr(getattr(sim, "operator", None), "analyzer", None), "data_repository", None)
        result_list = getattr(repo, "result_list", None) or []
        trades = int(len(result_list))
    except Exception:
        trades = 0

    return {
        "roi": roi,
        "profit_rate": roi,
        "min_return": min_return,
        "max_return": max_return,
        "trades": trades,
        "report": report,
    }
# --- END PATCH ----------------------------------------------------------
