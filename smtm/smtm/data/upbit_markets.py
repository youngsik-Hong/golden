import json
import os
import time
from typing import Dict, List

import requests


def _project_root() -> str:
    # .../smtm/data/upbit_markets.py 기준으로 repo 루트(C:\hys\smtm) 찾기
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def _cache_path() -> str:
    out_dir = os.path.join(_project_root(), "output")
    os.makedirs(out_dir, exist_ok=True)
    return os.path.join(out_dir, "upbit_markets_krw.json")


def fetch_upbit_krw_tickers() -> List[str]:
    """
    업비트 KRW 마켓 전체 티커 목록을 가져온다. 예) ["BTC","ETH","XRP",...]
    """
    url = "https://api.upbit.com/v1/market/all"
    r = requests.get(url, params={"isDetails": "false"}, timeout=10)
    r.raise_for_status()
    data = r.json()

    tickers: List[str] = []
    for row in data:
        market = row.get("market", "")
        if market.startswith("KRW-"):
            tickers.append(market.split("-")[1])

    tickers = sorted(set(tickers))
    return tickers


def load_krw_tickers(force_refresh: bool = False, max_age_sec: int = 3600) -> List[str]:
    """
    캐시가 있으면 캐시를 우선 사용하고, 오래됐으면 갱신한다.
    max_age_sec 기본 1시간.
    """
    path = _cache_path()

    if not force_refresh and os.path.exists(path):
        try:
            st = os.stat(path)
            age = time.time() - st.st_mtime
            if age <= max_age_sec:
                with open(path, "r", encoding="utf-8") as f:
                    obj = json.load(f)
                if isinstance(obj, dict) and "tickers" in obj:
                    return list(obj["tickers"])
        except Exception:
            # 캐시가 깨졌으면 아래에서 재생성
            pass

    tickers = fetch_upbit_krw_tickers()
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"generated_at": int(time.time()), "tickers": tickers}, f, indent=2, ensure_ascii=False)
    return tickers


def krw_market_map(force_refresh: bool = False) -> Dict[str, str]:
    """
    {"BTC":"KRW-BTC", "1INCH":"KRW-1INCH", ...}
    """
    tickers = load_krw_tickers(force_refresh=force_refresh)
    return {t: f"KRW-{t}" for t in tickers}
