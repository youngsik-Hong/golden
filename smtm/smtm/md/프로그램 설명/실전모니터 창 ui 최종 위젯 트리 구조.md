1) 실전 모니터 창 UI 최종 위젯 트리 구조
목표 UX

한눈에 **현재 상태(연결/ARM/KILL/지연/리스크)**가 보인다.

차트보다 포지션/체결/알림/타임라인이 우선이다.

모든 패널은 도킹/분리/배치 변경이 가능해야 한다.

최상위 구조 (Qt6)

QMainWindow: LiveMonitorMainWindow

QStatusBar (항상 하단 고정)

QToolBar (상단 고정)

CentralWidget: QSplitter(수평)

(좌) “차트/지표 영역”

(우) “테이프/포지션/리스크/알림 요약”

Dock Widgets(하단/좌우 도킹 가능)

Timeline(감사 로그)

Orders/Trades(상세)

System Log

Alerts(경고 모음)

(선택) Strategy Debug(디버그)

A. 상단 툴바(QToolBar) – 운영 버튼(읽기 중심)

연결 상태 표시(LED)

[연결/동기화] (STATUS→SNAPSHOT→SUBSCRIBE)

[재동기화] (강제 SNAPSHOT.GET)

[이벤트 일시정지/재개] (렌더만 멈춤, 수신은 유지 가능)

[스크린샷/리포트 저장] (현재 화면 캡처/상태 덤프)

(선택) 필터: Symbol / TF / Verbosity

실주문 버튼(ARM/KILL)은 모니터에 넣더라도 “읽기 중심”을 유지하는 걸 권장합니다.
(실전 제어는 콘솔(ui_tuning_simulator) 주도)

B. 상태바(QStatusBar) – 한눈에 보는 핵심

고정 라벨들:

ENGINE: 연결됨/끊김

MODE: DISARMED/ARMED/KILLED

CFG: config_version / profile / params_hash

FEED: OK/DEGRADED/DOWN + lag_ms

LAST: last_price + last_tick_ts

RISK: OK/BLOCK (reason)

RUN: run_id

SEQ: last_seq

C. 중앙 좌측: 차트/지표 (Central Left)

QWidget: ChartPane

상단: Symbol/TF + 마지막 캔들 정보(시간, OHLC)

중앙: Candlestick Chart (pyqtgraph)

캔들 500~2000개 버퍼

체결/주문 마커(4~5단계부터)

하단: Indicator Panel

RSI, MACD, Stoch, EMA, BB 등

v1: 라인 차트 1~2개 + 값 테이블(최근값)

렌더 정책: 이벤트 들어올 때마다 그림 X, 100ms 타이머로 10Hz 이하 갱신

D. 중앙 우측: “운영 핵심 패널” (Central Right)

QSplitter(수직) 로 3구역을 추천합니다.

PositionCard(상단)

Side / Qty / AvgPrice

Unrealized PnL % / Realized PnL %

Exposure %

(선택) 최고점/최저점 기반 Drawdown

RiskCard(중단)

BlockState / BlockReason

Daily PnL % / Loss Limit %

주문 제한(분당), cooldown 등

TapePanel(하단)

최근 Trades (체결 테이프)

최근 Orders (주문 상태 테이프)

v3 단계에서는 빈 상태여도 UI 자리는 확보

E. Dock Widgets (도킹 가능한 보조 패널)

Timeline Dock (가장 중요)

TIMELINE.EVENT를 시간순으로 append

필터: level/category/code

클릭 시 meta 상세 표시

Orders Dock

ORDER.EVENT 전체 목록/필터

System Log Dock

IPC 연결/재연결/에러/예외 로그

Alerts Dock

WARN/ERROR/CRITICAL만 모아서 표시

“소리/팝업”은 옵션

2) 이벤트 타입/스키마 “고정 표” (콘솔↔엔진↔모니터 공용)
공통 Envelope(모든 EVT)
필드	타입	설명
v	int	프로토콜 버전 (1)
type	str	이벤트 타입
ts	str	엔진 타임스탬프(ms 권장)
run_id	str	엔진 세션 ID
symbol	str	종목
seq	int	단조 증가 시퀀스
payload	obj	타입별 데이터
필수 이벤트(Phase 3~4)
1) EVT.HEARTBEAT

용도: 끊김/지연 판단, 적체 감지

payload 핵심:

lag_ms, evt_backlog, engine_uptime_sec, health(feed/orders)

2) ENGINE.STATUS.UPDATE

용도: 상태바/요약 패널 안정 갱신(주기 + 상태 변경 시)

payload 핵심:

mode(armed/killed/block_orders)

config(strategy_id/profile/config_version/params_hash)

market(last_price/last_tick_ts)

position(요약)

risk(요약)

health(feed/latency_ms)

3) CONFIG.UPDATED

용도: 콘솔에서 CONFIG.APPLY 성공 → 모니터 즉시 반영

payload:

config_version, strategy_id, profile, symbol, params, params_hash

4) MODE.ARMED / MODE.DISARMED / MODE.KILLED

용도: 운영 모드 변경 즉시 표시

payload:

reason, armed_at(옵션), block_orders(옵션)

5) DATA.CANDLE

용도: 차트 업데이트

payload:

tf

kind = UPDATE | CLOSE

candle {t,o,h,l,c,v}

source

6) INDICATOR.UPDATE

용도: 지표 최신값 갱신(가볍게)

payload:

tf, at_t, values{rsi14, macd..., ema..., bb...}

7) TIMELINE.EVENT

용도: “왜 그랬는가” 기록 (관제 핵심)

payload:

level, category, code, msg, meta

(자리 확보) 주문 이벤트(Phase 5 이후)
ORDER.EVENT (단일 타입 + status)

payload:

order_id, client_oid

status(REQUEST/SENT/ACK/PARTIAL/FILLED/REJECTED/ERROR…)

side, order_type, price, qty, filled_qty, avg_fill_price

reason, ts_exchange

3) 콘솔(ui_tuning_simulator)에서 “모니터로 보내야 하는 것”의 정답

콘솔은 모니터에 직접 데이터를 밀지 않습니다.
반드시 엔진을 통해 간접 반영합니다.

콘솔 → 엔진: CONFIG.APPLY, LIVE.ARM/DISARM, KILL.SWITCH

엔진 → 모니터: CONFIG.UPDATED, MODE.*, STATUS.UPDATE, TIMELINE.EVENT 등

즉, 모니터는 “엔진이 말해주는 현실”만 표시합니다.