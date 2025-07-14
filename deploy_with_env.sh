#!/bin/bash

# .env 파일이 있는지 확인
if [ ! -f .env ]; then
    echo "Error: .env file not found!"
    echo "Please create .env file from .env.example and fill in your API keys"
    exit 1
fi

# .env 파일 로드 (Windows 줄 바꿈 문자 제거)
export $(cat .env | sed 's/\r$//' | grep -v '^#' | grep -v '^$' | xargs)

# 필수 환경변수 확인
if [ -z "$BINANCE_API_KEY" ] || [ -z "$BINANCE_API_SECRET" ] || [ -z "$COINMARKETCAP_API_KEY" ] || [ -z "$TELEGRAM_BOT_TOKEN" ] || [ -z "$TELEGRAM_CHAT_ID" ]; then
    echo "Error: Missing required environment variables!"
    echo "Please check your .env file"
    exit 1
fi

echo "Deploying to Cloud Run with environment variables from .env file..."

# Cloud Run 배포
gcloud run deploy crypto-signal-bot \
    --image asia-northeast3-docker.pkg.dev/crypto-signal-bot-465917/crypto-bot-repo/crypto-signal-bot:latest \
    --platform managed \
    --region asia-northeast3 \
    --memory 512Mi \
    --cpu 1 \
    --timeout 3600 \
    --max-instances 1 \
    --min-instances 1 \
    --no-allow-unauthenticated \
    --set-env-vars="BINANCE_API_KEY=$BINANCE_API_KEY,BINANCE_API_SECRET=$BINANCE_API_SECRET,COINMARKETCAP_API_KEY=$COINMARKETCAP_API_KEY,TELEGRAM_BOT_TOKEN=$TELEGRAM_BOT_TOKEN,TELEGRAM_CHAT_ID=$TELEGRAM_CHAT_ID,TP_RATIO=${TP_RATIO:-0.1},SL_RATIO=${SL_RATIO:-0.05},MIN_MARKET_CAP=${MIN_MARKET_CAP:-150000000},MAX_MARKET_CAP=${MAX_MARKET_CAP:-20000000000},CMC_MAX_PAGES=${CMC_MAX_PAGES:-5}"

echo "Deployment complete!"