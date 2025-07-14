# Google Cloud Run 배포 가이드

이 가이드는 암호화폐 시그널 봇을 Google Cloud Run에 배포하는 과정을 단계별로 설명합니다.

## 사전 준비 사항

1. Google Cloud 계정 (신규 사용자는 $300 무료 크레딧 제공)
2. 로컬에 설치된 Google Cloud SDK (gcloud CLI)
3. Docker (선택사항, 로컬 테스트용)
4. 필요한 API 키들:
   - Binance API (읽기 전용)
   - CoinMarketCap API
   - Telegram Bot Token & Chat ID

## 1단계: Google Cloud 프로젝트 설정

### 1.1 Google Cloud 콘솔 접속
```bash
# https://console.cloud.google.com 접속
```

### 1.2 새 프로젝트 생성
1. 콘솔 상단의 프로젝트 선택 드롭다운 클릭
2. "새 프로젝트" 클릭
3. 프로젝트 이름 입력 (예: crypto-signal-bot)
4. "만들기" 클릭

### 1.3 필요한 API 활성화
```bash
# gcloud CLI로 프로젝트 설정
gcloud config set project YOUR_PROJECT_ID

# 필요한 API 활성화
gcloud services enable cloudbuild.googleapis.com
gcloud services enable run.googleapis.com
gcloud services enable artifactregistry.googleapis.com
```

## 2단계: Artifact Registry 설정 (Docker 이미지 저장소)

```bash
# Artifact Registry 저장소 생성
gcloud artifacts repositories create crypto-bot-repo \
    --repository-format=docker \
    --location=asia-northeast3 \
    --description="Crypto signal bot Docker images"

# Docker 인증 설정
gcloud auth configure-docker asia-northeast3-docker.pkg.dev
```

## 3단계: Docker 이미지 빌드 및 푸시

### 3.1 로컬에서 Docker 이미지 빌드
```bash
# 프로젝트 디렉토리로 이동
cd /path/to/your/project

# Docker 이미지 빌드
docker build -t crypto-signal-bot .

# 이미지 태그 지정
docker tag crypto-signal-bot \
    asia-northeast3-docker.pkg.dev/YOUR_PROJECT_ID/crypto-bot-repo/crypto-signal-bot:latest
```

### 3.2 이미지를 Google Cloud로 푸시
```bash
# 이미지 푸시
docker push asia-northeast3-docker.pkg.dev/YOUR_PROJECT_ID/crypto-bot-repo/crypto-signal-bot:latest
```

### 3.3 Cloud Build를 사용한 빌드 (대안)
```bash
# Cloud Build를 사용하여 직접 빌드 및 푸시
gcloud builds submit --tag \
    asia-northeast3-docker.pkg.dev/YOUR_PROJECT_ID/crypto-bot-repo/crypto-signal-bot:latest
```

## 4단계: 환경 변수 설정

### 4.1 Secret Manager에 민감한 정보 저장 (권장)
```bash
# Secret Manager API 활성화
gcloud services enable secretmanager.googleapis.com

# 각 시크릿 생성
echo -n "your_binance_api_key" | gcloud secrets create binance-api-key --data-file=-
echo -n "your_binance_api_secret" | gcloud secrets create binance-api-secret --data-file=-
echo -n "your_cmc_api_key" | gcloud secrets create cmc-api-key --data-file=-
echo -n "your_telegram_bot_token" | gcloud secrets create telegram-bot-token --data-file=-
echo -n "your_telegram_chat_id" | gcloud secrets create telegram-chat-id --data-file=-
```

## 5단계: Cloud Run 서비스 배포

### 5.1 서비스 생성 및 배포
```bash
gcloud run deploy crypto-signal-bot \
    --image asia-northeast3-docker.pkg.dev/YOUR_PROJECT_ID/crypto-bot-repo/crypto-signal-bot:latest \
    --platform managed \
    --region asia-northeast3 \
    --memory 512Mi \
    --cpu 1 \
    --timeout 3600 \
    --max-instances 1 \
    --min-instances 1 \
    --no-allow-unauthenticated \
    --set-env-vars="TP_RATIO=0.1,SL_RATIO=0.05,MIN_MARKET_CAP=150000000,MAX_MARKET_CAP=20000000000,CMC_MAX_PAGES=5" \
    --set-secrets="BINANCE_API_KEY=binance-api-key:latest,BINANCE_API_SECRET=binance-api-secret:latest,COINMARKETCAP_API_KEY=cmc-api-key:latest,TELEGRAM_BOT_TOKEN=telegram-bot-token:latest,TELEGRAM_CHAT_ID=telegram-chat-id:latest"
```

### 5.2 배포 옵션 설명
- `--memory 512Mi`: 메모리 할당 (필요에 따라 조정)
- `--cpu 1`: CPU 할당
- `--timeout 3600`: 요청 타임아웃 (1시간)
- `--max-instances 1`: 최대 인스턴스 수 (비용 절감을 위해 1로 설정)
- `--min-instances 1`: 최소 인스턴스 수 (항상 실행 유지)
- `--no-allow-unauthenticated`: 인증되지 않은 접근 차단

## 6단계: 서비스 모니터링

### 6.1 로그 확인
```bash
# 실시간 로그 확인
gcloud run services logs read crypto-signal-bot \
    --region=asia-northeast3 \
    --limit=50 \
    --follow
```

### 6.2 서비스 상태 확인
```bash
# 서비스 정보 확인
gcloud run services describe crypto-signal-bot \
    --region=asia-northeast3

# 서비스 URL 확인 (헬스체크용)
gcloud run services describe crypto-signal-bot \
    --region=asia-northeast3 \
    --format='value(status.url)'
```

### 6.3 헬스체크
```bash
# 서비스가 정상 작동하는지 확인
SERVICE_URL=$(gcloud run services describe crypto-signal-bot --region=asia-northeast3 --format='value(status.url)')
curl $SERVICE_URL/health
```

## 7단계: 비용 최적화

### 7.1 자동 스케일링 설정
```bash
# CPU 사용률 기반 자동 스케일링 설정
gcloud run services update crypto-signal-bot \
    --region=asia-northeast3 \
    --cpu-throttling \
    --min-instances=0 \
    --max-instances=1
```

### 7.2 예산 알림 설정
1. Google Cloud Console > 결제 > 예산 및 알림
2. "예산 만들기" 클릭
3. 월 예산 설정 (예: $10)
4. 알림 임계값 설정 (50%, 90%, 100%)

## 8단계: 문제 해결

### 8.1 일반적인 문제와 해결 방법

#### 메모리 부족
```bash
# 메모리 증가
gcloud run services update crypto-signal-bot \
    --region=asia-northeast3 \
    --memory=1Gi
```

#### API 타임아웃
```bash
# 타임아웃 증가
gcloud run services update crypto-signal-bot \
    --region=asia-northeast3 \
    --timeout=3600
```

#### 서비스가 시작되지 않음
```bash
# 상세 로그 확인
gcloud logging read \
    "resource.type=cloud_run_revision AND resource.labels.service_name=crypto-signal-bot" \
    --limit=100 \
    --format=json
```

## 9단계: 업데이트 배포

### 9.1 코드 업데이트 후 재배포
```bash
# 새 이미지 빌드 및 푸시
gcloud builds submit --tag \
    asia-northeast3-docker.pkg.dev/YOUR_PROJECT_ID/crypto-bot-repo/crypto-signal-bot:v2

# 서비스 업데이트
gcloud run services update crypto-signal-bot \
    --image asia-northeast3-docker.pkg.dev/YOUR_PROJECT_ID/crypto-bot-repo/crypto-signal-bot:v2 \
    --region=asia-northeast3
```

### 9.2 롤백
```bash
# 이전 리비전으로 롤백
gcloud run services update-traffic crypto-signal-bot \
    --region=asia-northeast3 \
    --to-revisions=PREVIOUS_REVISION_NAME=100
```

## 10단계: 정리 (프로젝트 삭제)

```bash
# 프로젝트 전체 삭제 (주의!)
gcloud projects delete YOUR_PROJECT_ID
```

## 추가 팁

1. **리전 선택**: 한국에서 사용한다면 `asia-northeast3` (서울) 추천
2. **비용 관리**: 최소 인스턴스를 0으로 설정하면 비용을 절약할 수 있지만, 첫 요청 시 콜드 스타트 발생
3. **모니터링**: Google Cloud Monitoring을 활용하여 성능 지표 추적
4. **보안**: Secret Manager 사용 및 최소 권한 원칙 적용

## 예상 비용

- Cloud Run: 월 200만 요청, 360,000 GB-초, 180,000 vCPU-초 무료
- 이 봇의 경우 무료 할당량 내에서 충분히 운영 가능
- 추가 비용: Artifact Registry 저장 공간 (약 $0.10/GB/월)

## 지원 및 문서

- [Cloud Run 공식 문서](https://cloud.google.com/run/docs)
- [Cloud Run 가격 책정](https://cloud.google.com/run/pricing)
- [Google Cloud 무료 프로그램](https://cloud.google.com/free)