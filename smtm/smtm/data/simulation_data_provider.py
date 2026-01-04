# smtm/data/simulation_data_provider.py

import sqlite3
from datetime import datetime, timedelta
from ..config import Config
from .data_provider import DataProvider
from ..log_manager import LogManager
from .data_repository import DataRepository

from .upbit_markets import krw_market_map


def _db_has_market(db_path: str, table: str, market_value: str) -> bool:
    try:
        con = sqlite3.connect(db_path)
        cur = con.cursor()
        cur.execute(f"SELECT 1 FROM {table} WHERE market=? LIMIT 1", (market_value,))
        row = cur.fetchone()
        con.close()
        return row is not None
    except Exception:
        return False


class SimulationDataProvider(DataProvider):
    AVAILABLE_CURRENCY = {
        "binance": {
            "BTC": "BTCUSDT",
            "ETH": "ETHUSDT",
            "DOGE": "DOGEUSDT",
            "XRP": "XRPUSDT",
        },
    }
    NAME = "SIMULATION DP"
    CODE = "SIM"

    def __init__(self, currency="BTC", interval=60):
        if Config.simulation_source not in ("upbit", "binance"):
            raise UserWarning(f"not supported source: {Config.simulation_source}")

        self.logger = LogManager.get_logger(__class__.__name__)

        # ✅ DB 경로 고정(프로젝트 루트 cwd 기준 실행이므로 "smtm.db" 그대로 OK)
        self.repo = DataRepository("smtm.db", interval=interval, source=Config.simulation_source)
        self.interval_min = interval / 60
        self.data = []
        self.index = 0

        if Config.simulation_source == "upbit":
            db_path = "smtm.db"
            table = "upbit"

            # 사용자가 "KRW-XXX"로 넣어도 허용
            raw = str(currency).upper().strip()
            if raw.startswith("KRW-"):
                krw_market = raw
                legacy_market = raw.split("-")[1]
            else:
                legacy_market = raw
                krw_market = f"KRW-{raw}"

            # 1) DB에 KRW-BTC 형식이 존재하면 그걸 사용
            if _db_has_market(db_path, table, krw_market):
                self.market = krw_market
                return

            # 2) 아니면 레거시(BTC)로 저장된 DB면 레거시로 조회
            if _db_has_market(db_path, table, legacy_market):
                self.market = legacy_market
                return

            # 3) 둘 다 없으면: 기존 로직(최신 업비트 마켓맵)으로 결정하되, 에러 메시지 강화
            market_map = krw_market_map(force_refresh=False)
            c = legacy_market
            if c not in market_map:
                raise UserWarning(f"not supported currency (upbit KRW market not found): {c}")
            self.market = market_map[c]

            # 그래도 없을 수 있으니 안내 로그
            self.logger.warning(
                f"[SIM-DP] upbit market resolved to {self.market}, but DB has no rows for both "
                f"{krw_market} and {legacy_market}. Please check DB contents."
            )
            return

        # binance
        c = str(currency).upper()
        if c not in self.AVAILABLE_CURRENCY["binance"]:
            raise UserWarning(f"not supported currency: {c}")
        self.market = self.AVAILABLE_CURRENCY["binance"][c]

    def initialize_simulation(self, end=None, count=100):
        self.index = 0
        end_dt = datetime.strptime(end, "%Y-%m-%dT%H:%M:%S")
        start_dt = end_dt - timedelta(minutes=count * self.interval_min)
        start = start_dt.strftime("%Y-%m-%dT%H:%M:%S")
        self.data = self.repo.get_data(start, end, market=self.market)

    def get_info(self):
        now = self.index
        if now >= len(self.data):
            return None

        self.index = now + 1
        self.logger.info(f'[DATA] @ {self.data[now]["date_time"]}')
        self.data[now]["type"] = "primary_candle"
        return [self.data[now]]
