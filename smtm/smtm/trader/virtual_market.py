from datetime import datetime, timedelta

from ..config import Config
from ..log_manager import LogManager
from ..data.data_repository import DataRepository


class VirtualMarket:
    """
    과거 캔들(OHLCV) 기반 가상 거래소(Virtual Market)

    - handle_request() 호출 1회 = turn 1회 진행
    - 요청이 0원/0수량이면(no-op) 기본적으로 아무 로그도 남기지 않고 turn만 진행
      (verbose+log_noop 옵션을 켜면 no-op도 로그 가능)

    주요 필드
    - data: 캔들 목록(dict)
    - turn_count: 현재 진행된 인덱스(턴)
    - balance: 현금 잔고
    - commission_ratio: 수수료율
    - asset: 보유자산 {market: (avg_price, amount)}
    """

    def __init__(
        self,
        market: str = "KRW-BTC",
        interval: int = 60,
        *,
        verbose: bool = False,
        log_noop: bool = False,
    ):
        self.logger = LogManager.get_logger(__class__.__name__)

        # verbosity controls (simulation default: quiet)
        self.verbose = bool(verbose)
        self.log_noop = bool(log_noop)

        self.repo = DataRepository(
            "smtm.db",
            interval=interval,
            source=Config.simulation_source,
        )

        self.data = None
        self.turn_count = 0
        self.balance = 0
        self.commission_ratio = 0.0005
        self.asset = {}
        self.is_initialized = False

        self.market = market
        self.interval = interval

    def initialize(self, end: str = None, count: int = 100, budget: float = 0):
        """
        과거 데이터 로딩 후 가상 마켓 초기화

        end: "%Y-%m-%dT%H:%M:%S"
        count: end 기준 과거로 몇 개 캔들을 로딩할지
        budget: 초기 예산(현금)
        """
        end_dt = datetime.strptime(end, "%Y-%m-%dT%H:%M:%S")
        start_dt = end_dt - timedelta(minutes=count * (self.interval / 60))
        start = start_dt.strftime("%Y-%m-%dT%H:%M:%S")

        self.data = self.repo.get_data(start, end, market=self.market)
        self.balance = budget
        self.is_initialized = True
        self.logger.debug(f"Virtual Market is initialized end: {end}, count: {count}")

    def get_balance(self):
        """
        현금+자산 정보 반환

        returns:
        {
            balance: 계좌 현금 잔고
            asset: {market: (avg_price, amount)}
            quote: {market: current_price}
            date_time: 기준 데이터 시간
        }
        """
        asset_info = {"balance": self.balance}
        quote = None

        try:
            quote = {
                self.data[self.turn_count]["market"]: self.data[self.turn_count][
                    "closing_price"
                ]
            }

            # 자산 debug 출력은 기존 스타일 유지 (debug 레벨)
            for name, item in self.asset.items():
                self.logger.debug(
                    f"asset item: {name}, item price: {item[0]}, amount: {item[1]}"
                )
        except (KeyError, IndexError) as msg:
            self.logger.error(f"invalid trading data {msg}")
            return None

        asset_info["asset"] = self.asset
        asset_info["quote"] = quote
        asset_info["date_time"] = self.data[self.turn_count]["date_time"]
        return asset_info

    def handle_request(self, request: dict):
        """
        거래 요청 처리

        request:
            {
                "type": "buy" | "sell" | ...
                "price": float/str
                "amount": float/str
                ...
            }

        return:
            dict 결과 또는
            - None: no-op(0원/0수량) 이거나 turn 진행만 하는 경우
            - "pass"/"error!" 등: 기존 코드 호환 유지
        """
        if self.is_initialized is not True:
            self.logger.error("virtual market is NOT initialized")
            return None

        # 현재 turn의 시각
        now = self.data[self.turn_count]["date_time"]

        # turn 진행
        self.turn_count += 1
        next_index = self.turn_count

        # 데이터 종료 처리 (game-over)
        if next_index >= len(self.data) - 1:
            return {
                "request": request,
                "type": request.get("type"),
                "price": 0,
                "amount": 0,
                "balance": self.balance,
                "msg": "game-over",
                "date_time": now,
                "state": "done",
            }

        # 0원/0수량 요청은 turn만 넘기고 no-op 처리
        try:
            if float(request.get("price", 0)) == 0 or float(request.get("amount", 0)) == 0:
                if self.verbose and self.log_noop:
                    self.logger.info("turn over")
                return None
        except Exception:
            # request 형식이 이상하면 기존과 동일하게 에러 처리
            self.logger.warning("invalid request payload")
            return "error!"

        rtype = request.get("type")
        if rtype == "buy":
            result = self.__handle_buy_request(request, next_index, now)
        elif rtype == "sell":
            result = self.__handle_sell_request(request, next_index, now)
        else:
            self.logger.warning("invalid type request")
            result = "error!"
        return result

    def __handle_buy_request(self, request, next_index, dt):
        price = float(request["price"])
        amount = float(request["amount"])
        buy_value = price * amount
        buy_total_value = buy_value * (1 + self.commission_ratio)
        old_balance = self.balance

        if buy_total_value > self.balance:
            self.logger.info("no money")
            return "pass"

        try:
            # 매수 체결 조건(기존 로직 유지):
            # 요청가가 다음 캔들 low보다 낮으면 체결 실패 처리
            if price < self.data[next_index]["low_price"]:
                self.logger.info("not matched")
                return "pass"

            name = self.data[next_index]["market"]
            if name in self.asset:
                asset = self.asset[name]
                new_amount = asset[1] + amount
                new_amount = round(new_amount, 6)
                new_value = (amount * price) + (asset[0] * asset[1])
                self.asset[name] = (round(new_value / new_amount), new_amount)
            else:
                self.asset[name] = (price, amount)

            self.balance -= buy_total_value
            self.balance = round(self.balance)

            self.__print_balance_info("buy", old_balance, self.balance, buy_value)

            return {
                "request": request,
                "type": request["type"],
                "price": request["price"],
                "amount": request["amount"],
                "msg": "success",
                "balance": self.balance,
                "state": "done",
                "date_time": dt,
            }
        except KeyError as msg:
            self.logger.warning(f"internal error {msg}")
            return "error!"

    def __handle_sell_request(self, request, next_index, dt):
        price = float(request["price"])
        amount = float(request["amount"])
        old_balance = self.balance

        try:
            name = self.data[next_index]["market"]
            if name not in self.asset:
                self.logger.info("asset empty")
                return "error!"

            # 매도 체결 조건(기존 로직 유지):
            # 요청가가 다음 캔들 high 이상이면 체결 실패 처리
            if price >= self.data[next_index]["high_price"]:
                self.logger.info("not matched")
                return "pass"

            sell_amount = amount
            if amount > self.asset[name][1]:
                sell_amount = self.asset[name][1]
                self.logger.warning(
                    f"sell request is bigger than asset {amount} > {sell_amount}"
                )
                del self.asset[name]
            else:
                new_amount = self.asset[name][1] - sell_amount
                new_amount = round(new_amount, 6)
                self.asset[name] = (
                    self.asset[name][0],
                    new_amount,
                )

            sell_value = sell_amount * price
            self.balance += sell_amount * price * (1 - self.commission_ratio)
            self.balance = round(self.balance)

            self.__print_balance_info("sell", old_balance, self.balance, sell_value)

            return {
                "request": request,
                "type": request["type"],
                "price": request["price"],
                "amount": sell_amount,
                "msg": "success",
                "balance": self.balance,
                "state": "done",
                "date_time": dt,
            }
        except KeyError as msg:
            self.logger.error(f"invalid trading data {msg}")
            return "error!"

    def __print_balance_info(self, trading_type, old, new, total_asset_value):
        # debug 레벨로만 남김 (시뮬레이션 기본 출력 최소화)
        self.logger.debug(f"[Balance] from {old}")
        if trading_type == "buy":
            self.logger.debug(
                f"[Balance] - {trading_type}_asset_value {total_asset_value}"
            )
        elif trading_type == "sell":
            self.logger.debug(
                f"[Balance] + {trading_type}_asset_value {total_asset_value}"
            )
        self.logger.debug(
            f"[Balance] - commission {total_asset_value * self.commission_ratio}"
        )
        self.logger.debug(f"[Balance] to {new}")
