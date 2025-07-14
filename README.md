# Crypto Signal Bot

주봉 캔들 기반 암호화폐 자동 시그널 봇입니다. 실시간으로 시가총액 기준으로 필터링된 코인들을 모니터링하며, 매수 시그널 발생 시 텔레그램으로 알림을 보냅니다.

## 주요 기능

- **실시간 시가총액 필터링**: 매 스캔마다 CoinMarketCap API를 통해 최신 시가총액 데이터로 코인 필터링
- **주봉 기반 전략**: Kwon Strategy를 사용한 주봉(1W) 캔들 분석
- **텔레그램 알림**: 매수 시그널 발생 시 즉시 텔레그램 봇을 통해 알림
- **24시간 자동 실행**: Render 등의 클라우드 서비스에서 24시간 실행 가능

## 전략 설명

이 봇은 다음과 같은 조건에서 매수 시그널을 생성합니다:

1. 최근 5개 주봉 내에서 단일 최고점 식별
2. 최고점 이후 하락 패턴 확인
3. 현재 저가가 EMA(15 또는 33) 아래에 위치
4. 매수가: EMA 가격
5. 목표가(TP): 매수가 + 10% (기본값)
6. 손절가(SL): 매수가 - 5% (기본값)

## 설치 방법

### 1. 필요 사항

- Python 3.11 이상
- Binance API 키
- CoinMarketCap API 키
- Telegram Bot 토큰 및 Chat ID

### 2. 의존성 설치

```bash
pip install -r requirements.txt
```

### 3. 환경 변수 설정

`.env.example` 파일을 복사하여 `.env` 파일을 생성하고 필요한 정보를 입력합니다:

```bash
cp .env.example .env
```

`.env` 파일 내용:
```
# Binance API Configuration
BINANCE_API_KEY=your_binance_api_key
BINANCE_API_SECRET=your_binance_api_secret

# CoinMarketCap API Configuration
COINMARKETCAP_API_KEY=your_coinmarketcap_api_key

# Telegram Bot Configuration
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
TELEGRAM_CHAT_ID=your_telegram_chat_id

# Trading Parameters (Optional)
TP_RATIO=0.1  # 목표가 비율 (10%)
SL_RATIO=0.05  # 손절가 비율 (5%)

# Market Cap Filter Parameters (Optional)
MIN_MARKET_CAP=150000000  # 최소 시가총액 (1.5억 달러)
MAX_MARKET_CAP=20000000000  # 최대 시가총액 (200억 달러)
CMC_MAX_PAGES=5  # CoinMarketCap에서 가져올 페이지 수
```

## 사용 방법

### 실시간 시그널 봇 실행

```bash
python crypto_signal_bot.py
```

봇이 시작되면:
- 즉시 첫 스캔을 실행합니다
- 매시간마다 자동으로 스캔을 반복합니다
- 매일 12:00 UTC에 상태 업데이트를 전송합니다

### 백테스팅 실행 (선택사항)

과거 데이터로 전략을 테스트하려면:

```bash
python KwontBot.py
```

## Render 배포 방법

1. GitHub에 코드를 푸시합니다
2. Render.com에서 새 Worker 서비스를 생성합니다
3. GitHub 저장소를 연결합니다
4. 환경 변수를 설정합니다:
   - BINANCE_API_KEY
   - BINANCE_API_SECRET
   - COINMARKETCAP_API_KEY
   - TELEGRAM_BOT_TOKEN
   - TELEGRAM_CHAT_ID
   - 기타 선택적 변수들

5. 배포를 시작합니다

## 파일 구조

```
.
├── crypto_signal_bot.py    # 메인 실시간 시그널 봇
├── backtest.py            # 백테스팅 로직
├── decision.py            # Kwon 전략 구현
├── indicators.py          # 기술적 지표 계산
├── symbols.py             # 심볼 관리 및 API 통신
├── config.py              # 설정 파일
├── analyzeData.py         # 차트 분석
├── KwontBot.py            # 백테스팅 인터페이스
├── requirements.txt       # Python 패키지 목록
├── .env.example          # 환경 변수 예시
├── .gitignore            # Git 제외 파일
├── render.yaml           # Render 배포 설정
└── runtime.txt           # Python 버전 지정
```

## API 키 발급 방법

### Binance API
1. [Binance](https://www.binance.com)에 로그인
2. 계정 설정 → API 관리
3. 새 API 키 생성 (읽기 권한만 필요)

### CoinMarketCap API
1. [CoinMarketCap](https://coinmarketcap.com/api/) 개발자 포털 방문
2. 무료 계정 생성
3. API 키 발급

### Telegram Bot
1. Telegram에서 @BotFather 검색
2. `/newbot` 명령어로 새 봇 생성
3. 봇 토큰 저장
4. 봇과 대화 시작 후 @userinfobot으로 Chat ID 확인

## 주의사항

- 이 봇은 투자 조언이 아닙니다. 실제 거래 전 충분한 검토가 필요합니다.
- API 키는 절대 공개하지 마세요.
- 시가총액 필터링은 CoinMarketCap API 요청 한도에 따라 제한될 수 있습니다.

## 문제 해결

### 텔레그램 메시지가 오지 않는 경우
- Chat ID가 올바른지 확인
- 봇과의 대화가 시작되었는지 확인

### API 오류가 발생하는 경우
- API 키가 올바른지 확인
- API 요청 한도를 초과하지 않았는지 확인

### 심볼을 찾을 수 없는 경우
- 시가총액 범위 조정 (MIN_MARKET_CAP, MAX_MARKET_CAP)
- CMC_MAX_PAGES 값 증가