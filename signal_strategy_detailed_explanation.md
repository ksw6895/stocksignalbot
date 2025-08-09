# 시그널 포착 전략 상세 설명

## 개요
이 시스템은 NASDAQ 주식 시장에서 Kwon Strategy를 활용하여 매수 시그널을 포착하는 자동화된 트레이딩 봇입니다. 주간(Weekly) 캔들스틱 데이터를 기반으로 특정 패턴을 식별하고, 기술적 지표를 활용하여 진입 시점을 결정합니다.

## 1. 전체 작동 프로세스

### 1.1 시스템 초기화 및 스케줄링
```
StockSignalBot 시작
    ↓
환경 변수 검증 (API 키, 텔레그램 설정)
    ↓
초기 스캔 실행
    ↓
매 시간마다 스캔 스케줄링 (기본: 3600초)
    ↓
매일 16:30 일일 요약 보고서 전송
```

### 1.2 스캔 프로세스 흐름
1. **시장 상태 확인**: 거래 시간 여부 체크 (선택적)
2. **주식 필터링**: FMP API를 통해 NASDAQ 주식 목록 획득
3. **배치 처리**: 20개씩 묶어서 메모리 효율적 처리
4. **패턴 분석**: 각 주식에 대해 Kwon Strategy 적용
5. **시그널 검증**: 유효한 시그널 필터링
6. **알림 전송**: 텔레그램으로 매수 시그널 전송

## 2. 주식 필터링 메커니즘

### 2.1 시가총액 필터링
```python
MIN_MARKET_CAP = 500,000,000    # 5억 달러
MAX_MARKET_CAP = 50,000,000,000 # 500억 달러
```
- **목적**: 극소형주와 초대형주를 제외하여 적절한 유동성과 변동성을 가진 종목 선별
- **구현**: FMP API의 스크리너 기능을 통해 NASDAQ 상장 주식 중 시가총액 범위 내 종목만 추출

### 2.2 추가 검증 조건
```python
def _validate_stock(self, stock: Dict) -> bool:
    # 가격 범위: $1 ~ $10,000
    if price < MIN_PRICE or price > MAX_PRICE:
        return False
    
    # 최소 거래량: 100,000주
    if volume < MIN_VOLUME:
        return False
    
    # 시가총액 재확인
    if market_cap < MIN_MARKET_CAP or market_cap > MAX_MARKET_CAP:
        return False
```

### 2.3 캐싱 전략
- **캐시 유효 시간**: 1시간
- **목적**: API 호출 횟수 최소화 (일일 한도: 250/750회)
- **구현**: 주식 목록을 메모리에 캐싱하여 반복 호출 방지

## 3. Kwon Strategy 핵심 로직

### 3.1 단일 피크(Single Peak) 패턴 식별

#### 피크 탐지 알고리즘
```python
def _find_single_peak(self, candles: List[Dict]) -> Optional[Tuple[int, float]]:
    # 최근 10개 캔들에서 피크 찾기
    peaks = []
    for i in range(1, len(candles) - 1):
        if candles[i]['high'] > candles[i-1]['high'] and 
           candles[i]['high'] > candles[i+1]['high']:
            peaks.append((i, candles[i]['high']))
    
    # 단일 피크만 유효
    if len(peaks) != 1:
        return None
```

#### 피크 유효성 검증
1. **위치 조건**: 피크가 2~7번째 캔들 사이에 위치
   - 너무 최근(1번째): 패턴 형성 미완료
   - 너무 오래됨(8번째 이후): 시그널 강도 약화

2. **상대적 높이**: 피크가 전체 기간 최고가의 95% 이상
   ```python
   if peak_price < max_high * 0.95:
       return None
   ```

### 3.2 베어리시 패턴 확인

#### 피크 이후 하락 패턴 분석
```python
def _check_bearish_after_peak(self, candles: List[Dict], peak_index: int) -> bool:
    after_peak = candles[peak_index + 1:]
    bearish_count = 0
    
    for candle in after_peak:
        # 음봉 카운트
        if candle['close'] < candle['open']:
            bearish_count += 1
        
        # 위꼬리가 긴 음봉 (매도 압력 신호)
        body = abs(candle['close'] - candle['open'])
        upper_wick = candle['high'] - max(candle['close'], candle['open'])
        if upper_wick > body * 1.5 and candle['close'] < candle['open']:
            bearish_count += 0.5
    
    # 50% 이상이 베어리시 패턴이어야 함
    return bearish_count >= len(after_peak) * 0.5
```

### 3.3 EMA 기반 진입점 결정

#### EMA 계산 및 적용
```python
# EMA 20 (단기) 및 EMA 50 (장기) 계산
ema_short = calculate_ema(close_prices, 20)
ema_long = calculate_ema(close_prices, 50)

# 현재 저가가 EMA보다 낮은지 확인
buy_condition_short = current_low < current_ema_short
buy_condition_long = current_low < current_ema_long

# 진입 가격 = EMA 레벨
entry_price = current_ema_short if buy_condition_short else current_ema_long
```

#### EMA 진입 로직의 의미
- **저가 < EMA**: 일시적 과매도 상태
- **EMA 레벨 진입**: 평균 회귀 전략
- **우선순위**: EMA 20 > EMA 50 (단기 지표 우선)

## 4. 시그널 강도 평가 시스템

### 4.1 강도 점수 계산 요소

#### 1) 풀백(Pullback) 정도
```python
pullback_pct = abs((current_price - peak_price) / peak_price)
if 0.15 <= pullback_pct <= 0.30:  # 15-30% 하락
    strength_score += 2  # 이상적인 풀백
elif 0.10 <= pullback_pct < 0.15:  # 10-15% 하락
    strength_score += 1  # 적절한 풀백
```

#### 2) 거래량 비율
```python
volume_ratio = current_volume / average_volume_20
if volume_ratio > 1.5:  # 평균 대비 150% 이상
    strength_score += 2  # 강한 관심
elif volume_ratio > 1.0:  # 평균 이상
    strength_score += 1  # 정상적 관심
```

#### 3) 변동성 평가
```python
recent_volatility = _calculate_volatility(candles[-20:])
if recent_volatility < 0.03:  # 3% 미만
    strength_score += 1  # 안정적 패턴
```

#### 4) RSI (상대강도지수)
```python
rsi = _calculate_rsi(candles[-14:])
if rsi < 40:  # 과매도 구간
    strength_score += 2
elif rsi < 50:  # 약세 구간
    strength_score += 1
```

### 4.2 시그널 강도 분류
```python
if strength_score >= 5:
    return "STRONG"    # 매우 강한 시그널
elif strength_score >= 3:
    return "MODERATE"  # 보통 시그널
else:
    return "WEAK"      # 약한 시그널
```

## 5. 리스크 관리

### 5.1 손익 비율 설정
```python
TP_RATIO = 0.07  # Take Profit: +7%
SL_RATIO = 0.03  # Stop Loss: -3%

tp_price = entry_price * (1 + TP_RATIO)
sl_price = entry_price * (1 - SL_RATIO)
risk_reward = (tp_price - entry_price) / (entry_price - sl_price)
```

### 5.2 시그널 검증 기준
```python
def validate_signal(self, signal: Dict) -> bool:
    # 리스크/리워드 비율 최소 1.5:1
    if signal['risk_reward'] < 1.5:
        return False
    
    # 약한 시그널 제외
    if signal['signal_strength'] == "WEAK":
        return False
    
    # 거래량 최소 요구사항
    if signal['volume_ratio'] < 0.5:
        return False
```

## 6. 시그널 생성 프로세스 상세

### 6.1 데이터 수집
1. **주간 캔들 데이터**: 최근 52주 (1년) 데이터 수집
2. **실시간 가격**: 현재 가격 및 거래량 정보
3. **기업 정보**: 시가총액, 섹터, 산업 정보

### 6.2 패턴 매칭 순서
```
1. 데이터 충분성 확인 (최소 50개 캔들)
    ↓
2. EMA 20, 50 계산
    ↓
3. 최근 10개 캔들에서 단일 피크 탐색
    ↓
4. 피크 위치 및 높이 검증
    ↓
5. 피크 이후 베어리시 패턴 확인
    ↓
6. 현재 저가와 EMA 비교
    ↓
7. 진입점, TP, SL 계산
    ↓
8. 시그널 강도 평가
    ↓
9. 최종 검증 및 필터링
```

### 6.3 시그널 생성 조건 요약
모든 다음 조건을 만족해야 시그널 생성:
1. ✅ 최근 10주 내 단일 피크 존재
2. ✅ 피크가 2-7주 전 위치
3. ✅ 피크가 최고가의 95% 이상
4. ✅ 피크 이후 50% 이상 베어리시 캔들
5. ✅ 현재 저가 < EMA (20 또는 50)
6. ✅ 리스크/리워드 비율 ≥ 1.5
7. ✅ 시그널 강도 ≠ "WEAK"
8. ✅ 거래량 비율 ≥ 0.5

## 7. 메모리 및 성능 최적화

### 7.1 배치 처리
```python
def process_stocks_in_batches(stocks, process_func, batch_size=20):
    for i in range(0, len(stocks), batch_size):
        batch = stocks[i:i+batch_size]
        # 배치 처리 후 가비지 컬렉션
        gc.collect()
```

### 7.2 API 호출 최적화
- **LRU 캐싱**: 자주 조회되는 데이터 캐싱
- **일일 한도 관리**: 250/750회 제한 추적
- **스마트 캐싱**: 1시간 유효 기간의 주식 목록 캐싱

### 7.3 중복 시그널 방지
```python
# 날짜별 시그널 키 생성
signal_key = f"{symbol}_{datetime.now().date().isoformat()}"

# 이미 전송된 시그널 체크
if signal_key in self.signals_sent:
    return
```

## 8. 실시간 모니터링 및 알림

### 8.1 텔레그램 메시지 포맷
```
🎯 STOCK BUY SIGNAL

Symbol: AAPL
Company: Apple Inc.
Sector: Technology
Market Cap: $2.5T

📊 Signal Details:
• Current Price: $175.50
• Entry Price: $178.20
• Take Profit: $190.67 (+7.0%)
• Stop Loss: $172.85 (-3.0%)

📈 Technical Analysis:
• Peak Price: $195.00 (3 weeks ago)
• Pullback: -10.0%
• EMA20: $178.20
• Volume Ratio: 1.8x avg
• Signal Strength: STRONG
• Risk/Reward: 2.3:1
```

### 8.2 일일 요약 보고서
매일 16:30 (시장 종료 후) 자동 전송:
- 가동 시간
- 총 스캔 횟수
- 발견된 시그널 수
- 모니터링 중인 주식 수
- 남은 API 호출 횟수
- 시장 상태 정보

## 9. 전략의 핵심 원리

### 9.1 평균 회귀 (Mean Reversion)
- 주가는 장기적으로 평균(EMA)으로 회귀하는 경향
- 과매도 상태에서 평균으로의 복귀를 노림

### 9.2 모멘텀 전환
- 단일 피크 후 하락 = 상승 모멘텀 소진
- 베어리시 패턴 = 매도 압력 확인
- EMA 하방 돌파 = 일시적 과매도

### 9.3 리스크 관리
- 명확한 진입/청산 기준
- 사전 정의된 손절/익절 레벨
- 리스크/리워드 비율 검증

## 10. 시스템 한계 및 주의사항

### 10.1 한계점
1. **주간 데이터 기반**: 단기 변동성 미반영
2. **과거 데이터 의존**: 미래 예측 불확실
3. **단일 전략**: 다양한 시장 상황 대응 제한
4. **API 제한**: 일일 호출 횟수 한도

### 10.2 주의사항
1. **백테스팅 필요**: 실제 투자 전 과거 데이터 검증
2. **시장 상황 고려**: 전체 시장 트렌드 확인
3. **분산 투자**: 단일 시그널에 과도한 의존 금지
4. **지속적 모니터링**: 시스템 성능 추적 및 조정

## 결론

이 시스템은 Kwon Strategy를 기반으로 한 체계적이고 자동화된 매수 시그널 포착 시스템입니다. 단일 피크 패턴, 베어리시 확인, EMA 기반 진입이라는 세 가지 핵심 요소를 결합하여 높은 확률의 매수 기회를 식별합니다. 

강력한 리스크 관리와 시그널 검증 메커니즘을 통해 잘못된 시그널을 필터링하고, 실시간 텔레그램 알림으로 즉각적인 대응이 가능합니다. 다만, 모든 자동화 트레이딩 시스템과 마찬가지로 시장 상황에 따른 성과 변동성이 있으므로 지속적인 모니터링과 조정이 필요합니다.