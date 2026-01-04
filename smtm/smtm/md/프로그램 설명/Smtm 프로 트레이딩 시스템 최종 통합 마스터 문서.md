# SMTM 프로 트레이딩 시스템 최종 통합 마스터 문서

본 문서는 **사용자가 최초 구상한 계획 문서들(p1.docx, p1-1.docx, 실전그래프 적용 계획, smtm_백테스트_실전_연계_시스템_구조_문서.md)**과,
**최근 확정된 ‘SMTM 프로 트레이딩 시스템 설계 마스터 문서’**를 완전히 통합하여 작성한 **최종본(Final Single Source of Truth)** 입니다.

이 문서 하나만으로 **어떤 AI / 개발자라도 프로젝트를 끝까지 완수할 수 있도록** 다음을 보장합니다.

* ❌ 의도 해석 불필요
* ❌ 구조 추측 불필요
* ❌ 설계 재논의 불필요
* ✅ 구현만 하면 되는 상태

---

## 0. 프로젝트의 본질적 목표 (변하지 않는 핵심)

### 이 프로젝트는 무엇을 만들려는가?

> **“시뮬레이션과 실전이 절대 혼동되지 않는
> 재현 가능한 프로 트레이딩 자동매매 시스템”**

### 절대 금지되는 것

* 시뮬레이션 결과를 실전 결과처럼 보이게 만드는 구조
* 주문 시점과 체결 시점을 혼동하는 그래프
* UI 종료 = 실전 중단 구조
* 암묵적 정책(코드 속 주석/관례)

---

## 1. 최상위 설계 철학 (AI/인간 공통 규칙)

### 1.1 Single Source of Truth (SSOT)

* **실전 상태의 단일 진실은 engine.exe**
* UI, 모니터는 절대 실전 상태를 계산하지 않는다

### 1.2 책임 분리 원칙

| 계층                  | 역할           | 금지 사항 |
| ------------------- | ------------ | ----- |
| ui_tuning_simulator | 설계·튜닝·검증·지휘  | 실전 실행 |
| engine              | 실전 판단·주문·리스크 | UI 신뢰 |
| live_monitor        | 관측·시각화       | 설정 변경 |

### 1.3 시간·체결·그래프 3대 오해 차단

* 시간축은 항상 **명시적(epoch 기반)**
* 체결은 항상 **EVENT 기반**
* 그래프는 **분석용 / 실전용 분리**

---

## 2. 전체 시스템 아키텍처 (확정)

```
[ ui_tuning_simulator.py ]  ── Command ──▶  [ engine.exe ]  ── Event ──▶  [ live_monitor.exe ]
        (설정/검증/지휘)             (실전 실행 SSOT)                 (관측 전용)
```

* 로컬 전용 IPC
* UI/모니터는 언제든 재시작 가능
* 엔진은 독립 생존

---

## 3. ui_tuning_simulator.py 최종 정의

### 유지되는 기능

* 전략/지표/리스크 파라미터 편집
* 프리셋(SAFE/BALANCED/AGGRESSIVE)
* 백테스트 실행
* 드라이런(DRYRUN, 실주문 없음)
* 실전 진입 UX (ARM/DISARM/KILL)

### 제거되는 실행 책임 (엔진으로 이동)

* 실시간 데이터 수집
* 실전 전략 루프
* 실주문/체결 관리
* 포지션·리스크 계산

> 삭제 ❌ / **실행 책임 이동 ⭕**

---

## 4. engine.exe (실전 실행 코어) 정의

### 엔진의 절대 규칙

* UI 없이 단독 실행 가능
* 모든 실전 상태의 단일 진실
* KILL은 언제나 최우선

### 엔진이 관리하는 핵심 상태

* armed / disarmed / killed
* config_version
* symbol / strategy / params
* (확장) 주문 / 포지션 / 리스크

---

## 5. IPC 통신 규약 (완전 확정)

### 5.1 채널

| 채널  | 용도       |
| --- | -------- |
| CMD | 요청/응답    |
| EVT | 엔진 → 스트림 |

### 5.2 메시지 프레이밍

* length-prefix JSON (uint32 + json)

### 5.3 공통 헤더

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

## 6. Command API (최종)

* PING
* ENGINE.STATUS
* SNAPSHOT.GET
* EVENT.SUBSCRIBE
* CONFIG.APPLY (DISARM_ONLY)
* LIVE.ARM / LIVE.DISARM
* KILL.SWITCH

모든 명령은 ACK(ok/error) 필수

---

## 7. Event Payload 스키마 (최종)

### 필수 이벤트

* EVT.HEARTBEAT
* ENGINE.STATUS.UPDATE
* CONFIG.UPDATED
* MODE.ARMED / DISARMED / KILLED
* DATA.CANDLE (UPDATE/CLOSE)
* INDICATOR.UPDATE (스냅형)
* TIMELINE.EVENT

### 이벤트 원칙

* 유실 허용
* 복구는 SNAPSHOT
* seq/run_id로 정합성 검증

---

## 8. Snapshot 스키마 (최종)

Snapshot은 **모니터 즉시 렌더링 + 복구용 상태 덩어리**이다.

### Snapshot 구조

* config
* mode
* health
* market
* position
* risk
* candles (배열, t 오름차순)
* indicators (candles 정렬 배열)
* recent_timeline
* recent_orders

### 규칙

* 배열 길이 정합 필수
* 계산 불가 값은 null
* Snapshot은 무겁게, Event는 가볍게

---

## 9. Live Monitor 최종 규칙

### 시작 시퀀스

1. CMD 연결
2. ENGINE.STATUS
3. SNAPSHOT.GET
4. EVT 연결
5. EVENT.SUBSCRIBE

### 렌더링

* 이벤트 수신 ≠ 즉시 렌더
* 10Hz 이하 배치 렌더

### 표시 우선순위

1. ARM/KILL/연결상태
2. 포지션/손익/차단
3. 주문·체결
4. 타임라인
5. 차트

---

## 10. 단계별 구현 로드맵 (변경 금지)

1. UI 구조 고정
2. 엔진 CMD 최소 구현
3. Event 스트림 + 모니터
4. 실데이터 관측
5. 주문 상태 머신
6. 실주문 활성화

---

## 11. 코드 착수 게이트 (최종)

다음 선언이 나오면 **모든 AI는 즉시 구현 단계로 전환**한다.

> **“본 문서 기준으로 SMTM 프로 트레이딩 시스템 구현을 시작한다.”**

설계 변경이 필요할 경우, 반드시 **본 문서를 먼저 수정**한다.

---

## 12. 최종 보증 문구 (AI/개발자 공통)

> 본 문서는 SMTM 프로젝트의 최종 설계 기준 문서이다.
>
> 이후 작성되는 모든 코드는 본 문서의 하위 산출물이며,
> 문서와 불일치하는 코드는 결함으로 간주한다.
