
"""
 엔진켜기 
cd C:\hys\smtm
python -m smtm.engine.engine_main

ui 실행금지
cd C:\hys\smtm
python -m smtm.ui.ui_tuning_simulator

ui 실행
cd C:\hys\smtm
python -m smtm.tools.run_ui_debug




# PowerShell
Get-ChildItem -Recurse -Directory -Filter "__pycache__" C:\HYS\SMTM | Remove-Item -Recurse -Force


Get-ChildItem -Recurse -Directory -Filter "__pycache__" C:\golden\SMTM | Remove-Item -Recurse -Force


cd C:\hys\smtm
Remove-Item -Recurse -Force .\smtm\ui\__pycache__

cd C:\hys\smtm
python -m smtm.ui.live_monitor_pro


python -c "from smtm.ipc.client import IpcClient; c=IpcClient(); print(c.send_cmd('LIVE.UNBLOCK', {}, timeout_ms=1500))"
python -c "from smtm.ipc.client import IpcClient; c=IpcClient(); print(c.send_cmd('LIVE.ARM', {}, timeout_ms=1500))"
python -c "from smtm.ipc.client import IpcClient; c=IpcClient(); oid='cli-test-20260102-001'; p={'client_oid': oid, 'symbol': 'KRW-BTC', 'side': 'BUY', 'price': 1500000, 'qty': 0.001}; print(c.send_cmd('ORDER.PLACE.LIMIT', p, timeout_ms=2000))"

cd C:\hys\smtm
python -m smtm.engine.engine_main


python -c "from smtm.ipc.client import IpcClient; c=IpcClient(); print(c.send_cmd('LIVE.UNBLOCK', {}, timeout_ms=1500))"
python -c "from smtm.ipc.client import IpcClient; c=IpcClient(); print(c.send_cmd('LIVE.ARM', {}, timeout_ms=1500))"
python -c "from smtm.ipc.client import IpcClient; c=IpcClient(); oid='cli-test-20260102-001'; p={'client_oid': oid, 'symbol':'KRW-BTC','side':'BUY','price':1500000,'qty':0.001}; print(c.send_cmd('ORDER.PLACE.LIMIT', p, timeout_ms=3000))"


cd C:\hys\smtm
python -c "from smtm.ipc.client import IpcClient; c=IpcClient(); print(c.send_cmd('LIVE.UNBLOCK', {}, timeout_ms=1500))"
python -c "from smtm.ipc.client import IpcClient; c=IpcClient(); print(c.send_cmd('LIVE.ARM', {}, timeout_ms=1500))"
python -c "from smtm.ipc.client import IpcClient; c=IpcClient(); oid='cli-test-20260103-001'; p={'client_oid': oid, 'symbol':'KRW-BTC','side':'BUY','price':1500000,'qty':0.001}; print(c.send_cmd('ORDER.PLACE.LIMIT', p, timeout_ms=3000))"





Remove-Item -Recurse -Force .\smtm\engine\__pycache__ -ErrorAction SilentlyContinue
"""

