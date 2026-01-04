# SMTM 프로 트레이딩 시스템 설계 마스터 문서

본 문서는 **ui_tuning_simulator.py를 기반으로 한 프로 트레이딩 자동매매 시스템**을 구축하기 위해, 지금까지 합의·검토된 **모든 설계 결정 사항**을 한 곳에 보관·공유하기 위한 **단일 기준 문서(Single Source of Truth)** 입니다.

> 목적:
>
> * 이후 어떤 AI(또는 개발자)가 보더라도
> * 전체 맥락을 잃지 않고
> * 임의 수정 없이
> * 동일한 방향으로 구현·확장할 수 있도록 함

---

## 0. 설계 철학 (가장 중요)

### 핵심 원칙

1. **UI는 실행하지 않는다. 지휘만 한다.**
2. **엔진은 UI를 신뢰하지 않는다.** (엔진이 단일 진실, SSOT)
3. **실전 관측은 실행과 분리한다.** (live_monitor)
4. **이벤트 유실은 허용, 복구는 스냅샷으로**
5. **코드보다 설계가 먼저이며, 설계 확정 후에만 코드 작성**

---

## 1. 전체 아키텍처 개요

### 프로세스 구성 (로컬 전용)

```
[ ui_tuning_simulator.py ]   -> 설정/튜닝/검증/지휘 (콘솔)
            |
            |  Command (IPC)
            v
[ engine.exe ]               -> 실전 실행 코어 (SSOT)
            |
            |  Event Stream (IPC)
            v
[ live_monitor.exe ]         -> 관측 전용 모니터
```

### 각 프로세스의 정체성

| 구성요소                | 역할                       | 절대 하지 않는 것 |
| ------------------- | ------------------------ | ---------- |
| ui_tuning_simulator | 전략 설계, 백테스트, 드라이런, 실전 지휘 | 실전 실행, 주문  |
| engine              | 데이터/전략/주문/포지션/리스크의 단일 진실 | UI 신뢰      |
| live_monitor        | 차트/체결/포지션/타임라인 관측        | 설정 변경      |

---

## 2. ui_tuning_simulator.py의 최종 역할

### 유지되는 기능

* 전략/지표/리스크 파라미터 편집
* 프리셋 관리 (SAFE / BALANCED / AGGRESSIVE)
* 백테스트 실행 및 결과 분석
* 드라이런(DRY-RUN, 실주문 없음)
* 결과/아티팩트 뷰어
* 실전 진입 UX (ARM/DISARM/KILL 버튼)

### 제거(이동)되는 실행 책임

* 실시간 데이터 수집
* 실전 전략 루프
* 실주문/체결 관리
* 포지션/리스크 최종 계산

> ⚠️ 제거 = 삭제 ❌ / **엔진으로 실행 책임 이동 ⭕**

---

## 3. 엔진(engine.exe) 설계 요약

### 엔진의 핵심 성격

* UI 없이도 단독 실행 가능
* 실전 상태의 **단일 진실(SSOT)**
* UI/모니터는 언제든 재시작 가능

### 엔진이 관리하는 상태

* armed / disarmed / killed
* config_version
* symbol / strategy / params
* (추후) 주문/포지션/리스크

---

## 4. IPC 설계 (로컬 전용)

### 채널 분리

| 채널  | 용도              |
| --- | --------------- |
| CMD | 요청/응답 (명령)      |
| EVT | 엔진 → UI/모니터 스트림 |

### 메시지 프레이밍

* **Length-prefix JSON (uint32 + JSON bytes)**

### 공통 헤더 (모든 메시지)

```json
{
  "v": 1,
  "type": "...",
  "ts": "YYYY-MM-DD HH:MM:SS.mmm",
  "run_id": "live-YYYYMMDD-XXX",
  "symbol": "BTC-KRW",
  "seq": 12345,
  "payload": {}
}
```

---

## 5. Command API (확정)

### 기본 명령

* PING
* ENGINE.STATUS
* SNAPSHOT.GET
* EVENT.SUBSCRIBE

### 설정/제어

* CONFIG.APPLY (DISARM_ONLY 기본)
* LIVE.ARM
* LIVE.DISARM
* KILL.SWITCH

### 응답 규칙

* 모든 CMD는 `ACK(ok/error)` 반환

---

## 6. Event Payload 스키마 (확정)

### 필수 이벤트 세트 (3단계)

1. EVT.HEARTBEAT
2. ENGINE.STATUS.UPDATE
3. CONFIG.UPDATED
4. MODE.ARMED / DISARMED / KILLED
5. DATA.CANDLE (UPDATE / CLOSE)
6. INDICATOR.UPDATE (스냅형)
7. TIMELINE.EVENT

> 이벤트는 **유실 전제**, 상태 복구는 **SNAPSHOT**으로 수행

---

## 7. Snapshot 스키마 (완전 확정)

### Snapshot 목적

* 모니터 최초 로딩 즉시 화면 구성
* 재연결/유실 시 상태 복구

### Snapshot 최상위 구조

```json
{
  "snapshot_version": 1,
  "ts": "...",
  "run_id": "...",
  "symbol": "BTC-KRW",
  "tf": "1m",

  "config": {},
  "mode": {},
  "health": {},

  "market": {},
  "position": {},
  "risk": {},

  "candles": {},
  "indicators": {},

  "recent_orders": [],
  "recent_timeline": []
}
```

### 핵심 규칙

* candles.items는 t 오름차순
* indicators 배열은 candles와 길이 정렬
* 계산 불가 값은 null
* Snapshot은 무겁고, Event는 가볍게

---

## 8. Live Monitor 설계 원칙

### 모니터 시작 시퀀스

1. CMD 연결
2. ENGINE.STATUS
3. SNAPSHOT.GET
4. EVT 연결
5. EVENT.SUBSCRIBE

### 렌더링 규칙

* 이벤트 수신 ≠ 즉시 렌더
* StateStore 버퍼 → UI 타이머 렌더 (≤10Hz)

### 표시 우선순위

1. ARM/KILL/연결상태/지연
2. 현재가/포지션/손익/차단
3. 주문/체결 테이프
4. 타임라인(왜 그런가)
5. 차트/지표

---

## 9. 상태 전이 규칙 (엔진 강제)

* killed == true → ARM 불가
* armed == true → CONFIG.APPLY 불가
* DISARM은 언제나 허용
* KILL은 언제나 최우선

---

## 10. 단계별 진행 로드맵

### 1단계

* ui_tuning_simulator UI 구조 고정
* 실전 실행 책임 제거

### 2단계

* 엔진 최소 프로토타입 (CMD)

### 3단계

* Event 스트림 + live_monitor

### 4단계

* 실데이터 연결 (주문 없음)

### 5단계

* 주문 상태 머신 + 리스크

### 6단계

* 실주문 활성화

---

## 11. 코드 작업 착수 조건 (Gate)

다음 조건이 충족되면 **코드 작성 시작**:

* Event Payload 확정 ✅
* Snapshot 스키마 확정 ✅
* 본 문서 내용에 대해 "이 스펙으로 진행" 선언

---

## 12. 최종 선언 문구 (보관용)

> 본 문서는 SMTM 프로 트레이딩 시스템의 설계 기준 문서이며,
> 이후 모든 구현·수정·확장은 본 문서를 기준으로 한다.
>
> 설계 변경이 필요할 경우, 코드를 수정하기 전에
> 반드시 본 문서를 먼저 개정한다.
