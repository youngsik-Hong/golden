# SMTM (Algorithm-based Crypto Trading System)

## 📌 문서 목적
이 문서는 **SMTM 프로젝트의 전체 구조, 동작 원리, 데이터 흐름, 설계 의도**를 체계적으로 정리한 기술 문서입니다.

목표:
- 신규 개발자 또는 **다른 AI가 보더라도 전체 구조를 이해**할 수 있도록 함
- **전략 검증 → 시뮬레이션 → 실전 적용** 흐름을 명확히 설명
- 향후 **수정·확장·업데이트 시 기준 문서**로 사용

---

## 1️⃣ 시스템 설계 철학 (핵심 요약)

### 🔑 핵심 원칙
1. **1분봉 = 기본 틱 (절대 기준)**
2. **엔진·시뮬레이션·그래프는 동일한 캔들 단위 논리 좌표계 사용**
3. 그래프는 자동매매용이 아닌 **전략 검증/해석용 도구**
4. 실전(업비트) 적용을 전제로 한 **보수적 체결 모델**
5. BTC는 기준 검증 종목일 뿐, **전체 KRW 마켓 확장 가능 구조**

---

## 2️⃣ 전체 프로그램 트리 구조

```
smtm/
├─ config.py                      # 전역 설정
├─ log_manager.py                 # 로깅 관리
├─ runner/
│   └─ multi_backtest_runner.py   # UI/CLI 백테스트 진입점
│
├─ controller/
│   ├─ simulator.py               # 단일 시뮬레이션 컨트롤러
│   ├─ controller.py              # 실전 컨트롤러
│   └─ mass_simulator.py          # 대량 백테스트
│
├─ simulation_operator.py         # 시뮬레이션 메인 루프
│
├─ data/
│   ├─ simulation_data_provider.py
│   ├─ simulation_dual_data_provider.py
│   ├─ data_repository.py
│   ├─ database.py
│   └─ upbit_markets.py
│
├─ trader/
│   ├─ simulation_trader.py
│   └─ virtual_market.py
│
├─ strategy/
│   └─ (각 전략 구현 파일들)
│
├─ analyzer/
│   ├─ analyzer.py
│   ├─ data_analyzer.py
│   ├─ graph_generator.py         # 기본 그래프
│   └─ report_generator.py
│
├─ analyzer/custom_graph_generator.py
│   └─ CandleGraphGenerator       # 전략 검증용 고급 차트
│
├─ result/                        # 차트, CSV 결과
└─ output/                        # JSON 실행 결과
```

---

## 3️⃣ 시스템 전체 동작 흐름

### 🔁 상위 흐름 요약

```
UI / CLI
  ↓
multi_backtest_runner
  ↓
run_single_backtest()
  ↓
Simulator
  ↓
SimulationOperator (턴 기반 루프)
  ↓
DataProvider → Strategy → Trader
  ↓
Analyzer (기록)
  ↓
GraphGenerator / CSV / JSON
```

---

## 4️⃣ 핵심 모듈별 상세 설명

### 4.1 Config (config.py)

- 시스템 전역 설정

주요 항목:
- `simulation_source = 'upbit'`
- `candle_interval = 60` (1분봉 고정)
- 실전/시뮬레이션 **동일 데이터 기준 유지**

📌 **설계 의도**
- 모든 시간 계산의 기준을 1분봉으로 통일

---

### 4.2 Runner (multi_backtest_runner.py)

**역할:**
- UI 또는 CLI에서 실행되는 **단일 백테스트 진입점**

주요 기능:
- 파라미터 검증
- `run_single_backtest()` 호출
- 결과(JSON) 정규화
- 차트/CSV 미존재 시 CLI fallback 실행

📌 **중요 설계 포인트**
- UI 실행 시에도 result 폴더 산출물 보장
- 실전/시뮬레이션 엔진을 직접 호출 (중복 로직 제거)

---

### 4.3 Simulator (controller/simulator.py)

**역할:**
- 시뮬레이션 전체 생명주기 관리

주요 단계:
1. initialize()
2. start()
3. run_single()
4. terminate()

📌 **핵심 개념**
- `from_dash_to = yymmdd.000000-yymmdd.000000`
- 내부적으로 DateConverter를 통해 **정확한 1분봉 개수 산출**

---

### 4.4 SimulationOperator

**역할:**
- 시뮬레이션의 **실제 턴 기반 엔진**

핵심 구조:
- 1턴 = 1캔들
- `get_info()` → 전략 판단 → 주문 → 체결 → 기록

📌 **중요 판단**
- 시간 기반 루프 ❌
- **캔들 인덱스 기반 루프 ⭕**

---

### 4.5 DataProvider & DataRepository

**역할:**
- 과거 캔들 데이터 제공
- DB 캐시 + 서버 fallback 구조

특징:
- 업비트 KST 기준
- 누락 캔들 자동 복구
- 동일 DB를 시뮬레이션·실전 공용 사용

📌 **실전 정합성 매우 높음**

---

### 4.6 Trader & VirtualMarket

**역할:**
- 가상 거래소 역할

체결 로직 특징:
- 매수: 지정가 < 저가 → 체결 실패
- 매도: 지정가 ≥ 고가 → 체결 실패

📌 **실전 대비 보수적 모델**

---

### 4.7 Analyzer (리팩터링 구조)

구성:
- DataRepository (기록)
- DataAnalyzer (수익률 계산)
- GraphGenerator (기본 그래프)
- ReportGenerator (리포트)

📌 역할 분리로 유지보수 용이

---

### 4.8 CandleGraphGenerator (전략 검증용 핵심)

**목적:**
- 전략의 논리를 **눈으로 검증**

주요 기능:
- 캔들 + BB
- 하단 돌파 감지
- 10캔들 윈도우 생성
- RSI / MACD / Stoch 분석
- 후보 윈도우 강조
- CSV 요약 자동 생성

📌 **중요:**
- 그래프 좌표 = 캔들 인덱스
- 엔진 판단 시점과 1:1 매칭

---

## 5️⃣ 그래프와 실전 매매의 관계

| 항목 | 용도 |
|----|----|
| 시뮬레이션 엔진 | 실제 판단 기준 |
| 그래프 | 전략 검증 / 해석 |
| CSV | 수치 검증 |

⚠️ 그래프를 신호로 사용 ❌
✔️ 전략의 **합리성 검증 도구**

---

## 6️⃣ 확장·수정 시 반드시 지켜야 할 규칙

1. **1분봉 기준 절대 유지**
2. 시간 기반 로직 추가 금지
3. 엔진과 그래프 좌표계 분리 금지
4. 실전 체결보다 낙관적인 시뮬레이션 금지
5. 전략 판단 로직은 반드시 Strategy 내부에서만 변경

---

## 7️⃣ 현재 시스템 상태 요약

✔ 구조적으로 완성도 높음
✔ 실전 업비트 기준 정합성 확보
✔ 전략 검증용 그래프 목적 명확
✔ BTC → 전체 KRW 마켓 확장 가능

---

## 8️⃣ 이 문서를 읽은 개발자/AI를 위한 가이드

- 전략을 바꾸고 싶다면 → `strategy/`
- 체결 현실성을 바꾸고 싶다면 → `VirtualMarket`
- 그래프를 바꾸고 싶다면 → `CandleGraphGenerator`
- 실행 흐름을 바꾸고 싶다면 → **건드리지 말 것 (핵심 엔진)**

---

📌 **이 문서는 SMTM 프로젝트의 기준 문서입니다.**
향후 업데이트 시 본 문서와의 정합성을 반드시 확인해야 합니다.

