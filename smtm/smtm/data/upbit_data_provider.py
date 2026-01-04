import requests

from .data_provider import DataProvider
from ..log_manager import LogManager
from .upbit_markets import krw_market_map


class UpbitDataProvider(DataProvider):
    """
    업비트 거래소의 실시간 거래 데이터를 제공하는 클래스

    Upbit OPEN API 사용 (인증/토큰 불필요)
    https://docs.upbit.com/reference#시세-캔들-조회
    """

    NAME = "UPBIT DP"
    CODE = "UPB"

    def __init__(self, currency: str = "BTC", interval: int = 60, force_refresh: bool = False):
        self.logger = LogManager.get_logger(__class__.__name__)

        # ✅ 업비트 KRW 전체 코인 자동 매핑
        market_map = krw_market_map(force_refresh=force_refresh)

        if currency not in market_map:
            raise UserWarning(f"not supported currency (upbit KRW market not found): {currency}")

        self.market = currency
        self.interval = interval
        self.query_string = {"market": market_map[currency], "count": 1}

        # interval(초) -> Upbit candles endpoint 매핑
        if self.interval == 60:
            self.URL = "https://api.upbit.com/v1/candles/minutes/1"
        elif self.interval == 180:
            self.URL = "https://api.upbit.com/v1/candles/minutes/3"
        elif self.interval == 300:
            self.URL = "https://api.upbit.com/v1/candles/minutes/5"
        elif self.interval == 600:
            self.URL = "https://api.upbit.com/v1/candles/minutes/10"
        else:
            raise UserWarning(f"not supported interval: {interval}")

    def get_info(self):
        """실시간 거래 정보(1개 캔들)를 반환"""
        data = self.__get_data_from_server()
        return [self.__create_candle_info(data[0])]

    def __create_candle_info(self, data):
        try:
            return {
                "type": "primary_candle",
                "market": self.market,
                "date_time": data["candle_date_time_kst"],
                "opening_price": float(data["opening_price"]),
                "high_price": float(data["high_price"]),
                "low_price": float(data["low_price"]),
                "closing_price": float(data["trade_price"]),
                "acc_price": float(data["candle_acc_trade_price"]),
                "acc_volume": float(data["candle_acc_trade_volume"]),
            }
        except KeyError as err:
            self.logger.warning(f"invalid data for candle info: {err}")
            return None

    def __get_data_from_server(self):
        try:
            response = requests.get(self.URL, params=self.query_string, timeout=10)
            response.raise_for_status()
            return response.json()
        except ValueError as error:
            self.logger.error(f"Invalid data from server: {error}")
            raise UserWarning("Fail get data from server") from error
        except requests.exceptions.HTTPError as error:
            self.logger.error(error)
            raise UserWarning("Fail get data from server") from error
        except requests.exceptions.RequestException as error:
            self.logger.error(error)
            raise UserWarning("Fail get data from server") from error
