# -*- coding: utf-8 -*-
"""
단독 검증 스크립트: 엔진 IPC CONFIG.APPLY 테스트
- UI 없이 엔진에 명령을 보내서 연결/응답을 확인한다.
"""
import sys
import traceback

def main():
    try:
        from smtm.ipc.client import IpcClient
    except Exception as e:
        print("[VERIFY][ERR] smtm.ipc.client.IpcClient import 실패:", e)
        print(traceback.format_exc())
        sys.exit(2)

    cli = None
    try:
        cli = IpcClient()
    except Exception as e:
        print("[VERIFY][ERR] IpcClient 생성 실패:", e)
        print(traceback.format_exc())
        sys.exit(3)

    payload = {
        "symbol": "KRW-BTC",
        "strategy_id": "BBI-V3-SPEC-V16",
        "profile": "SAFE",
        "params": {"_verify": True}
    }

    try:
        resp = cli.send_cmd("CONFIG.APPLY", payload)
    except Exception as e:
        print("[VERIFY][ERR] send_cmd 예외:", e)
        print(traceback.format_exc())
        sys.exit(4)

    print("[VERIFY] resp =", resp)
    ok = bool(resp.get("ok"))
    sys.exit(0 if ok else 1)

if __name__ == "__main__":
    main()
