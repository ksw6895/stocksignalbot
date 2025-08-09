# 시그널 포착 전략 상세 문서

## 전략 개요

이 트레이딩 전략은 **"Upper Section Strategy"** 로 명명되며, 주간(1w) 또는 일간(1d) 차트에서 특정 패턴을 식별하여 매수 시그널을 생성합니다. 핵심은 단일 고점(Single Peak) 이후 베어리시 캔들 패턴을 확인하고, 가격이 EMA 아래로 떨어질 때 진입하는 것입니다.

## 1. 지표 계산 (Indicators)

### 1.1 EMA (Exponential Moving Average) 계산

```python
def compute_ema_series(prices: pd.Series, period: int) -> pd.Series:
    """
    지수이동평균 계산
    
    매개변수:
    - prices: 종가 시리즈
    - period: EMA 기간 (15 또는 33)
    
    계산 방법:
    1. 데이터가 period보다 적으면 모든 값을 None으로 반환
    2. alpha = 2.0 / (period + 1)
    3. 처음 period개 캔들의 단순이동평균(SMA)을 초기값으로 사용
    4. 이후 각 캔들에 대해: EMA = 현재가격 * alpha + 이전EMA * (1 - alpha)
    """
    if len(prices) < period:
        return pd.Series([None]*len(prices), index=prices.index)
    
    alpha = 2.0 / (period + 1)
    ema_values = [None]*(period-1)
    
    # 초기 SMA 계산
    initial_sma = prices.iloc[:period].mean()
    ema_values.append(initial_sma)
    
    # EMA 반복 계산
    for i in range(period, len(prices)):
        prev_ema = ema_values[-1]
        curr_val = prices.iloc[i]
        curr_ema = curr_val * alpha + prev_ema * (1 - alpha)
        ema_values.append(curr_ema)
    
    return pd.Series(ema_values, index=prices.index)
```

### 1.2 사용되는 EMA 기간
- **EMA 15**: 모든 캔들이 베어리시일 때 사용
- **EMA 33**: 한 개를 제외한 모든 캔들이 베어리시일 때 사용

## 2. 단일 고점 (Single Peak) 식별

### 2.1 단일 고점 조건

```python
def check_single_peak(highs: pd.Series, closes: pd.Series, recent_window=7, total_window=200) -> int:
    """
    단일 고점 식별 로직
    
    매개변수:
    - highs: 고가 시리즈
    - closes: 종가 시리즈
    - recent_window: 최근 윈도우 크기 (주간=5, 일간=7)
    - total_window: 전체 검색 윈도우 (주간=52, 일간=200)
    
    조건:
    1. total_window 내에서 최고가가 단 하나만 존재해야 함
    2. 그 최고가가 recent_window 내에 위치해야 함
    3. 고점에서의 고가가 15-EMA의 1.2배 이상이어야 함 (20% 이상 높음)
    4. recent_window 내 최소 하나의 종가가 이전 고가들보다 높아야 함
    5. 고점 캔들의 종가 또는 그 직전 캔들의 종가가 이전 모든 고가보다 높아야 함
    
    반환값:
    - 조건을 만족하는 고점의 인덱스, 조건 불만족시 -1
    """
```

#### 2.1.1 최고가 위치 확인
```python
# total_window 범위 내에서 최고가 찾기
mod_window = min(len(highs), total_window)
subset_highs = highs.iloc[-mod_window:]
max_val = subset_highs.max()
max_indices = subset_highs[subset_highs == max_val].index

# 최고가가 유일해야 함
if len(max_indices) != 1:
    return -1
peak_idx = max_indices[0]

# 최고가가 recent_window 내에 있어야 함
if peak_idx not in subset_highs.iloc[-recent_window:].index:
    return -1
```

#### 2.1.2 EMA 대비 고점 검증
```python
# 15-EMA 계산
ema_series = compute_ema_series(subset_closes, 15)
ema_value = ema_series[peak_idx]

# 고점이 EMA의 120% 이상이어야 함
if subset_highs[peak_idx] < 1.2 * ema_value:
    return -1
```

#### 2.1.3 돌파 확인
```python
# recent_window 이전의 최고가
split_point = mod_window - recent_window - 1
earlier_highs = subset_highs.iloc[:split_point]
max_earlier_high = earlier_highs.max()

# 최근 종가 중 하나가 이전 최고가를 돌파해야 함
recent_closes = subset_closes.iloc[-(recent_window + 1):]
if not (recent_closes > max_earlier_high).any():
    return -1
```

#### 2.1.4 고점 캔들 종가 검증
```python
# 고점 캔들 또는 직전 캔들의 종가가 이전 고가들을 돌파해야 함
peak_loc = subset_highs.index.get_loc(peak_idx)
if peak_loc > 0:
    peak_close = subset_closes.iloc[peak_loc]
    prev_close = subset_closes.iloc[peak_loc - 1]
    prev_highs = subset_highs.iloc[:peak_loc - 1]
    max_prev_high = prev_highs.max()
    
    if peak_close <= max_prev_high and prev_close <= max_prev_high:
        return -1
```

### 2.2 타임프레임별 파라미터

| 타임프레임 | recent_window | total_window |
|-----------|---------------|--------------|
| 주간 (1w)  | 5 캔들        | 52 캔들      |
| 일간 (1d)  | 7 캔들        | 200 캔들     |

## 3. 베어리시 패턴 확인 (핵심 구현)

### 3.1 베어리시 패턴 판정의 완전한 구현

```python
def check_bearish_pattern(df: pd.DataFrame, window=7, start_idx: Optional[int] = None, buffer=0.1) -> str:
    """
    고점 이후 최대 7개 캔들의 베어리시 패턴을 정확히 카운팅
    """
    # 1단계: 검사할 캔들 범위 추출
    pos = None
    if start_idx is not None:
        try:
            pos = df.index.get_loc(start_idx)  # 고점 다음 캔들 위치
            sub = df.iloc[pos : pos + window]   # 고점 이후 7개 캔들
        except KeyError:
            sub = df.tail(window)
    else:
        sub = df.tail(window)
    
    if len(sub) == 0:
        return "none"
    
    # 2단계: 각 캔들을 "bullish" 또는 "bearish"로 분류
    statuses = []
    
    for i in range(len(sub)):
        # 첫 번째 캔들 처리 (고점 직후 캔들)
        if i == 0:
            if pos is not None and pos > 0:
                prev_candle = df.iloc[pos - 1]  # 고점 캔들
                this_candle = sub.iloc[i]       # 고점 다음 캔들
                
                # 세 가지 조건 중 하나라도 만족하면 bullish
                if this_candle["high"] > prev_candle["high"]:
                    # 조건 1: 이전 고가를 갱신
                    statuses.append("bullish")
                elif this_candle["close"] > this_candle["open"]:
                    # 조건 2: 양봉 (종가 > 시가)
                    statuses.append("bullish")
                elif this_candle["high"] > (1 + buffer) * this_candle["open"]:
                    # 조건 3: 긴 위꼬리 (고가가 시가보다 buffer% 이상 높음)
                    statuses.append("bullish")
                else:
                    # 모든 조건 불만족 = bearish
                    statuses.append("bearish")
            else:
                statuses.append("bearish")
        
        # 두 번째 이후 캔들들
        else:
            curr = sub.iloc[i]      # 현재 캔들
            prev = sub.iloc[i - 1]  # 직전 캔들
            
            # 동일한 세 가지 조건 체크
            if curr["high"] > prev["high"]:
                statuses.append("bullish")
            elif curr["close"] > curr["open"]:
                statuses.append("bullish")  
            elif curr["high"] > (1 + buffer) * curr["open"]:
                statuses.append("bullish")
            else:
                statuses.append("bearish")
    
    # 3단계: bearish 캔들 카운팅 및 패턴 결정
    n_bearish = sum(s == "bearish" for s in statuses)
    total_count = len(statuses)
    
    # 핵심 로직: 정확한 개수로 패턴 분류
    if n_bearish == total_count:
        # 7개 모두 bearish (예: bearish 7개, bullish 0개)
        return "all"
    elif n_bearish == (total_count - 1):
        # 정확히 1개만 bullish, 나머지는 bearish (예: bearish 6개, bullish 1개)
        return "all_but_one"
    else:
        # 2개 이상이 bullish (예: bearish 5개 이하)
        return "none"
```

### 3.2 베어리시 캔들 판정 조건 상세 분석

#### 3.2.1 Bullish 판정 조건 (OR 연산)

```python
# 캔들이 Bullish로 분류되는 3가지 경우:

# 조건 1: 고가 갱신
if this_candle["high"] > prev_candle["high"]:
    status = "bullish"
    # 예: 이전 고가 100, 현재 고가 101 → bullish

# 조건 2: 양봉
elif this_candle["close"] > this_candle["open"]:
    status = "bullish"
    # 예: 시가 100, 종가 102 → bullish (초록 캔들)

# 조건 3: 긴 위꼬리 (buffer 적용)
elif this_candle["high"] > (1 + buffer) * this_candle["open"]:
    status = "bullish"
    # 일간 차트 예 (buffer=0.1):
    # 시가 100, 고가 111 → 111 > 110 → bullish
    # 시가 100, 고가 109 → 109 < 110 → 이 조건은 불만족
    
    # 주간 차트 예 (buffer=0.2):
    # 시가 100, 고가 121 → 121 > 120 → bullish
    # 시가 100, 고가 119 → 119 < 120 → 이 조건은 불만족
```

#### 3.2.2 Bearish 판정 (모든 조건 불만족)

```python
# 위 3가지 조건을 모두 만족하지 않으면 bearish
else:
    status = "bearish"
    
# Bearish 캔들의 특징:
# - 이전 고가를 갱신하지 못함
# - 음봉 (종가 ≤ 시가)
# - 위꼬리가 짧음 (고가가 시가의 buffer% 이내)
```

### 3.3 패턴 분류와 EMA 선택의 하드코딩 구현

```python
def determine_ema_period_from_pattern(pattern: str) -> int:
    """
    베어리시 패턴 결과에 따른 EMA 기간 선택 (하드코딩)
    """
    if pattern == "all":
        # 7개 캔들 모두 bearish = 강한 하락 신호
        # → 빠른 반응을 위해 짧은 EMA 15 사용
        return 15
    
    elif pattern == "all_but_one":
        # 6개 bearish + 1개 bullish = 중간 하락 신호
        # → 노이즈 필터링을 위해 긴 EMA 33 사용
        return 33
    
    else:  # pattern == "none"
        # 2개 이상 bullish = 하락 신호 아님
        # → 시그널 없음
        return None
```

### 3.4 실제 적용 예시

#### 예시 1: "all" 패턴 (7개 모두 bearish)
```python
# 고점 이후 7개 캔들 데이터
candles = [
    {"open": 100, "high": 99,  "low": 95,  "close": 96},   # bearish
    {"open": 96,  "high": 97,  "low": 94,  "close": 95},   # bearish
    {"open": 95,  "high": 96,  "low": 93,  "close": 94},   # bearish
    {"open": 94,  "high": 95,  "low": 92,  "close": 93},   # bearish
    {"open": 93,  "high": 94,  "low": 91,  "close": 92},   # bearish
    {"open": 92,  "high": 93,  "low": 90,  "close": 91},   # bearish
    {"open": 91,  "high": 92,  "low": 89,  "close": 90}    # bearish
]

# 결과: n_bearish = 7, total_count = 7
# 7 == 7 → return "all" → EMA 15 사용
```

#### 예시 2: "all_but_one" 패턴 (6개 bearish + 1개 bullish)
```python
# 고점 이후 7개 캔들 데이터
candles = [
    {"open": 100, "high": 99,  "low": 95,  "close": 96},   # bearish
    {"open": 96,  "high": 97,  "low": 94,  "close": 95},   # bearish
    {"open": 95,  "high": 96,  "low": 93,  "close": 97},   # bullish (양봉)
    {"open": 97,  "high": 97,  "low": 92,  "close": 93},   # bearish
    {"open": 93,  "high": 94,  "low": 91,  "close": 92},   # bearish
    {"open": 92,  "high": 93,  "low": 90,  "close": 91},   # bearish
    {"open": 91,  "high": 92,  "low": 89,  "close": 90}    # bearish
]

# 결과: n_bearish = 6, total_count = 7
# 6 == (7 - 1) → return "all_but_one" → EMA 33 사용
```

#### 예시 3: "none" 패턴 (5개 이하 bearish)
```python
# 고점 이후 7개 캔들 데이터
candles = [
    {"open": 100, "high": 102, "low": 95,  "close": 101},  # bullish (양봉)
    {"open": 101, "high": 103, "low": 100, "close": 102},  # bullish (고가갱신)
    {"open": 102, "high": 102, "low": 98,  "close": 99},   # bearish
    {"open": 99,  "high": 100, "low": 97,  "close": 98},   # bearish
    {"open": 98,  "high": 99,  "low": 96,  "close": 97},   # bearish
    {"open": 97,  "high": 98,  "low": 95,  "close": 96},   # bearish
    {"open": 96,  "high": 97,  "low": 94,  "close": 95}    # bearish
]

# 결과: n_bearish = 5, total_count = 7
# 5 != 7 이고 5 != 6 → return "none" → 시그널 없음
```

### 3.5 버퍼(buffer)의 역할

```python
# buffer는 "긴 위꼬리" 판정 기준을 결정

# 일간 차트 (buffer = 0.1 = 10%)
if curr["high"] > 1.1 * curr["open"]:
    # 고가가 시가보다 10% 이상 높으면 bullish
    # 위로 크게 시도했다가 떨어진 캔들 = 매수 압력 존재
    
# 주간 차트 (buffer = 0.2 = 20%)  
if curr["high"] > 1.2 * curr["open"]:
    # 고가가 시가보다 20% 이상 높으면 bullish
    # 주간은 변동성이 크므로 더 큰 버퍼 필요
```

## 4. 진입 조건 확인

### 4.1 EMA 아래 저가 확인

```python
def is_low_under_ema(df: pd.DataFrame, period: int) -> bool:
    """
    현재 캔들의 저가가 EMA 아래에 있는지 확인
    
    매개변수:
    - df: 캔들 데이터
    - period: EMA 기간 (15 또는 33)
    
    조건:
    - 마지막 캔들의 저가 < EMA(period)
    
    반환값:
    - True: 저가가 EMA 아래
    - False: 저가가 EMA 이상
    """
    ema_series = compute_ema_series(df["close"], period)
    last_idx = len(df) - 1
    curr_low = df["low"].iloc[last_idx]
    curr_ema = ema_series.iloc[last_idx]
    return curr_low < curr_ema
```

### 4.2 EMA 기간 선택 로직

```python
# 베어리시 패턴에 따른 EMA 선택
if pattern == "all":
    use_period = 15  # 모든 캔들이 베어리시 → EMA 15 사용
elif pattern == "all_but_one":
    use_period = 33  # 한 개 제외 베어리시 → EMA 33 사용
```

## 5. 최종 시그널 생성

### 5.1 전체 의사결정 프로세스

```python
def kwon_strategy_decision(df: pd.DataFrame, interval: str,
                          tp_ratio: float = 0.1, sl_ratio: float = 0.05) -> dict:
    """
    최종 매수 시그널 생성
    
    프로세스:
    1. check_upper_section() 호출
       - 단일 고점 확인
       - 베어리시 패턴 확인
       - EMA 아래 저가 확인
       - 조건 만족시 "INITIAL_YES_15" 또는 "INITIAL_YES_33" 반환
    
    2. generate_trade_signal() 호출
       - INITIAL_YES 시그널을 받으면 거래 파라미터 계산
       - entry_price = 해당 EMA 값
       - tp_price = entry_price * (1 + tp_ratio)
       - sl_price = entry_price * (1 - sl_ratio)
    
    반환값:
    {
        'signal': 'BUY' 또는 'NO',
        'decision': 'YES_15', 'YES_33' 또는 'NO',
        'entry_price': EMA 값 (매수 시그널시),
        'tp_price': 목표가 (매수 시그널시),
        'sl_price': 손절가 (매수 시그널시),
        'ema_period': 15 또는 33 (매수 시그널시)
    }
    """
```

### 5.2 시그널 플로우차트

```
┌─────────────────┐
│  캔들 데이터 입력  │
└────────┬────────┘
         ▼
┌─────────────────┐
│  단일 고점 확인   │
│  (check_single_peak) │
└────────┬────────┘
         ▼
    ◆ 고점 존재? ◆──NO──→ [시그널: NO]
         │
        YES
         ▼
┌─────────────────┐
│ 베어리시 패턴 확인 │
│ (고점 이후 7개 캔들) │
└────────┬────────┘
         ▼
    ◆ 패턴 타입? ◆
         │
    ┌────┴────┬──────┐
    │         │      │
   all    all_but_one none
    │         │      │
    ▼         ▼      ▼
  EMA15    EMA33   [시그널: NO]
    │         │
    └────┬────┘
         ▼
┌─────────────────┐
│ 저가 < EMA 확인  │
└────────┬────────┘
         ▼
    ◆ 조건 만족? ◆──NO──→ [시그널: NO]
         │
        YES
         ▼
┌─────────────────┐
│   거래 파라미터    │
│      계산         │
│ • Entry = EMA 값  │
│ • TP = Entry×1.1  │
│ • SL = Entry×0.95 │
└────────┬────────┘
         ▼
   [시그널: BUY]
```

## 6. 타임프레임별 상세 설정

### 6.1 주간 차트 (1w)

| 파라미터 | 값 | 설명 |
|---------|-----|------|
| recent_window | 5 | 최근 5주 내 고점 |
| total_window | 52 | 52주(1년) 범위 검색 |
| buffer | 0.2 | 20% 상승 버퍼 |
| 최소 캔들 수 | 35 | 분석에 필요한 최소 데이터 |

### 6.2 일간 차트 (1d)

| 파라미터 | 값 | 설명 |
|---------|-----|------|
| recent_window | 7 | 최근 7일 내 고점 |
| total_window | 200 | 200일 범위 검색 |
| buffer | 0.1 | 10% 상승 버퍼 |
| 최소 캔들 수 | 35 | 분석에 필요한 최소 데이터 |

## 7. 시그널 예시

### 7.1 YES_15 시그널 (강한 베어리시)

```
조건:
1. 200일 내 최고점이 최근 7일 내에 형성
2. 고점이 15-EMA보다 20% 이상 높음
3. 고점 이후 7개 캔들이 모두 베어리시
4. 현재 저가가 15-EMA 아래

결과:
- signal: 'BUY'
- decision: 'YES_15'
- entry_price: 15-EMA 값
- tp_price: entry_price × 1.1
- sl_price: entry_price × 0.95
```

### 7.2 YES_33 시그널 (중간 베어리시)

```
조건:
1. 200일 내 최고점이 최근 7일 내에 형성
2. 고점이 15-EMA보다 20% 이상 높음
3. 고점 이후 7개 캔들 중 6개가 베어리시
4. 현재 저가가 33-EMA 아래

결과:
- signal: 'BUY'
- decision: 'YES_33'
- entry_price: 33-EMA 값
- tp_price: entry_price × 1.1
- sl_price: entry_price × 0.95
```

## 8. 구현 시 주의사항

### 8.1 데이터 요구사항
- 최소 35개 이상의 캔들 데이터 필요
- EMA 계산을 위한 충분한 히스토리 데이터
- 정확한 OHLC(시가, 고가, 저가, 종가) 및 타임스탬프

### 8.2 예외 처리
```python
# 데이터 부족 처리
if len(df) < 35:
    return {'signal': 'NO'}

# EMA 계산 불가 처리
if ema_value is None or pd.isna(ema_value):
    return -1

# 빈 데이터프레임 처리
if df.empty:
    return "NO DATA"
```

### 8.3 성능 최적화
- EMA는 한 번만 계산하여 재사용
- 필요한 범위만 슬라이싱하여 메모리 효율성 확보
- 조건 검사 순서 최적화 (빠른 실패 원칙)

## 9. 백테스팅 고려사항

### 9.1 실제 진입가 계산
```python
# 시그널 발생 시 EMA 값을 초기 진입가로 사용
initial_entry = ema_value

# 실제 거래에서는 다음 캔들 시가 또는 
# 지정가 주문으로 진입 가능
actual_entry = min(next_candle_open, initial_entry)
```

### 9.2 슬리피지 및 수수료
- 실제 거래 시 슬리피지 고려 필요
- 거래 수수료를 TP/SL 계산에 반영

### 9.3 리스크 관리
- 포지션 크기 관리
- 최대 손실 한도 설정
- 동시 포지션 수 제한

## 10. 전략 특징 요약

### 10.1 장점
- 명확한 패턴 기반 진입
- 두 가지 EMA 사용으로 유연성 확보
- 고점 이후 조정 구간 포착
- 리스크/리워드 비율 사전 정의 (1:2)

### 10.2 단점
- 레인지 장세에서 가짜 시그널 가능성
- 급락 시장에서 늦은 진입
- 단일 타임프레임 의존

### 10.3 개선 가능 영역
- 볼륨 지표 추가 검증
- 멀티 타임프레임 확인
- 동적 TP/SL 조정
- 시장 상황별 파라미터 최적화