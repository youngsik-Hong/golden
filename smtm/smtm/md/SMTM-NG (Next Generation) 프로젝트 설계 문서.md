SMTM-NG (Next Generation) 프로젝트 설계 문서
0. 프로젝트 목적

기존 SMTM 프로젝트에서 발생한 문제:

UI 렉 심각 (PyQt + pyqtgraph + IPC 혼합 구조)

이벤트 폭주로 인한 응답 지연

UI ↔ Engine ↔ Trader 결합도 과도

PyQt5/6, Python 3.9/3.10 혼용으로 인한 유지보수 난이도 증가

“고치면 다른 곳이 깨지는” 상태

SMTM-NG의 목표는 다음 4가지다.

UI 반응성 보장 (60fps 유지, 이벤트 지연 없음)

엔진/트레이더/UI 완전 분리

관측 전용 UI의 절대 안정성

단계별 확장 가능 구조

1. 프로젝트 분리 전략 (가장 중요)
1.1 기존 SMTM에서 가져오지 않는 것 ❌

절대 가져오지 말 것:

live_monitor_pro.py 전체

pyqtgraph 기반 캔들 렌더링 로직

Qt Signal 폭주 구조

Engine 내부 상태 직접 접근

기존 IPC Client/Signal 구조

👉 참고만 하고 코드 복사는 금지

1.2 새 프로젝트의 기본 철학
항목	원칙
UI	Read-only, 상태만 표현
Engine	Headless, UI 모름
Trader	Engine 내부 모듈
IPC	단방향 이벤트 스트림
렌더링	최소 데이터, 배치 처리
실패	UI가 죽어도 Engine은 계속
2. 전체 아키텍처
┌────────────┐      events       ┌──────────────┐
│  ENGINE     │ ─────────────▶  │   EVENT BUS   │
│ (strategy)  │                  │ (ZMQ / Redis)│
└────────────┘                  └───────┬──────┘
                                               
                                        subscribe
                                               
                                  ┌──────────────┐
                                  │   UI (NG)    │
                                  │  Read-only   │
                                  └──────────────┘

3. 기술 스택 (확정안)
3.1 Python / Runtime
항목	선택
Python	3.11 (고정)
OS	Windows / Linux
venv	필수
3.2 IPC (가장 중요)

권장: ZeroMQ (PUB/SUB)

이유:

Qt Signal 제거 가능

이벤트 폭주 제어 쉬움

UI는 단순 Subscriber

대안:

Redis Streams (차후)

3.3 UI 기술
항목	선택
UI Framework	PyQt6
차트	QGraphicsView 직접 구현
pyqtgraph	❌ 사용 금지
멀티스레드	UI 스레드 + 1 수신 스레드
4. 이벤트 설계 (성능 핵심)
4.1 이벤트는 반드시 “요약형”

❌ 잘못된 예:

{
  "candles": [120개],
  "indicators": {...},
  "positions": {...}
}


✅ 올바른 예:

{
  "type": "TICK",
  "t": 1700000000,
  "o": 1501000,
  "h": 1501200,
  "l": 1500800,
  "c": 1501100
}

4.2 이벤트 종류 (최소)
TICK          (1초~1분)
INDICATOR     (RSI, EMA 등)
HEARTBEAT     (1초)
STATUS        (모드/연결 상태)


❗ 주문/체결 이벤트는 UI v2 이후

5. UI 구조 (렉 제거 핵심)
5.1 스레드 구조
Main Thread (Qt)
 ├─ paint / input
 └─ render timer (30~60fps)

Worker Thread
 └─ ZMQ recv (queue 적재)


UI 스레드에서 절대 IPC 직접 수신 금지

Queue size 제한 필수 (예: 100)

5.2 렌더링 전략

캔들 최대 표시 개수: 200

새 데이터 → append → 초과분 pop

매 tick마다 전체 redraw ❌

dirty flag 방식

6. 단계별 개발 계획
Phase 1 — 최소 안정판 (MVP)

 ZMQ PUB/SUB 연결

 캔들 1개 실시간 표시

 EMA 1개

 FPS 안정성 확인

👉 이 단계에서 절대 전략/주문 없음

Phase 2 — 관측 강화

 RSI / BB

 스케일 자동 조절

 데이터 누락 대응

Phase 3 — 시뮬/리플레이

 로그 기반 재생

 속도 조절

Phase 4 — 주문/포지션 UI (선택)

완전 분리된 별도 패널

7. 성능 기준 (명문화)
항목	기준
UI FPS	≥ 30
이벤트 지연	< 50ms
UI 프리징	0
Engine 영향	없음
8. 실패 시 대응 원칙

UI 죽으면 → 자동 재시작

Engine은 절대 종료되지 않음

IPC 끊겨도 UI는 유지

9. 저장소 구조 (추천)
smtm-ng/
 ├─ engine/
 ├─ trader/
 ├─ events/
 ├─ ui/
 │   ├─ app.py
 │   ├─ charts/
 │   └─ widgets/
 ├─ common/
 └─ docs/

10. 기존 SMTM과의 관계

SMTM = 레거시 / 참고

SMTM-NG = 실전용

👉 두 프로젝트는 영원히 병합하지 않음