# SMTM (Simulation & Multi Trading Manager)

## 프로젝트 사양서 (Project Specification)

**버전**: v1.0 (Baseline)

**상태**: 기준선 확정 · 지속 개발용

**작성 목적**:
이 문서는 SMTM 프로젝트를 장기간 중단 없이 이어가기 위한 **정식 프로젝트 사양서**입니다.  
사람, 세션, GPT가 바뀌어도 동일한 맥락과 판단 기준을 유지할 수 있도록 **설계 철학, 불변 규칙, 파일 역할, 저장 스펙, 운영 로드맵**을 명시합니다.

---

## 1. 프로젝트 개요

### 1.1 프로젝트 명
**SMTM (Simulation & Multi Trading Manager)**

### 1.2 프로젝트 목적
- 전략 기반 백테스트 시스템 구축
- 백테스트와 실전 자동매매 간 **정합성 유지**
- 차트/CSV/JSON 등 분석 산출물의 **항상성 보장**
- 업비트 실전 자동매매까지 확장 가능한 구조 확보

### 1.3 현재 사용 전략
- **BBI V3 Spec v1.6 (Volume)**
- 전략 로직(진입/청산 규칙)은 본 프로젝트 전반에서 **절대 수정 금지**

### 1.4 기준 테스트 환경
- Ticker: BTC
- Timeframe: 1m
- Period: 2025-02-03 ~ 2025-02-04
- Budget: 1,000,000

---

## 2. 현재 기준선 상태 요약 (Baseline v1.0)

### 2.1 정상 동작 판정
아래 조건을 모두 만족하면 **정상 기준선**으로 간주한다.

- `multi_backtest_runner` 실행 Exit Code = 0
- `output/multi_backtest_results.json` 생성
- 결과 JSON에 error-only 레코드가 아닌 정상 결과 포함
- 동일 조건 반복 실행 시 결과 안정
- SIM 원본 산출물 생성
- result 디렉토리에 chart / windows CSV 생성

### 2.2 Golden Run
기준 실행 결과를 **Golden Run**으로 정의한다.

포함 파일:
- multi_backtest_results.json
- chart_*.png
- windows_*.csv
- SIM-*.txt / SIM-*.csv

Golden Run과 동일한 산출물이 나오면 **정상 동작**으로 판정한다.

---

## 3. 프로젝트 핵심 불변 규칙 (헌법)

### 3.1 Tick Advancement 단일화
- 1분봉 진행은 단 하나의 루프에서만 증가한다.
- 데이터/체결/그래프 인덱스는 동일 기준을 공유한다.

### 3.2 Fill Policy (체결 기준)
- FILLBASIS는 **로직 개념**이며 수익률에 직접 영향
- 로그 출력은 옵션이나, 체결 기준 변경은 전략 변경과 동일
- 체결 기준 정책은 results.json 메타에 항상 기록한다.

### 3.3 전략 로직 불변
- 진입/청산 조건 수정 금지
- 허용: 튜닝 파라미터 주입, 검증, 예외 처리, 로그

### 3.4 저장 스펙 불변
- SIM 원본 없이는 result 산출물 생성 불가
- 저장 실패는 반드시 결과 JSON에 사유 기록
- 조용한 실패(silent skip) 금지

---

## 4. 디렉토리 및 파일 구조 (의미 기준)

### 4.1 실행/제어 레이어
- smtm/runner/multi_backtest_runner.py
- smtm/controller/simulator.py
- smtm/simulation_operator.py

### 4.2 트레이딩/체결 레이어
- smtm/trader/simulation_trader.py
- smtm/trader/virtual_market.py (고위험 · 수정 금지)

### 4.3 전략 레이어
- smtm/strategy/strategy_bbi_v3_spec_v16_vol.py

### 4.4 분석/산출 레이어
- smtm/analyzer/graph_generator.py
- smtm/analyzer/report_generator.py

---

## 5. 저장(Artifacts) 정식 스펙

### 5.1 SIM 원본 산출물
- 디렉토리: output/
- 파일명:
  - SIM-{strategy_slug}-{from_num}-{to_num}.png
  - SIM-{strategy_slug}-{from_num}-{to_num}.csv

### 5.2 Runner 친화 산출물
- 디렉토리: result/
- 파일명:
  - chart_{ticker}_{strategy_slug}_{from_ymd}_{to_ymd}.png
  - windows_{ticker}_{strategy_slug}_{from_ymd}_{to_ymd}.csv

### 5.3 대표 실패 조건
- SIM 미생성 → result 미생성
- fallback(mode=1) 날짜 포맷 불일치 → DateConverter 실패
- 전략/튜닝 스키마 오류 → error-only 결과

---

## 6. 변경 이력 요약 (현재 기준선)

### 6.1 VirtualMarket
- verbose/log_noop 옵션 추가
- 체결 로직 자체는 유지

### 6.2 SimulationTrader
- VirtualMarket 옵션 전달

### 6.3 Multi Backtest Runner
- tuning json 검증 강화
- params_list 비어있을 경우 중단
- fallback(mode=1) 시도 이력 존재 (현재 위험 요소)

### 6.4 GraphGenerator
- SIM → result 복제 담당
- 파일명 파서가 저장 스펙의 근거

---

## 7. 위험 요소 (이번 라운드 미수정)

- Windows 로그 롤오버 파일 잠금 문제
- fallback(mode=1) 구조적 취약성
- 실전 체결 모델 단순화(슬리피지/부분체결 미반영)

---

## 8. 실전 자동매매 확장 설계 원칙

### 8.1 Trader 인터페이스 분리
- SimulationTrader ↔ UpbitTrader 동일 인터페이스

### 8.2 필수 운영 모듈
- 주문 상태기계(Order State Machine)
- 상태 영속화(State Persistence)
- 리스크 관리 레이어
- 이벤트 저장(Event Sourcing)

---

## 9. 향후 개발 로드맵

### Phase 1
- 기준선 자동 검증 스크립트
- 저장 안정화

### Phase 2
- 이벤트 스토어 도입
- 그래프/이벤트 1:1 대응

### Phase 3
- 실전 트레이더 구현
- 리스크/상태 복구

---

## 10. 최종 선언

이 문서는 SMTM 프로젝트의 **정식 기준 사양서**이다.

- 본 문서를 기준으로 모든 개선/확장은 판단한다.
- 본 문서를 위반하는 변경은 전략 변경 또는 시스템 퇴행으로 간주한다.
- Golden Run을 통과하지 못하는 변경은 병합하지 않는다.

---

(End of Document)

