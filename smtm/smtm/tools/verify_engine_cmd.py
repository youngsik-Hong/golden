# -*- coding: utf-8 -*-
"""엔진 CMD 채널 연결 여부를 '최소 침습'으로 검증하는 도구.

목표:
- UI를 고치기 전에, 현재 IpcClient가 엔진 CMD 채널에 실제로 연결 가능한지 확인
- 모듈/경로 혼선 확인(smtm, IpcClient 파일 경로 출력)

사용:
cd C:\hys\smtm
python -m smtm.tools.verify_engine_cmd

준비:
- 별도 터미널에서 엔진 실행:
  python -m smtm.engine.engine_main
"""

from __future__ import annotations

import traceback

def main() -> None:
    import smtm
    print(f"[VERIFY] smtm={smtm.__file__}")

    try:
        from smtm.ipc.client import IpcClient
        import smtm.ipc.client as m
        print(f"[VERIFY] ipc_client={m.__file__}")
    except Exception as e:
        print(f"[VERIFY][ERR] IpcClient import 실패: {e}")
        print(traceback.format_exc())
        raise SystemExit(2)

    cli = IpcClient()

    # 가능한 경우 채널명 출력(없을 수도 있음)
    cmd_name = getattr(cli, "cmd_name", None)
    evt_name = getattr(cli, "evt_name", None)
    print(f"[VERIFY] client cmd_name={cmd_name} evt_name={evt_name}")

    # 연결 시도(메서드가 있을 때만)
    for fn in ("connect_cmd", "connect", "open_cmd"):
        if hasattr(cli, fn):
            try:
                ok = getattr(cli, fn)()
                print(f"[VERIFY] {fn}() => {ok}")
                break
            except Exception as e:
                print(f"[VERIFY][WARN] {fn}() 예외: {e}")

    # 가장 안전한 cmd: PING(엔진이 지원하면 ok=True)
    try:
        resp = cli.send_cmd("PING", {"from": "verify_engine_cmd"})
        print(f"[VERIFY] send_cmd('PING') => {resp}")
    except Exception as e:
        print(f"[VERIFY][ERR] send_cmd 예외: {e}")
        print(traceback.format_exc())
        raise SystemExit(2)

if __name__ == "__main__":
    main()
