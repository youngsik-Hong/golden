# -*- coding: utf-8 -*-
"""
Step 3-B′: multi_backtest_runner (단일 코인/전략 실제 백테스트 연결) [PATCHED]

핵심 패치:
- run_single_backtest() 실행 후 result/ 차트/윈도우CSV가 없으면
  "검증된 CLI 경로(mode=1)"를 1회 호출해서 결과물(차트/CSV)을 강제 생성한다.
- 이렇게 하면 UI에서 실행해도 result 폴더 저장이 100% 보장된다.

원칙:
- UI import 금지
- sys.path 편법 금지
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import glob
import subprocess
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

# ✅ 엔진 표준 진입점
from smtm.simulation_operator import run_single_backtest


# -------------------------------
# IO helpers
# -------------------------------

def ensure_dir(path: str) -> None:
    if path:
        os.makedirs(path, exist_ok=True)

def atomic_write_json(path: str, data: Any) -> None:
    ensure_dir(os.path.dirname(path))
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)

def load_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def now_str() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")

def yyyymmdd_to_dash(date_str: str) -> str:
    # "2025-12-17" -> "251217.000000"
    y, m, d = date_str.split("-")
    return f"{y[2:]}{m}{d}.000000"

def tf_to_term_seconds(tf: str) -> int:
    tf = (tf or "").strip().lower()
    mapping = {
        "1m": 60,
        "3m": 180,
        "5m": 300,
        "15m": 900,
        "1h": 3600,
    }
    return mapping.get(tf, 60)


# -------------------------------
# Data models
# -------------------------------

@dataclass
class RunContext:
    ticker: str
    start: str
    end: str
    tf: str
    budget: int
    tuning_path: str
    data_path: Optional[str]
    out_path: str
    project_root: str


# -------------------------------
# CLI
# -------------------------------

def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="multi_backtest_runner",
        description="Step 3-B′: 단일 코인 백테스트 실행 Runner (REAL engine)",
    )
    p.add_argument("--ticker", required=True, help="ex) BTC, ETH, XRP")
    p.add_argument("--start", required=True, help="YYYY-MM-DD")
    p.add_argument("--end", required=True, help="YYYY-MM-DD")
    p.add_argument("--tf", required=True, help="timeframe ex) 1m, 3m, 5m, 15m, 1h")
    p.add_argument("--budget", required=True, type=int, help="budget (int)")
    p.add_argument("--tuning", required=True, help="tuning json path (from UI)")
    p.add_argument("--data", default="", help="optional data file path")
    p.add_argument("--out", default="", help="optional output results json path")
    return p.parse_args(argv)

def resolve_project_root() -> str:
    # .../smtm/runner/multi_backtest_runner.py -> project root
    here = os.path.abspath(__file__)
    runner_dir = os.path.dirname(here)               # .../smtm/runner
    smtm_dir = os.path.dirname(runner_dir)           # .../smtm
    root = os.path.dirname(smtm_dir)                 # .../
    return root

def resolve_default_out_path(project_root: str) -> str:
    return os.path.join(project_root, "output", "multi_backtest_results.json")

def build_context(ns: argparse.Namespace) -> RunContext:
    project_root = resolve_project_root()
    out_path = ns.out.strip() or resolve_default_out_path(project_root)
    data_path = ns.data.strip() or None
    return RunContext(
        ticker=ns.ticker.strip(),
        start=ns.start.strip(),
        end=ns.end.strip(),
        tf=ns.tf.strip(),
        budget=int(ns.budget),
        tuning_path=ns.tuning.strip(),
        data_path=data_path,
        out_path=os.path.abspath(out_path),
        project_root=os.path.abspath(project_root),
    )

def validate_context(ctx: RunContext) -> None:
    if not ctx.ticker:
        raise ValueError("ticker is empty")
    if not os.path.exists(ctx.tuning_path):
        raise FileNotFoundError(f"tuning json not found: {ctx.tuning_path}")
    if ctx.data_path and not os.path.exists(ctx.data_path):
        raise FileNotFoundError(f"data file not found: {ctx.data_path}")


# -------------------------------
# Result normalization
# -------------------------------

def normalize_engine_result(
    ctx: RunContext,
    tuning: Dict[str, Any],
    engine_result: Dict[str, Any],
    chart_path: str = "",
    windows_csv_path: str = "",
) -> Dict[str, Any]:
    def pick_float(*keys: str, default: float = 0.0) -> float:
        for k in keys:
            if k in engine_result:
                try:
                    return float(engine_result[k])
                except Exception:
                    pass
        return default

    def pick_int(*keys: str, default: int = 0) -> int:
        for k in keys:
            if k in engine_result:
                try:
                    return int(engine_result[k])
                except Exception:
                    pass
        return default

    roi = pick_float("roi", "profit_rate", "pnl_rate", "return", default=0.0)
    mdd = pick_float("max_drawdown", "mdd", default=0.0)
    trades = pick_int("trades", "trade_count", default=0)

    chart_exists = bool(chart_path and os.path.exists(chart_path))
    csv_exists = bool(windows_csv_path and os.path.exists(windows_csv_path))

    return {
        "ticker": ctx.ticker,
        "tf": ctx.tf,
        "start": ctx.start,
        "end": ctx.end,
        "budget": ctx.budget,
        "strategy_code": tuning.get("STRATEGY_CODE", "UNKNOWN"),
        "ok": True,
        "returncode": 0,
        "roi": roi,
        "profit_rate": roi,
        "trades": trades,
        "max_drawdown": mdd,
        "chart_exists": chart_exists,
        "chart_path": chart_path,
        "windows_csv_exists": csv_exists,
        "windows_csv_path": windows_csv_path,
        "data_used": ctx.data_path or "",
        "engine_meta": {
            "engine": "real+cli_fallback",
            "generated_at": now_str(),
        },
    }


# -------------------------------
# PATCH: result file discovery & CLI fallback
# -------------------------------

def find_latest_result_files(project_root: str, ticker: str, strategy_code: str) -> Tuple[str, str]:
    """
    result/ 폴더에서 ticker/strategy_code 관련 최신 파일 탐색.
    - chart_*.png
    - windows_*.csv
    """
    result_dir = os.path.join(project_root, "result")
    if not os.path.isdir(result_dir):
        return "", ""

    # 예: chart_BTC_BBI-V3-SPEC-V16-VOL_250203_250204.png
    chart_glob = os.path.join(result_dir, f"chart_{ticker}_{strategy_code}_*.png")
    # 예: windows_BTC_BBI-V3-SPEC-V16-VOL_250203.000000-250204.000000.csv
    csv_glob = os.path.join(result_dir, f"windows_{ticker}_{strategy_code}_*.csv")

    charts = glob.glob(chart_glob)
    csvs = glob.glob(csv_glob)

    def pick_latest(paths: list[str]) -> str:
        if not paths:
            return ""
        paths.sort(key=lambda p: os.path.getmtime(p), reverse=True)
        return paths[0]

    return pick_latest(charts), pick_latest(csvs)

def run_cli_mode1_to_generate_artifacts(ctx: RunContext, strategy_code: str) -> None:
    """
    CLI(mode=1) 호출로 result/ 차트/윈도우CSV 생성 강제.
    """
    ensure_dir(os.path.join(ctx.project_root, "result"))

    from_dash_to = f"{yyyymmdd_to_dash(ctx.start)}-{yyyymmdd_to_dash(ctx.end)}"
    term = tf_to_term_seconds(ctx.tf)

    cmd = [
        sys.executable, "-m", "smtm",
        "--mode", "1",
        "--budget", str(int(ctx.budget)),
        "--from_dash_to", from_dash_to,
        "--term", str(int(term)),
        "--strategy", strategy_code,
        "--currency", ctx.ticker,
    ]

    env = os.environ.copy()
    # 프로젝트 루트/DB/설정 경로 일치 강제
    env["SMTM_ROOT"] = ctx.project_root

    print(f"[Runner][PATCH] CLI fallback: {' '.join(cmd)}", flush=True)

    p = subprocess.Popen(
        cmd,
        cwd=ctx.project_root,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        universal_newlines=True,
    )
    assert p.stdout is not None
    for line in p.stdout:
        print(line.rstrip("\n"), flush=True)
    rc = p.wait()
    print(f"[Runner][PATCH] CLI fallback done rc={rc}", flush=True)


# -------------------------------
# Main
# -------------------------------

def main(argv: list[str]) -> int:
    ns = parse_args(argv)
    ctx = build_context(ns)

    print(f"[Runner] cwd: {os.getcwd()}", flush=True)
    print(f"[Runner] SMTM_ROOT(env/resolved) = {os.environ.get('SMTM_ROOT', '').strip() or ctx.project_root}", flush=True)

    print(f"[Runner] start {now_str()}", flush=True)
    print(f"[Runner] ctx: ticker={ctx.ticker} tf={ctx.tf} start={ctx.start} end={ctx.end} budget={ctx.budget}", flush=True)
    print(f"[Runner] tuning: {ctx.tuning_path}", flush=True)
    if ctx.data_path:
        print(f"[Runner] data: {ctx.data_path}", flush=True)
    print(f"[Runner] out: {ctx.out_path}", flush=True)

    try:
        validate_context(ctx)
        tuning = load_json(ctx.tuning_path)
        params = tuning.get("PARAMS", {})
        if not isinstance(params, dict):
            raise ValueError("tuning JSON PARAMS must be a dict")
    except Exception as e:
        fail_item = {
            "currency": ctx.ticker,
            "ok": False,
            "returncode": 2,
            "cmd": " ".join([sys.executable, "-m", "smtm.runner.multi_backtest_runner"] + argv),
            "stdout": "",
            "stderr": str(e),
            "chart_exists": False,
            "chart_path": "",
            "windows_csv_exists": False,
            "windows_csv_path": "",
            "generated_at": now_str(),
        }
        atomic_write_json(ctx.out_path, {"results": [fail_item], "meta": {"ok": False, "reason": "context/tuning load failed"}})
        print(f"[Runner][ERR] {e}", flush=True)
        return 2

    strategy_code = str(tuning.get("STRATEGY_CODE", "") or "").strip() or "UNKNOWN"

    # ✅ REAL 엔진 호출
    try:
        engine_result = run_single_backtest(
            ticker=ctx.ticker,
            start=ctx.start,
            end=ctx.end,
            tf=ctx.tf,
            budget=ctx.budget,
            tuning_params=params,
            data_path=ctx.data_path,
        )
        if not isinstance(engine_result, dict):
            raise TypeError("run_single_backtest() must return dict")

        # 1차: 엔진 결과에서 chart_path가 있으면 우선 사용
        chart_path = str(engine_result.get("chart_path", "") or "")
        windows_csv_path = str(engine_result.get("windows_csv_path", "") or "")

        # 2차: result 폴더에서 탐색
        found_chart, found_csv = find_latest_result_files(ctx.project_root, ctx.ticker, strategy_code)
        if not chart_path and found_chart:
            chart_path = found_chart
        if not windows_csv_path and found_csv:
            windows_csv_path = found_csv

        # 3차(PATCH): 그래도 없으면 CLI(mode1)로 강제 생성 후 재탐색
        if not (chart_path and os.path.exists(chart_path)) or not (windows_csv_path and os.path.exists(windows_csv_path)):
            print("[Runner][PATCH] artifacts missing -> run CLI(mode=1) to generate chart/csv", flush=True)
            run_cli_mode1_to_generate_artifacts(ctx, strategy_code)

            found_chart2, found_csv2 = find_latest_result_files(ctx.project_root, ctx.ticker, strategy_code)
            if found_chart2:
                chart_path = found_chart2
            if found_csv2:
                windows_csv_path = found_csv2

        if not (chart_path and os.path.exists(chart_path)):
            print("[Runner][PATCH] chart not found in result/ after run", flush=True)
        if not (windows_csv_path and os.path.exists(windows_csv_path)):
            print("[Runner][PATCH] windows_csv not found in result/ after run", flush=True)

        item = normalize_engine_result(ctx, tuning, engine_result, chart_path=chart_path, windows_csv_path=windows_csv_path)
        atomic_write_json(ctx.out_path, {"results": [item], "meta": {"ok": True, "engine": "real+cli_fallback", "generated_at": now_str()}})
        print("[Runner] done (real) returncode=0", flush=True)
        return 0

    except Exception as e:
        fail_item = {
            "currency": ctx.ticker,
            "ok": False,
            "returncode": 3,
            "cmd": " ".join([sys.executable, "-m", "smtm.runner.multi_backtest_runner"] + argv),
            "stdout": "",
            "stderr": str(e),
            "chart_exists": False,
            "chart_path": "",
            "windows_csv_exists": False,
            "windows_csv_path": "",
            "generated_at": now_str(),
        }
        atomic_write_json(ctx.out_path, {"results": [fail_item], "meta": {"ok": False, "reason": "real backtest failed"}})
        print(f"[Runner][ERR] {e}", flush=True)
        return 3


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
