# -*- coding: utf-8 -*-
"""IpcClient 시그널 시그니처(오버로드 포함) 검증"""
from __future__ import annotations

from smtm.ipc.client import IpcClient

def _can_connect(sig, label: str) -> bool:
    ok = True
    try:
        sig.connect(lambda *a, **k: None)
    except Exception:
        ok = False
    print(f"[VERIFY] {label}: {ok}")
    return ok

def main() -> None:
    cli = IpcClient()
    all_ok = True

    all_ok &= _can_connect(cli.cmd_connected, "cmd_connected()")
    # 오버로드 시그널은 [str] 인덱싱으로 접근 가능
    try:
        all_ok &= _can_connect(cli.cmd_connected[str], "cmd_connected(str)")
    except Exception:
        print("[VERIFY] cmd_connected(str): False")
        all_ok = False

    all_ok &= _can_connect(cli.cmd_disconnected, "cmd_disconnected()")
    try:
        all_ok &= _can_connect(cli.cmd_disconnected[str], "cmd_disconnected(str)")
    except Exception:
        print("[VERIFY] cmd_disconnected(str): False")
        all_ok = False

    all_ok &= _can_connect(cli.evt_connected, "evt_connected()")
    all_ok &= _can_connect(cli.evt_disconnected, "evt_disconnected()")
    all_ok &= _can_connect(cli.evt_message, "evt_message(dict)")

    if all_ok:
        print("[VERIFY] OK: required signals present (including overloads).")
    else:
        raise SystemExit(2)

if __name__ == "__main__":
    main()
