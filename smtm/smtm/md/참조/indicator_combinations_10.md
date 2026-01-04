# 눌림목 감지를 위한 10가지 지표 조합

**목표**: BB 하단 터치 + 추가 지표로 "진짜 눌림목" 필터링

---

## 🎯 지표 선정 기준

### 눌림목 특징

```
1. 과매도 상태 (RSI, Stoch)
2. 하락 모멘텀 약화 (MACD)
3. 변동성 확대 (ATR)
4. 지지선 근접 (EMA)
5. 거래량 급증 (Volume)
```

---

## 📊 10가지 지표 조합

### 조합 1: RSI 단독 (기본)

**컨셉**: 과매도만 확인

```python
# 라인 67-70
RSI_LIMIT = 30          # RSI < 30 (과매도)
MACD_LIMIT = 100000000  # 무조건 통과
STOCH_LIMIT = 100000    # 무조건 통과

# 라인 189-191
USE_ATR_FILTER = False
USE_EMA_FILTER = False
USE_VOLUME_FILTER = False
```

**기대**:
- 매수: 30~40개
- 특징: RSI 30 이하일 때만

---

### 조합 2: MACD 단독

**컨셉**: 하락 모멘텀 약화

```python
RSI_LIMIT = 100000      # 무조건 통과
MACD_LIMIT = 0          # MACD < 0 (음수)
STOCH_LIMIT = 100000    # 무조건 통과

USE_ATR_FILTER = False
USE_EMA_FILTER = False
USE_VOLUME_FILTER = False
```

**기대**:
- 매수: 35~45개
- 특징: 하락세에서만

---

### 조합 3: Stochastic 단독

**컨셉**: 단기 과매도

```python
RSI_LIMIT = 100000      # 무조건 통과
MACD_LIMIT = 100000000  # 무조건 통과
STOCH_LIMIT = 20        # Stoch < 20

USE_ATR_FILTER = False
USE_EMA_FILTER = False
USE_VOLUME_FILTER = False
```

**기대**:
- 매수: 20~30개
- 특징: 단기 과매도만

---

### 조합 4: RSI + MACD (보수적)

**컨셉**: 과매도 + 하락 약화

```python
RSI_LIMIT = 35          # RSI < 35 (약간 완화)
MACD_LIMIT = 0          # MACD < 0
STOCH_LIMIT = 100000    # 무조건 통과

USE_ATR_FILTER = False
USE_EMA_FILTER = False
USE_VOLUME_FILTER = False
```

**기대**:
- 매수: 15~25개
- 특징: 엄격한 필터

---

### 조합 5: RSI + Stoch (단기 신호)

**컨셉**: 단기 + 중기 과매도

```python
RSI_LIMIT = 30          # RSI < 30
MACD_LIMIT = 100000000  # 무조건 통과
STOCH_LIMIT = 20        # Stoch < 20

USE_ATR_FILTER = False
USE_EMA_FILTER = False
USE_VOLUME_FILTER = False
```

**기대**:
- 매수: 10~20개
- 특징: 강한 과매도만

---

### 조합 6: MACD + Stoch

**컨셉**: 모멘텀 + 단기 과매도

```python
RSI_LIMIT = 100000      # 무조건 통과
MACD_LIMIT = -100000    # MACD < -100K (강한 하락)
STOCH_LIMIT = 25        # Stoch < 25

USE_ATR_FILTER = False
USE_EMA_FILTER = False
USE_VOLUME_FILTER = False
```

**기대**:
- 매수: 10~15개
- 특징: 강한 하락 + 과매도

---

### 조합 7: 3종 지표 (원래 설정)

**컨셉**: 종합 판단

```python
RSI_LIMIT = 29          # 사용자 설정
MACD_LIMIT = -1600000   # 사용자 설정
STOCH_LIMIT = 2         # 사용자 설정

USE_ATR_FILTER = False
USE_EMA_FILTER = False
USE_VOLUME_FILTER = False
```

**기대**:
- 매수: 3~5개
- 특징: 가장 보수적

---

### 조합 8: RSI + ATR 필터

**컨셉**: 과매도 + 변동성 확대

```python
RSI_LIMIT = 30          # RSI < 30
MACD_LIMIT = 100000000  # 무조건 통과
STOCH_LIMIT = 100000    # 무조건 통과

USE_ATR_FILTER = True
ATR_PERCENTILE = 70     # 상위 30% 변동성
USE_EMA_FILTER = False
USE_VOLUME_FILTER = False
```

**기대**:
- 매수: 15~25개
- 특징: 변동성 큰 구간만

---

### 조합 9: MACD + EMA 필터

**컨셉**: 하락 약화 + EMA 이격

```python
RSI_LIMIT = 100000      # 무조건 통과
MACD_LIMIT = 0          # MACD < 0
STOCH_LIMIT = 100000    # 무조건 통과

USE_ATR_FILTER = False
USE_EMA_FILTER = True
EMA_DISTANCE_PERCENT_MIN = 2.0  # EMA에서 2% 이상 이격
USE_VOLUME_FILTER = False
```

**기대**:
- 매수: 20~30개
- 특징: 깊은 하락만

---

### 조합 10: RSI + 거래량 필터

**컨셉**: 과매도 + 거래량 급증

```python
RSI_LIMIT = 30          # RSI < 30
MACD_LIMIT = 100000000  # 무조건 통과
STOCH_LIMIT = 100000    # 무조건 통과

USE_ATR_FILTER = False
USE_EMA_FILTER = False
USE_VOLUME_FILTER = True
VOLUME_MULTIPLIER = 1.5  # 평균 거래량 1.5배
```

**기대**:
- 매수: 15~25개
- 특징: 거래량 터진 구간만

---

## 🎯 추천 테스트 순서

### Phase 1: 단일 지표 (기준선)

```
1. 조합 1: RSI 단독
   → 30~40개 매수

2. 조합 2: MACD 단독
   → 35~45개 매수

3. 조합 3: Stoch 단독
   → 20~30개 매수

목적: 각 지표의 특성 파악
```

---

### Phase 2: 2종 조합 (균형)

```
4. 조합 4: RSI + MACD
   → 15~25개 매수

5. 조합 5: RSI + Stoch
   → 10~20개 매수

6. 조합 6: MACD + Stoch
   → 10~15개 매수

목적: 최적 조합 찾기
```

---

### Phase 3: 필터 추가 (정밀)

```
8. 조합 8: RSI + ATR
   → 변동성 필터

9. 조합 9: MACD + EMA
   → 이격도 필터

10. 조합 10: RSI + Volume
   → 거래량 필터

목적: 정밀도 향상
```

---

### Phase 4: 최종 조합

```
7. 조합 7: 3종 지표
   → 가장 보수적
   → 최종 검증

목적: 최고 품질 신호
```

---

## 📋 지표 값 조정 가이드

### RSI (Relative Strength Index)

```python
RSI_LIMIT = 30  # 기본값

조정 방향:
- 20: 매우 강한 과매도 (매수 적음)
- 25: 강한 과매도
- 30: 적당한 과매도 (권장)
- 35: 약한 과매도 (매수 많음)
- 40: 매우 약한 과매도

권장 범위: 25~35
```

---

### MACD (Moving Average Convergence Divergence)

```python
MACD_LIMIT = 0  # 기본값 (음수만)

조정 방향:
- -500000: 매우 강한 하락 (매수 적음)
- -200000: 강한 하락
- -100000: 적당한 하락
- 0: 하락세 전환 (권장)
- 100000: 상승세 초기 (매수 많음)

권장 범위: -200000 ~ 0
```

---

### Stochastic

```python
STOCH_LIMIT = 20  # 기본값

조정 방향:
- 10: 매우 강한 과매도 (매수 적음)
- 15: 강한 과매도
- 20: 적당한 과매도 (권장)
- 25: 약한 과매도
- 30: 매우 약한 과매도 (매수 많음)

권장 범위: 15~25
```

---

### ATR 필터

```python
ATR_PERCENTILE = 70  # 기본값

조정 방향:
- 90: 상위 10% (매수 매우 적음)
- 80: 상위 20%
- 70: 상위 30% (권장)
- 60: 상위 40%
- 50: 상위 50% (매수 많음)

권장 범위: 60~80
```

---

### EMA 이격도 필터

```python
EMA_DISTANCE_PERCENT_MIN = 2.0  # 기본값

조정 방향:
- 3.0: 큰 이격 (매수 적음)
- 2.5: 적당한 이격
- 2.0: 작은 이격 (권장)
- 1.5: 매우 작은 이격
- 1.0: 거의 붙음 (매수 많음)

권장 범위: 1.5~3.0
```

---

### 거래량 필터

```python
VOLUME_MULTIPLIER = 1.5  # 기본값

조정 방향:
- 2.0: 평균 2배 (매수 적음)
- 1.8: 평균 1.8배
- 1.5: 평균 1.5배 (권장)
- 1.3: 평균 1.3배
- 1.2: 평균 1.2배 (매수 많음)

권장 범위: 1.3~2.0
```

---

## 🔧 코드 수정 방법

### 파일 경로

```
C:\golden\smtm\smtm\strategy\strategy_bbi_v3_spec_v1.py
```

---

### 수정 위치

```python
# ============================================================
# 라인 67-70: 지표 조건 (여기 수정!)
# ============================================================
RSI_LIMIT = 30              # ← 여기!
MACD_LIMIT = 0              # ← 여기!
STOCH_LIMIT = 20            # ← 여기!

# ============================================================
# 라인 189-191: 필터 활성화 (여기 수정!)
# ============================================================
USE_ATR_FILTER = False      # ← 여기!
USE_EMA_FILTER = False      # ← 여기!
USE_VOLUME_FILTER = False   # ← 여기!

# ============================================================
# 라인 195-203: 필터 설정 (필터 켜면 여기도 수정!)
# ============================================================
ATR_PERCENTILE = 70                 # ← 여기!
EMA_DISTANCE_PERCENT_MIN = 2.0      # ← 여기!
VOLUME_MULTIPLIER = 1.5             # ← 여기!
```

---

## 📊 테스트 체크리스트

### 각 조합마다 기록

```
[ ] 조합 번호: ___
[ ] 지표 설정: RSI=___, MACD=___, Stoch=___
[ ] 필터: ATR=___, EMA=___, Volume=___
[ ] 매수 횟수: ___개
[ ] 윈도우 분포: 전반부 ___개, 후반부 ___개
[ ] 평균 매수가: ______원
[ ] 최종 수익률: ___%
[ ] 특징: ___________________
```

---

### Excel 기록 양식

```
조합 | RSI | MACD | Stoch | ATR | EMA | Vol | 매수 | 수익 | 비고
-----|-----|------|-------|-----|-----|-----|------|------|-----
  1  | 30  |  무  |  무   | X   | X   | X   | 35개 | -0.5%| 기본
  2  | 무  |  0   |  무   | X   | X   | X   | 40개 | -0.3%| MACD
  3  | 무  |  무  |  20   | X   | X   | X   | 25개 | -0.7%| Stoch
  4  | 35  |  0   |  무   | X   | X   | X   | 18개 | +0.2%| 균형
 ... | ... | ...  | ...   | ... | ... | ... | ...  | ...  | ...
```

---

## 🎯 최적화 목표

### 찾아야 할 것

```
1. 매수 횟수: 20~30개
   → 너무 많으면 품질 낮음
   → 너무 적으면 기회 놓침

2. 수익률: 양수!
   → 최소 +0.5% 이상

3. 분포: 골고루
   → 전반부, 후반부 균등

4. 품질: 진짜 눌림목
   → 매수 후 반등률 높음
```

---

### 평가 기준

```
S급: 매수 20~30개, 수익률 +1% 이상
A급: 매수 15~35개, 수익률 +0.5% 이상
B급: 매수 10~40개, 수익률 0% 이상
C급: 매수 5~45개, 수익률 -0.5% 이상
D급: 그 외
```

---

## 💡 추가 아이디어

### 조합 11: 완화된 3종

```python
RSI_LIMIT = 35          # 29 → 35 (완화)
MACD_LIMIT = -500000    # -1.6M → -500K (완화)
STOCH_LIMIT = 10        # 2 → 10 (완화)
```

**기대**: 5~10개 (원래 3개보다 많음)

---

### 조합 12: 초단타형

```python
RSI_LIMIT = 40          # 매우 완화
MACD_LIMIT = 100000000  # 무조건 통과
STOCH_LIMIT = 30        # 완화

USE_VOLUME_FILTER = True
VOLUME_MULTIPLIER = 2.0  # 거래량 2배
```

**기대**: 급등 직전 포착

---

## ✅ 시작 가이드

### Step 1: 조합 1 테스트

```python
# strategy_bbi_v3_spec_v1.py
# 라인 67-70
RSI_LIMIT = 30
MACD_LIMIT = 100000000
STOCH_LIMIT = 100000
```

```bash
# 캐시 삭제
Get-ChildItem -Recurse -Filter "__pycache__" C:\golden\SMTM | Remove-Item -Recurse -Force

# 실행
python -m smtm --mode 1 --budget 500000 --from_dash_to 251011.000000-251012.000000 --term 60 --strategy BBI-V3-SPEC-V1 --currency BTC
```

---

### Step 2: 결과 기록

```
조합 1 결과:
- 매수: __개
- 수익률: __%
- 특징: __________
```

---

### Step 3: 다음 조합

```
조합 2로 변경:
RSI_LIMIT = 100000
MACD_LIMIT = 0
STOCH_LIMIT = 100000
```

---

## 🎉 마무리

### 10가지 조합 요약

```
1. RSI 단독
2. MACD 단독
3. Stoch 단독
4. RSI + MACD
5. RSI + Stoch
6. MACD + Stoch
7. 3종 지표 (원래)
8. RSI + ATR
9. MACD + EMA
10. RSI + Volume
```

---

**파이팅!** 💪

최적 조합을 찾으면 알려주세요!
결과를 보고 추가 조언 드리겠습니다! 😊
