# 눌림목 감지를 위한 10가지 지표 조합 (정확한 라인 번호)

**파일**: `strategy_bbi_v3_spec_v1.py`

---

## 🎯 수정할 라인 (정확한 위치!)

### 지표 조건 (라인 72-74)

```python
RSI_LIMIT = 100000           # 라인 72
MACD_LIMIT = 100000000       # 라인 73
STOCH_LIMIT = 100000         # 라인 74
```

---

### 필터 설정 (라인 88, 93)

```python
ATR_PERCENTILE = 0          # 라인 88
EMA_DISTANCE_PERCENT_MIN = 0    # 라인 93
```

---

### 자금 관리 (라인 97-98)

```python
POSITION_SIZE_PERCENT = 0.01  # 라인 97 (1%)
MAX_BUY_COUNT = 100      # 라인 98
```

---

## 📊 10가지 조합

### 조합 1: RSI 단독

**라인 72-74 수정**:
```python
RSI_LIMIT = 30              # 라인 72
MACD_LIMIT = 100000000      # 라인 73
STOCH_LIMIT = 100000        # 라인 74
```

**라인 88, 93 확인** (필터 OFF):
```python
ATR_PERCENTILE = 0          # 라인 88
EMA_DISTANCE_PERCENT_MIN = 0    # 라인 93
```

**기대**: 30~40개 매수

---

### 조합 2: MACD 단독

**라인 72-74 수정**:
```python
RSI_LIMIT = 100000          # 라인 72
MACD_LIMIT = 0              # 라인 73 ← 여기만 변경!
STOCH_LIMIT = 100000        # 라인 74
```

**라인 88, 93 확인**:
```python
ATR_PERCENTILE = 0          # 라인 88
EMA_DISTANCE_PERCENT_MIN = 0    # 라인 93
```

**기대**: 35~45개 매수

---

### 조합 3: Stochastic 단독

**라인 72-74 수정**:
```python
RSI_LIMIT = 100000          # 라인 72
MACD_LIMIT = 100000000      # 라인 73
STOCH_LIMIT = 20            # 라인 74 ← 여기만 변경!
```

**라인 88, 93 확인**:
```python
ATR_PERCENTILE = 0          # 라인 88
EMA_DISTANCE_PERCENT_MIN = 0    # 라인 93
```

**기대**: 20~30개 매수

---

### 조합 4: RSI + MACD (보수적)

**라인 72-74 수정**:
```python
RSI_LIMIT = 35              # 라인 72
MACD_LIMIT = 0              # 라인 73
STOCH_LIMIT = 100000        # 라인 74
```

**라인 88, 93 확인**:
```python
ATR_PERCENTILE = 0          # 라인 88
EMA_DISTANCE_PERCENT_MIN = 0    # 라인 93
```

**기대**: 15~25개 매수

---

### 조합 5: RSI + Stoch (단기 신호)

**라인 72-74 수정**:
```python
RSI_LIMIT = 30              # 라인 72
MACD_LIMIT = 100000000      # 라인 73
STOCH_LIMIT = 20            # 라인 74
```

**라인 88, 93 확인**:
```python
ATR_PERCENTILE = 0          # 라인 88
EMA_DISTANCE_PERCENT_MIN = 0    # 라인 93
```

**기대**: 10~20개 매수

---

### 조합 6: MACD + Stoch

**라인 72-74 수정**:
```python
RSI_LIMIT = 100000          # 라인 72
MACD_LIMIT = -100000        # 라인 73 (MACD < -100K)
STOCH_LIMIT = 25            # 라인 74
```

**라인 88, 93 확인**:
```python
ATR_PERCENTILE = 0          # 라인 88
EMA_DISTANCE_PERCENT_MIN = 0    # 라인 93
```

**기대**: 10~15개 매수

---

### 조합 7: 3종 지표 (보수적)

**라인 72-74 수정**:
```python
RSI_LIMIT = 29              # 라인 72 (사용자 설정)
MACD_LIMIT = -1600000       # 라인 73 (사용자 설정)
STOCH_LIMIT = 2             # 라인 74 (사용자 설정)
```

**라인 88, 93 확인**:
```python
ATR_PERCENTILE = 0          # 라인 88
EMA_DISTANCE_PERCENT_MIN = 0    # 라인 93
```

**기대**: 3~5개 매수

---

### 조합 8: RSI + ATR 필터

**라인 72-74 수정**:
```python
RSI_LIMIT = 30              # 라인 72
MACD_LIMIT = 100000000      # 라인 73
STOCH_LIMIT = 100000        # 라인 74
```

**라인 88, 93 수정** (ATR 필터 ON!):
```python
ATR_PERCENTILE = 70         # 라인 88 ← 여기 켜기!
EMA_DISTANCE_PERCENT_MIN = 0    # 라인 93
```

**기대**: 15~25개 매수

---

### 조합 9: MACD + EMA 필터

**라인 72-74 수정**:
```python
RSI_LIMIT = 100000          # 라인 72
MACD_LIMIT = 0              # 라인 73
STOCH_LIMIT = 100000        # 라인 74
```

**라인 88, 93 수정** (EMA 필터 ON!):
```python
ATR_PERCENTILE = 0          # 라인 88
EMA_DISTANCE_PERCENT_MIN = 2.0  # 라인 93 ← 여기 켜기!
```

**기대**: 20~30개 매수

---

### 조합 10: RSI + 거래량 필터

**주의**: 거래량 필터는 코드에 구현 안 됨!

대신 **조합 10-2: RSI + ATR + EMA 복합 필터**

**라인 72-74 수정**:
```python
RSI_LIMIT = 30              # 라인 72
MACD_LIMIT = 100000000      # 라인 73
STOCH_LIMIT = 100000        # 라인 74
```

**라인 88, 93 수정** (둘 다 ON!):
```python
ATR_PERCENTILE = 70         # 라인 88 ← 켜기!
EMA_DISTANCE_PERCENT_MIN = 1.5  # 라인 93 ← 켜기!
```

**기대**: 10~15개 매수

---

## 🔧 빠른 수정 방법

### VSCode / 메모장 사용

1. 파일 열기:
   ```
   C:\golden\smtm\smtm\strategy\strategy_bbi_v3_spec_v1.py
   ```

2. Ctrl+G 누르고 라인 번호 입력:
   ```
   72  → RSI_LIMIT
   73  → MACD_LIMIT
   74  → STOCH_LIMIT
   88  → ATR_PERCENTILE
   93  → EMA_DISTANCE_PERCENT_MIN
   ```

3. 값 수정 후 저장

4. 캐시 삭제 + 실행:
   ```powershell
   Get-ChildItem -Recurse -Filter "__pycache__" C:\golden\SMTM | Remove-Item -Recurse -Force
   python -m smtm --mode 1 --budget 500000 --from_dash_to 251011.000000-251012.000000 --term 60 --strategy BBI-V3-SPEC-V1 --currency BTC
   ```

---

## 📋 테스트 체크리스트

### 조합별 기록

```
[ ] 조합 1: RSI=30, MACD=무, Stoch=무
    매수: __개, 수익: __%, 비고: ______

[ ] 조합 2: RSI=무, MACD=0, Stoch=무
    매수: __개, 수익: __%, 비고: ______

[ ] 조합 3: RSI=무, MACD=무, Stoch=20
    매수: __개, 수익: __%, 비고: ______

[ ] 조합 4: RSI=35, MACD=0, Stoch=무
    매수: __개, 수익: __%, 비고: ______

[ ] 조합 5: RSI=30, MACD=무, Stoch=20
    매수: __개, 수익: __%, 비고: ______

[ ] 조합 6: RSI=무, MACD=-100K, Stoch=25
    매수: __개, 수익: __%, 비고: ______

[ ] 조합 7: RSI=29, MACD=-1.6M, Stoch=2
    매수: __개, 수익: __%, 비고: ______

[ ] 조합 8: RSI=30, ATR=70
    매수: __개, 수익: __%, 비고: ______

[ ] 조합 9: MACD=0, EMA=2.0
    매수: __개, 수익: __%, 비고: ______

[ ] 조합 10: RSI=30, ATR=70, EMA=1.5
    매수: __개, 수익: __%, 비고: ______
```

---

## 🎯 값 조정 가이드

### RSI_LIMIT (라인 72)

```python
# 더 많은 매수 원하면
RSI_LIMIT = 35  # 30 → 35
RSI_LIMIT = 40  # 30 → 40

# 더 적은 매수 원하면
RSI_LIMIT = 25  # 30 → 25
RSI_LIMIT = 20  # 30 → 20

# 권장 범위: 20~40
```

---

### MACD_LIMIT (라인 73)

```python
# 더 많은 매수 원하면
MACD_LIMIT = 100000    # 0 → 100K
MACD_LIMIT = 500000    # 0 → 500K

# 더 적은 매수 원하면
MACD_LIMIT = -200000   # 0 → -200K
MACD_LIMIT = -500000   # 0 → -500K

# 권장 범위: -500000 ~ 500000
```

---

### STOCH_LIMIT (라인 74)

```python
# 더 많은 매수 원하면
STOCH_LIMIT = 25  # 20 → 25
STOCH_LIMIT = 30  # 20 → 30

# 더 적은 매수 원하면
STOCH_LIMIT = 15  # 20 → 15
STOCH_LIMIT = 10  # 20 → 10

# 권장 범위: 10~30
```

---

### ATR_PERCENTILE (라인 88)

```python
# 더 많은 매수 원하면
ATR_PERCENTILE = 60  # 70 → 60 (상위 40%)
ATR_PERCENTILE = 50  # 70 → 50 (상위 50%)

# 더 적은 매수 원하면
ATR_PERCENTILE = 80  # 70 → 80 (상위 20%)
ATR_PERCENTILE = 90  # 70 → 90 (상위 10%)

# 권장 범위: 50~80
```

---

### EMA_DISTANCE_PERCENT_MIN (라인 93)

```python
# 더 많은 매수 원하면
EMA_DISTANCE_PERCENT_MIN = 1.0  # 2.0 → 1.0
EMA_DISTANCE_PERCENT_MIN = 1.5  # 2.0 → 1.5

# 더 적은 매수 원하면
EMA_DISTANCE_PERCENT_MIN = 2.5  # 2.0 → 2.5
EMA_DISTANCE_PERCENT_MIN = 3.0  # 2.0 → 3.0

# 권장 범위: 1.0~3.0
```

---

## ✅ 조합 1 시작 예시

### Step 1: 파일 수정

```python
# C:\golden\smtm\smtm\strategy\strategy_bbi_v3_spec_v1.py

# 라인 72-74 (Ctrl+G → 72)
RSI_LIMIT = 30              # ← 여기 수정!
MACD_LIMIT = 100000000      # 무조건 통과
STOCH_LIMIT = 100000        # 무조건 통과

# 라인 88, 93 확인
ATR_PERCENTILE = 0          # OFF
EMA_DISTANCE_PERCENT_MIN = 0    # OFF
```

---

### Step 2: 저장 (Ctrl+S)

---

### Step 3: 실행

```powershell
# 캐시 삭제
Get-ChildItem -Recurse -Filter "__pycache__" C:\golden\SMTM | Remove-Item -Recurse -Force

# 백테스트
python -m smtm --mode 1 --budget 500000 --from_dash_to 251011.000000-251012.000000 --term 60 --strategy BBI-V3-SPEC-V1 --currency BTC
```

---

### Step 4: 결과 기록

```
조합 1 결과:
- RSI_LIMIT = 30
- 매수: __개
- 수익률: __%
- 특징: __________
```

---

### Step 5: 다음 조합

```python
# 조합 2로 변경
RSI_LIMIT = 100000          # 라인 72
MACD_LIMIT = 0              # 라인 73 ← 변경!
STOCH_LIMIT = 100000        # 라인 74
```

---

## 🎉 마무리

### 정확한 라인 요약

```
라인 72: RSI_LIMIT
라인 73: MACD_LIMIT
라인 74: STOCH_LIMIT
라인 88: ATR_PERCENTILE
라인 93: EMA_DISTANCE_PERCENT_MIN
라인 97: POSITION_SIZE_PERCENT
라인 98: MAX_BUY_COUNT
```

---

**이제 정확합니다!** ✅

Ctrl+G로 라인 번호 찾아서 수정하세요! 🚀

파이팅! 💪
