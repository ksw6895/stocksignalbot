# 아키텍처 문서

## 시스템 개요

NASDAQ 주식 시그널 봇은 Kwon Strategy(Upper Section Strategy)를 사용하여 주식 시장을 모니터링하고 매수 신호를 실시간으로 감지하는 자동화된 거래 신호 시스템입니다. 이 시스템은 주간 캔들스틱 데이터를 분석하여 특정 패턴을 식별하고, 텔레그램을 통해 트레이더에게 즉시 알림을 전송합니다.

### 주요 특징
- **자동화된 시장 스캐닝**: 24/7 NASDAQ 주식 모니터링
- **시가총액 필터링**: 5억~500억 달러 범위의 주식 선별
- **Upper Section 전략**: 단일 피크 + 하락 패턴 + EMA 진입점 식별
- **실시간 알림**: 텔레그램 봇을 통한 즉각적인 신호 전송
- **메모리 최적화**: Render 스타터 플랜(512MB RAM)에 최적화
- **API 관리**: FMP API 요청 제한 관리 및 스마트 캐싱

## 시스템 아키텍처

### 전체 아키텍처 다이어그램

```mermaid
graph TB
    subgraph "외부 API"
        FMP[FMP API<br/>주식 데이터]
        TG[Telegram API<br/>알림 전송]
    end
    
    subgraph "핵심 봇 시스템"
        MAIN[stock_signal_bot.py<br/>메인 오케스트레이터]
        STOCKS[stocks.py<br/>데이터 수집]
        DECISION[decision.py<br/>전략 분석]
        INDICATORS[indicators.py<br/>기술 지표]
        CONFIG[config.py<br/>설정 관리]
        FMP_CLIENT[fmp_api.py<br/>API 클라이언트]
    end
    
    subgraph "배포 환경"
        RENDER[render_web_wrapper.py<br/>헬스체크 서버]
        ENV[환경 변수<br/>.env 설정]
    end
    
    subgraph "데이터 저장"
        CACHE[LRU 캐시<br/>메모리 내]
        SIGNALS[signals_sent.json<br/>신호 이력]
    end
    
    FMP --> FMP_CLIENT
    FMP_CLIENT --> STOCKS
    STOCKS --> MAIN
    MAIN --> DECISION
    DECISION --> INDICATORS
    MAIN --> TG
    CONFIG --> MAIN
    ENV --> CONFIG
    MAIN --> CACHE
    MAIN --> SIGNALS
    RENDER --> MAIN
    
    style MAIN fill:#f9f,stroke:#333,stroke-width:4px
    style FMP fill:#bbf,stroke:#333,stroke-width:2px
    style TG fill:#bbf,stroke:#333,stroke-width:2px
```

### 컴포넌트 관계도

```mermaid
classDiagram
    class StockSignalBot {
        +bot_token: str
        +chat_id: str
        +data_fetcher: StockDataFetcher
        +strategy: UpperSectionStrategy
        +signals_sent: set
        +scan_interval: int
        +run()
        +scan_for_signals()
        +send_telegram_message()
        +process_signal()
        +handle_command()
    }
    
    class StockDataFetcher {
        +fmp_client: FMPAPIClient
        +min_market_cap: int
        +max_market_cap: int
        +get_nasdaq_stocks()
        +fetch_weekly_candles()
        +get_company_profile()
        +process_stocks_in_batches()
    }
    
    class FMPAPIClient {
        +api_key: str
        +daily_limit: int
        +cache: dict
        +request_count: int
        +get_nasdaq_stocks()
        +get_historical_weekly()
        +get_company_profile()
        +get_quote()
        -_make_request()
        -_convert_to_weekly()
    }
    
    class UpperSectionStrategy {
        +tp_ratio: float
        +sl_ratio: float
        +analyze()
        -_check_single_peak()
        -_check_bearish_pattern()
        -_is_low_under_ema()
        -_generate_trade_signal()
    }
    
    class IndicatorModule {
        +compute_ema_series()
        +calculate_ema()
    }
    
    StockSignalBot --> StockDataFetcher
    StockSignalBot --> UpperSectionStrategy
    StockDataFetcher --> FMPAPIClient
    UpperSectionStrategy --> IndicatorModule
```

## 데이터 플로우

### 신호 생성 프로세스

```mermaid
sequenceDiagram
    participant Bot as StockSignalBot
    participant Fetcher as StockDataFetcher
    participant FMP as FMP API
    participant Strategy as UpperSectionStrategy
    participant Telegram as Telegram API
    
    Bot->>Bot: 스케줄된 스캔 시작
    Bot->>Fetcher: get_nasdaq_stocks()
    Fetcher->>FMP: 주식 스크리너 API 호출
    FMP-->>Fetcher: NASDAQ 주식 목록
    Fetcher->>Fetcher: 시가총액/볼륨 필터링
    Fetcher-->>Bot: 필터링된 주식 목록
    
    loop 각 주식에 대해
        Bot->>Fetcher: fetch_weekly_candles(symbol)
        Fetcher->>FMP: 주간 히스토리컬 데이터
        FMP-->>Fetcher: OHLC 캔들 데이터
        Fetcher-->>Bot: 주간 캔들 데이터
        
        Bot->>Strategy: analyze(candles, symbol)
        Strategy->>Strategy: _check_single_peak()
        Strategy->>Strategy: _check_bearish_pattern()
        Strategy->>Strategy: _is_low_under_ema()
        
        alt 신호 조건 충족
            Strategy->>Strategy: _generate_trade_signal()
            Strategy-->>Bot: 신호 딕셔너리
            Bot->>Telegram: send_telegram_message()
            Telegram-->>Bot: 전송 확인
            Bot->>Bot: 신호 이력 저장
        else 조건 미충족
            Strategy-->>Bot: None
        end
    end
    
    Bot->>Telegram: 스캔 요약 보고서 전송
```

### Upper Section 전략 플로우

```mermaid
flowchart TD
    START[시작: 주간 캔들 데이터] --> CHECK_DATA{데이터 충분?<br/>35개 이상}
    CHECK_DATA -->|아니오| NO_SIGNAL[신호 없음]
    CHECK_DATA -->|예| FIND_PEAK[단일 피크 찾기]
    
    FIND_PEAK --> PEAK_COND{피크 조건 충족?<br/>- 최근 5주 내<br/>- EMA15의 1.2배 이상<br/>- 돌파 확인}
    PEAK_COND -->|아니오| NO_SIGNAL
    PEAK_COND -->|예| CHECK_BEARISH[피크 이후 패턴 확인]
    
    CHECK_BEARISH --> BEARISH_TYPE{하락 패턴 유형}
    BEARISH_TYPE -->|모두 하락| EMA15[EMA 15 사용]
    BEARISH_TYPE -->|1개 제외 하락| EMA33[EMA 33 사용]
    BEARISH_TYPE -->|기타| NO_SIGNAL
    
    EMA15 --> CHECK_LOW15{현재 저가 < EMA15?}
    EMA33 --> CHECK_LOW33{현재 저가 < EMA33?}
    
    CHECK_LOW15 -->|예| GEN_SIGNAL15[신호 생성<br/>진입: EMA15]
    CHECK_LOW15 -->|아니오| NO_SIGNAL
    CHECK_LOW33 -->|예| GEN_SIGNAL33[신호 생성<br/>진입: EMA33]
    CHECK_LOW33 -->|아니오| NO_SIGNAL
    
    GEN_SIGNAL15 --> CALC_LEVELS[TP/SL 계산<br/>TP: +10%<br/>SL: -5%]
    GEN_SIGNAL33 --> CALC_LEVELS
    
    CALC_LEVELS --> SEND_SIGNAL[텔레그램 신호 전송]
    
    style START fill:#e1f5fe
    style SEND_SIGNAL fill:#c8e6c9
    style NO_SIGNAL fill:#ffccbc
```

## 핵심 컴포넌트 상세

### 1. StockSignalBot (stock_signal_bot.py)
**주요 책임:**
- 전체 시스템 오케스트레이션
- 스캔 스케줄링 및 실행
- 텔레그램 명령어 처리
- 신호 이력 관리
- 에러 처리 및 복구

**주요 기능:**
- `scan_for_signals()`: 주식 스캔 및 신호 감지
- `send_telegram_message()`: 알림 전송
- `handle_command()`: 사용자 명령 처리
- `process_stocks_in_batches()`: 배치 처리로 메모리 최적화

### 2. StockDataFetcher (stocks.py)
**주요 책임:**
- FMP API와의 통신 관리
- 주식 데이터 수집 및 필터링
- 배치 처리 최적화
- 캐싱 전략 구현

**주요 기능:**
- `get_nasdaq_stocks()`: NASDAQ 주식 목록 조회
- `fetch_weekly_candles()`: 주간 캔들 데이터 수집
- `_validate_stock()`: 주식 유효성 검증
- `process_stocks_in_batches()`: 메모리 효율적 배치 처리

### 3. UpperSectionStrategy (decision.py)
**주요 책임:**
- Kwon Strategy 구현
- 패턴 인식 및 분석
- 거래 신호 생성
- 리스크 관리 계산

**전략 단계:**
1. **단일 피크 확인**: 최근 5주 내 단일 최고점
2. **하락 패턴 분석**: 피크 이후 7개 캔들의 패턴
3. **EMA 위치 확인**: 현재 저가가 EMA 아래인지 확인
4. **신호 생성**: 진입가, TP, SL 계산

### 4. FMPAPIClient (fmp_api.py)
**주요 책임:**
- FMP API 요청 관리
- 지수 백오프를 통한 재시도 로직
- LRU 캐싱 구현
- 요청 제한 추적

**주요 기능:**
- `_make_request()`: API 요청 핵심 로직
- `_convert_to_weekly()`: 일간 데이터를 주간으로 변환
- `get_remaining_requests()`: API 할당량 추적

## 외부 통합

### FMP (Financial Modeling Prep) API
```
용도: 주식 시장 데이터 제공
엔드포인트:
- /v3/stock-screener: 주식 스크리닝
- /v3/historical-price-full: 과거 가격 데이터
- /v3/profile: 기업 프로필
- /v3/quote: 실시간 시세
- /v3/is-the-market-open: 시장 상태

요청 제한:
- 무료: 250 요청/일
- 스타터: 750 요청/일
```

### Telegram Bot API
```
용도: 실시간 알림 전송
기능:
- 신호 알림 전송
- 명령어 처리 (/start, /help, /status, /scan 등)
- 스캔 보고서 전송
- 양방향 통신 지원
```

## 배포 아키텍처

### Render 플랫폼 배포

```mermaid
graph LR
    subgraph "Render Cloud"
        subgraph "Worker Service"
            BOT[Stock Signal Bot<br/>Python 3.11]
            HEALTH[Health Check<br/>Flask Server]
        end
        
        ENV_VARS[환경 변수<br/>보안 저장소]
    end
    
    subgraph "외부 서비스"
        FMP_SVC[FMP API]
        TG_SVC[Telegram]
    end
    
    GIT[GitHub<br/>자동 배포] --> BOT
    ENV_VARS --> BOT
    BOT <--> FMP_SVC
    BOT <--> TG_SVC
    HEALTH --> |/health| MONITOR[Render 모니터링]
    
    style BOT fill:#f9f,stroke:#333,stroke-width:2px
    style GIT fill:#bbf,stroke:#333,stroke-width:2px
```

### 배포 사양
- **플랫폼**: Render.com
- **서비스 타입**: Worker (백그라운드 작업)
- **플랜**: Starter ($7/월)
- **메모리**: 512MB RAM
- **리전**: Oregon (US West)
- **런타임**: Python 3.11
- **자동 배포**: GitHub 푸시 시 자동 배포

## 성능 최적화

### 메모리 관리 전략

```mermaid
graph TD
    subgraph "메모리 최적화 기법"
        BATCH[배치 처리<br/>20개씩 처리]
        CACHE[LRU 캐싱<br/>크기 제한]
        GC[가비지 수집<br/>배치 후 실행]
        STREAM[스트리밍 처리<br/>대용량 데이터]
    end
    
    BATCH --> MEM[메모리 사용량<br/><400MB 유지]
    CACHE --> MEM
    GC --> MEM
    STREAM --> MEM
    
    MEM --> STABLE[안정적인<br/>512MB 환경 운영]
```

### API 요청 최적화

1. **스마트 캐싱**
   - 회사 프로필: 2시간 캐시
   - 주간 데이터: 1시간 캐시
   - 실시간 시세: 1분 캐시

2. **지수 백오프**
   - 초기 지연: 1초
   - 최대 재시도: 6회
   - 백오프 배수: 2x (1s → 2s → 4s → 8s → 16s → 32s)

3. **배치 처리**
   - 배치 크기: 20 주식
   - 병렬 처리: 없음 (메모리 절약)
   - 배치 간 가비지 수집

## 설정 관리

### 환경 변수 구조

```yaml
# 필수 API 키
FMP_API_KEY: FMP API 접근 키
TELEGRAM_BOT_TOKEN: 텔레그램 봇 토큰
TELEGRAM_CHAT_ID: 알림 받을 채팅 ID

# 전략 파라미터
TP_RATIO: 0.10  # 이익 실현 비율 (10%)
SL_RATIO: 0.05  # 손절 비율 (5%)

# 필터링 파라미터
MIN_MARKET_CAP: 500000000    # 최소 시가총액 (5억 달러)
MAX_MARKET_CAP: 50000000000  # 최대 시가총액 (500억 달러)
MIN_VOLUME: 100000           # 최소 거래량
MIN_PRICE: 1.0               # 최소 주가
MAX_PRICE: 10000.0          # 최대 주가

# 운영 파라미터
SCAN_INTERVAL: 14400        # 스캔 주기 (4시간)
BATCH_SIZE: 20              # 배치 크기
FMP_DAILY_LIMIT: 99999      # API 일일 제한
LOG_LEVEL: INFO             # 로그 레벨
```

## 모니터링 및 헬스체크

### 헬스체크 엔드포인트

```mermaid
graph TD
    subgraph "Flask 웹 서버 엔드포인트"
        ROOT[/ - 서비스 정보]
        HEALTH[/health - 헬스체크]
        STATUS[/status - 상세 상태]
        METRICS[/metrics - Prometheus 메트릭]
        SCAN[/trigger-scan - 수동 스캔]
        CACHE_CLEAR[/clear-cache - 캐시 클리어]
    end
    
    HEALTH --> RENDER[Render 모니터링]
    STATUS --> ADMIN[관리자 대시보드]
    METRICS --> PROM[Prometheus/Grafana]
    
    style HEALTH fill:#c8e6c9
    style METRICS fill:#fff9c4
```

### 주요 메트릭
- **bot_running**: 봇 실행 상태
- **total_scans**: 총 스캔 횟수
- **total_signals**: 총 신호 수
- **api_requests_remaining**: 남은 API 요청
- **memory_usage_bytes**: 메모리 사용량

## 에러 처리 및 복구

### 에러 처리 계층

```mermaid
flowchart TD
    ERROR[에러 발생] --> TYPE{에러 유형}
    
    TYPE -->|API 제한| BACKOFF[지수 백오프<br/>재시도]
    TYPE -->|네트워크| RETRY[재시도 로직<br/>최대 6회]
    TYPE -->|메모리| GC_FORCE[강제 GC<br/>캐시 클리어]
    TYPE -->|전략 로직| LOG[로그 기록<br/>다음 주식 처리]
    
    BACKOFF --> RECOVER[정상 처리 재개]
    RETRY --> RECOVER
    GC_FORCE --> RECOVER
    LOG --> CONTINUE[계속 실행]
    
    RECOVER --> NOTIFY[텔레그램 알림<br/>상태 업데이트]
    CONTINUE --> NOTIFY
    
    style ERROR fill:#ffccbc
    style RECOVER fill:#c8e6c9
    style NOTIFY fill:#e1f5fe
```

### 복구 전략
1. **자동 재시작**: Render가 크래시 시 자동 재시작
2. **신호 이력 보존**: JSON 파일로 영구 저장
3. **부분 실패 허용**: 개별 주식 실패 시 전체 스캔 계속
4. **상태 보고**: 에러 발생 시 텔레그램 알림

## 보안 고려사항

1. **API 키 관리**
   - 환경 변수로 분리
   - Render 보안 저장소 사용
   - 코드에 하드코딩 금지

2. **접근 제어**
   - 텔레그램 채팅 ID 검증
   - 관리자 토큰으로 API 보호
   - 명령어 권한 검증

3. **데이터 보호**
   - HTTPS 통신만 사용
   - 민감 정보 로깅 금지
   - 캐시 데이터 암호화 없음 (비민감 데이터)

## 향후 개선 방향

1. **확장성 개선**
   - Redis 캐시 도입
   - 다중 워커 지원
   - 메시지 큐 구현

2. **전략 확장**
   - 추가 기술 지표 통합
   - 다중 시간대 분석
   - 머신러닝 모델 통합

3. **모니터링 강화**
   - 실시간 대시보드 구축
   - 성과 추적 시스템
   - 자동 백테스팅

4. **사용자 경험**
   - 웹 인터페이스 추가
   - 개인화된 알림 설정
   - 포트폴리오 추적 기능