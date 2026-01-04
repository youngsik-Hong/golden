from ..config import Config
from ..log_manager import LogManager
from .trader import Trader
from .virtual_market import VirtualMarket
import os

from ..data.upbit_markets import krw_market_map


class SimulationTrader(Trader):
    """
    시뮬레이션용 가상 트레이더
    """

    AVAILABLE_CURRENCY = {
        "binance": {
            "BTC": "BTCUSDT",
            "ETH": "ETHUSDT",
            "DOGE": "DOGEUSDT",
            "XRP": "XRPUSDT",
        },
    }
    NAME = "Simulation"

    def __init__(self, currency="BTC", interval=60):
        if Config.simulation_source not in ("upbit", "binance"):
            raise UserWarning(f"not supported source: {Config.simulation_source}")

        self.logger = LogManager.get_logger(__class__.__name__)

        # upbit: KRW 전체 코인을 자동 매핑
        if Config.simulation_source == "upbit":
            market_map = krw_market_map(force_refresh=False)

            if isinstance(currency, str) and currency.upper().startswith("KRW-"):
                market = currency.upper()
            else:
                c = str(currency).upper()
                if c not in market_map:
                    raise UserWarning(f"not supported currency (upbit KRW market not found): {c}")
                market = market_map[c]
        else:
            c = str(currency).upper()
            if c not in self.AVAILABLE_CURRENCY["binance"]:
                raise UserWarning(f"not supported currency: {c}")
            market = self.AVAILABLE_CURRENCY["binance"][c]

        # ✅ 추가 옵션(상세 로그)은 기본 OFF
        #    실주문/디버그 상황에서만 환경변수로 켜세요.
        sim_verbose = os.getenv("SMTM_SIM_VERBOSE", "0") in ("1", "true", "True", "YES", "yes")

        self.v_market = VirtualMarket(
            market=market,
            interval=interval,
            verbose=sim_verbose,
            log_noop=sim_verbose,
        )
        self.is_initialized = False

    def initialize_simulation(self, end, count, budget):
        self.v_market.initialize(end, count, budget)
        self.is_initialized = True

    def send_request(self, request_list, callback):
        if self.is_initialized is not True:
            raise UserWarning("Not initialzed")

        try:
            result = self.v_market.handle_request(request_list[0])
            if result is not None:
                callback(result)
        except (TypeError, AttributeError) as msg:
            self.logger.error(f"invalid state {msg}")
            raise UserWarning("invalid state") from msg

    def get_account_info(self):
        if self.is_initialized is not True:
            raise UserWarning("Not initialzed")

        try:
            return self.v_market.get_balance()
        except (TypeError, AttributeError) as msg:
            self.logger.error(f"invalid state {msg}")
            raise UserWarning("invalid state") from msg

    def cancel_request(self, request):
        """
        시뮬레이션에서는 실거래 주문취소 개념이 없거나 단순화될 수 있습니다.
        VirtualMarket이 취소를 지원하면 거기로 위임하고,
        없으면 no-op 처리합니다.
        """
        if getattr(self, "v_market", None) is None:
            return None

        if hasattr(self.v_market, "cancel_request"):
            try:
                return self.v_market.cancel_request(request)
            except Exception:
                return None

        return None

    def cancel_all_requests(self):
        """
        시뮬레이션에서는 대기 주문 전체 취소.
        VirtualMarket이 지원하면 위임, 아니면 no-op 처리.
        """
        if getattr(self, "v_market", None) is None:
            return None

        if hasattr(self.v_market, "cancel_all_requests"):
            try:
                return self.v_market.cancel_all_requests()
            except Exception:
                return None

        return None
