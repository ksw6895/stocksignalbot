# 📚 Render 배포 완벽 가이드

## 목차
1. [사전 준비사항](#1-사전-준비사항)
2. [Render 계정 설정](#2-render-계정-설정)
3. [render.yaml 파일 생성](#3-renderyaml-파일-생성)
4. [Background Worker 생성](#4-background-worker-생성)
5. [환경 변수 설정](#5-환경-변수-설정)
6. [배포 및 모니터링](#6-배포-및-모니터링)
7. [트러블슈팅](#7-트러블슈팅)

---

## 1. 사전 준비사항

### 필요한 것들:
- ✅ GitHub 계정 (완료)
- ✅ 코드가 푸시된 GitHub 저장소 (완료: `ksw6895/stocksignalbot`)
- ⬜ Render 계정
- ⬜ FMP API 키
- ⬜ Telegram Bot Token & Chat ID
- ⬜ 신용카드 (유료 플랜용)

### API 키 확인:
```bash
# FMP API 키 확인 (없으면 생성)
# https://site.financialmodelingprep.com/developer/docs

# Telegram Bot Token 확인
# @BotFather에게 /mybots 명령어로 확인

# Telegram Chat ID 확인
# @userinfobot에게 메시지 보내서 확인
```

---

## 2. Render 계정 설정

### 2.1 Render 가입
1. https://render.com 접속
2. **"Get Started for Free"** 클릭
3. **GitHub으로 가입** 선택 (권장)
4. GitHub 권한 승인

### 2.2 결제 정보 등록 (Background Worker용)
1. Dashboard → **"Account Settings"**
2. **"Billing"** 탭 선택
3. **"Add Payment Method"** 클릭
4. 신용카드 정보 입력
5. **"Save"** 클릭

> ⚠️ **중요**: Background Worker는 유료 플랜이므로 결제 정보 필수

---

## 3. render.yaml 파일 생성

### 3.1 프로젝트 루트에 `render.yaml` 파일 생성

```yaml
services:
  - type: worker
    name: stock-signal-bot
    runtime: python
    plan: starter  # $7/월 플랜
    region: oregon  # 또는 ohio, frankfurt, singapore
    
    buildCommand: |
      pip install --upgrade pip
      pip install -r requirements.txt
    
    startCommand: python stock_signal_bot.py
    
    envVars:
      - key: FMP_API_KEY
        sync: false  # 수동으로 입력
      - key: TELEGRAM_BOT_TOKEN
        sync: false  # 수동으로 입력
      - key: TELEGRAM_CHAT_ID
        sync: false  # 수동으로 입력
      - key: TP_RATIO
        value: "0.10"  # 10% Take Profit
      - key: SL_RATIO
        value: "0.05"  # 5% Stop Loss
      - key: MIN_MARKET_CAP
        value: "500000000"  # 5억 달러
      - key: MAX_MARKET_CAP
        value: "50000000000"  # 500억 달러
      - key: MIN_VOLUME
        value: "100000"
      - key: MIN_PRICE
        value: "1"
      - key: MAX_PRICE
        value: "10000"
      - key: WATCHLIST_SYMBOLS
        value: ""  # 특정 종목만 모니터링하려면 "AAPL,MSFT,GOOGL"
      - key: EXCLUDED_SYMBOLS
        value: ""  # 제외할 종목 "TSLA,META"
      - key: FMP_DAILY_LIMIT
        value: "99999"  # 실제로는 backoff로 처리
      - key: BATCH_SIZE
        value: "20"
    
    autoDeploy: true  # GitHub 푸시 시 자동 배포
```

### 3.2 파일 커밋 & 푸시
```bash
git add render.yaml
git commit -m "Add Render deployment configuration"
git push origin main
```

---

## 4. Background Worker 생성

### 방법 1: Blueprint로 한 번에 배포 (권장) ⭐

1. Render Dashboard에서 **"New +"** → **"Blueprint"** 클릭
2. GitHub 저장소 연결:
   - **"Connect GitHub account"** 클릭
   - `ksw6895/stocksignalbot` 저장소 선택
   - **"Connect"** 클릭
3. Blueprint 이름 입력: `stock-signal-bot-blueprint`
4. **"Apply"** 클릭
5. 서비스가 자동으로 생성됨

### 방법 2: 수동으로 Background Worker 생성

1. Render Dashboard에서 **"New +"** → **"Background Worker"** 클릭
2. **"Connect a repository"** 선택
3. GitHub 저장소 선택:
   - `ksw6895/stocksignalbot` 찾기
   - **"Connect"** 클릭
4. 설정 입력:
   ```
   Name: stock-signal-bot
   Region: Oregon (US West)
   Branch: main
   Runtime: Python 3
   Build Command: pip install -r requirements.txt
   Start Command: python stock_signal_bot.py
   Plan: Starter ($7/month)
   ```
5. **"Create Background Worker"** 클릭

---

## 5. 환경 변수 설정

### 5.1 서비스 대시보드 접속
1. Render Dashboard → 생성된 `stock-signal-bot` 클릭
2. **"Environment"** 탭 선택

### 5.2 필수 환경 변수 입력

| 변수명 | 설명 | 예시 값 |
|--------|------|---------|
| `FMP_API_KEY` | FMP API 키 | `your_fmp_api_key_here` |
| `TELEGRAM_BOT_TOKEN` | 텔레그램 봇 토큰 | `7012345678:AAH...` |
| `TELEGRAM_CHAT_ID` | 텔레그램 채팅 ID | `-1001234567890` |

### 5.3 환경 변수 추가 방법
1. **"Add Environment Variable"** 클릭
2. Key와 Value 입력
3. **"Save"** 클릭
4. 모든 필수 변수 입력 후 서비스 자동 재시작

---

## 6. 배포 및 모니터링

### 6.1 첫 배포 확인
1. **"Logs"** 탭에서 실시간 로그 확인
2. 정상 시작 메시지 확인:
   ```
   =================================================
   Upper Section Strategy Bot Started
   =================================================
   Starting Upper Section Strategy scan (Weekly)...
   ```

### 6.2 텔레그램 확인
1. 봇이 시작 메시지 전송 확인:
   ```
   🚀 Upper Section Strategy Bot Started
   
   Monitoring NASDAQ stocks for Upper Section patterns using weekly data.
   • Strategy: Single Peak + Bearish Pattern + EMA Entry
   • Timeframe: Weekly (1W)
   • Scan Interval: Every 4 hours
   • TP/SL: +10% / -5%
   ```

### 6.3 모니터링 대시보드
- **Metrics** 탭: CPU, 메모리 사용량 확인
- **Logs** 탭: 실시간 로그 스트리밍
- **Events** 탭: 배포 이력 확인

---

## 7. 트러블슈팅

### 문제 1: ModuleNotFoundError
**증상**: `ModuleNotFoundError: No module named 'pandas'`

**해결**:
```bash
# requirements.txt 확인
pandas==2.1.4
python-telegram-bot==20.7
requests==2.31.0
schedule==1.2.0

# 커밋 & 푸시
git add requirements.txt
git commit -m "Update requirements.txt"
git push
```

### 문제 2: 환경 변수 에러
**증상**: `TELEGRAM_BOT_TOKEN environment variable is not set`

**해결**:
1. Environment 탭에서 변수 확인
2. 변수명 철자 확인 (대소문자 구분)
3. Save 후 서비스 재시작

### 문제 3: API 에러 429
**증상**: `Rate limit hit (429)`

**해결**:
- 자동으로 exponential backoff 작동
- 로그에서 재시도 메시지 확인

### 문제 4: 메모리 부족
**증상**: `Worker exited with signal: SIGKILL`

**해결**:
1. Settings → Instance Type
2. Standard ($25/월)로 업그레이드
3. Save Changes

---

## 8. 유용한 명령어

### 로컬 테스트
```bash
# 환경 변수 설정
export FMP_API_KEY="your_key"
export TELEGRAM_BOT_TOKEN="your_token"
export TELEGRAM_CHAT_ID="your_chat_id"

# 실행
python stock_signal_bot.py
```

### 로그 확인 (Render CLI)
```bash
# Render CLI 설치
brew install render/render/render

# 로그인
render login

# 로그 확인
render logs stock-signal-bot --tail
```

---

## 9. 비용 관리

### 현재 설정 월 비용
- Background Worker (Starter): $7.00
- 예상 총 비용: **$7.00/월** (약 9,100원)

### 비용 모니터링
1. Account Settings → Billing
2. **"Current Usage"** 확인
3. 월별 청구서 확인

### 비용 절감 팁
- 불필요한 로그 레벨 낮추기
- 캐시 적극 활용
- 스캔 주기 조정 (4시간 → 6시간)

---

## 10. 자동 배포 설정

### GitHub Actions 연동 (선택사항)
1. Render Dashboard → Service Settings
2. **"Auto-Deploy"** 활성화
3. Branch: `main` 선택
4. 이제 GitHub push 시 자동 배포

---

## 📞 지원 및 문의

### Render 지원
- 문서: https://render.com/docs
- 커뮤니티: https://community.render.com
- 지원: support@render.com

### 봇 관련 문의
- GitHub Issues: https://github.com/ksw6895/stocksignalbot/issues

---

## ✅ 체크리스트

배포 전 확인사항:
- [ ] GitHub에 최신 코드 푸시 완료
- [ ] render.yaml 파일 생성 및 푸시
- [ ] Render 계정 생성 및 결제 정보 등록
- [ ] FMP API 키 준비
- [ ] Telegram Bot Token & Chat ID 준비
- [ ] requirements.txt 파일 확인

배포 후 확인사항:
- [ ] Logs에서 정상 시작 확인
- [ ] Telegram 시작 메시지 수신 확인
- [ ] 첫 스캔 완료 확인 (최대 몇 분 소요)
- [ ] 4시간 후 다음 스캔 예정 확인

---

## 🎉 축하합니다!

모든 설정이 완료되면 봇이 자동으로:
- 매 4시간마다 NASDAQ 주식 스캔
- Upper Section Strategy 패턴 탐지
- Telegram으로 시그널 전송
- 24/7 연속 운영

행운을 빕니다! 📈🚀