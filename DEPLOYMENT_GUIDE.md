# 배포 가이드 - Binance API IP 제한 해결

## 문제
Binance API는 보안을 위해 IP 화이트리스트를 사용합니다. Render와 같은 클라우드 서비스는 동적 IP를 사용하므로 문제가 발생합니다.

## 해결 방법

### 방법 1: 읽기 전용 API 사용 (추천) ✅

가장 안전하고 간단한 방법입니다.

1. Binance 계정 로그인
2. API Management 페이지로 이동
3. API 키 수정 (Edit restrictions)
4. 다음과 같이 설정:
   - ✅ Enable Reading (읽기만 허용)
   - ❌ Enable Spot & Margin Trading (비활성화)
   - ❌ Enable Futures (비활성화)
   - ❌ Other permissions (모두 비활성화)
5. IP access restrictions: **"Unrestricted (Less Secure)"** 선택
6. Save 클릭

**장점:**
- 무료
- 간단한 설정
- 읽기만 가능하므로 안전
- 모든 클라우드 서비스에서 작동

**단점:**
- IP 제한이 없어 약간의 보안 위험 (하지만 읽기만 가능하므로 큰 문제 없음)

### 방법 2: Railway 사용 (무료 고정 IP) 🚂

Railway는 무료 플랜에서도 고정 IP를 제공합니다.

1. [Railway.app](https://railway.app) 가입
2. New Project → Deploy from GitHub repo
3. 환경 변수 설정
4. Railway가 제공하는 고정 IP를 Binance에 등록

**railway.json 생성:**
```json
{
  "$schema": "https://railway.app/railway.schema.json",
  "build": {
    "builder": "NIXPACKS"
  },
  "deploy": {
    "startCommand": "python crypto_signal_bot.py"
  }
}
```

### 방법 3: 가정/사무실에서 실행 🏠

고정 IP가 있는 환경에서 실행:

1. 가정용 인터넷의 공인 IP 확인: https://whatismyipaddress.com
2. Binance API에 해당 IP 등록
3. 24시간 PC 또는 라즈베리파이에서 실행

**systemd 서비스 생성 (Linux):**
```bash
sudo nano /etc/systemd/system/crypto-signal-bot.service
```

```ini
[Unit]
Description=Crypto Signal Bot
After=network.target

[Service]
Type=simple
User=youruser
WorkingDirectory=/path/to/bot
ExecStart=/usr/bin/python3 /path/to/bot/crypto_signal_bot.py
Restart=always

[Install]
WantedBy=multi-user.target
```

### 방법 4: Oracle Cloud 무료 VM 사용 ☁️

Oracle Cloud는 평생 무료 VM을 제공합니다:

1. [Oracle Cloud](https://www.oracle.com/cloud/free/) 가입
2. Always Free VM 인스턴스 생성
3. 고정 공인 IP 할당
4. SSH로 접속하여 봇 설치

```bash
# VM에서 실행
git clone https://github.com/yourusername/crypto-signal-bot
cd crypto-signal-bot
pip install -r requirements.txt
# .env 파일 생성 후
python crypto_signal_bot.py
```

### 방법 5: GitHub Actions 사용 (제한적) 🤖

매시간 실행되는 GitHub Actions 워크플로우:

**.github/workflows/signal-check.yml:**
```yaml
name: Crypto Signal Check

on:
  schedule:
    - cron: '0 * * * *'  # 매시간
  workflow_dispatch:  # 수동 실행 가능

jobs:
  check-signals:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v3
    - uses: actions/setup-python@v4
      with:
        python-version: '3.11'
    - run: pip install -r requirements.txt
    - run: python crypto_signal_bot.py
      env:
        BINANCE_API_KEY: ${{ secrets.BINANCE_API_KEY }}
        BINANCE_API_SECRET: ${{ secrets.BINANCE_API_SECRET }}
        COINMARKETCAP_API_KEY: ${{ secrets.COINMARKETCAP_API_KEY }}
        TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}
        TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}
```

**주의:** GitHub Actions IP 범위가 넓어서 모든 IP를 등록하기 어려움

## 권장 순서

1. **먼저 시도**: 방법 1 (읽기 전용 API)
2. **보안이 중요하면**: 방법 2 (Railway) 또는 방법 4 (Oracle Cloud)
3. **안정성이 중요하면**: 방법 3 (가정/사무실 실행)

## Binance API 보안 팁

- API 키는 절대 코드에 직접 넣지 마세요
- 정기적으로 API 키를 교체하세요
- API 활동을 모니터링하세요
- 의심스러운 활동 발견 시 즉시 API 키를 삭제하세요