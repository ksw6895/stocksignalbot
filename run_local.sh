#!/bin/bash
# 로컬 실행 스크립트

# 가상환경 활성화
source venv/bin/activate

# 환경변수 체크
if [ ! -f .env ]; then
    echo "Error: .env file not found!"
    echo "Please copy .env.example to .env and configure your API keys"
    exit 1
fi

echo "Starting Crypto Signal Bot..."
python crypto_signal_bot.py