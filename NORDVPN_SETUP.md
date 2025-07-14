# NordVPN 프록시 설정 가이드

## 1. NordVPN SOCKS5 프록시 정보 얻기

1. NordVPN 계정에 로그인: https://my.nordaccount.com/dashboard/nordvpn/
2. 왼쪽 메뉴에서 "NordVPN" > "Manual setup" 클릭
3. "Service credentials (manual setup)" 섹션에서:
   - Username: 자동 생성된 사용자명 (이메일과 다름)
   - Password: 자동 생성된 비밀번호

4. SOCKS5 프록시 서버 목록 확인:
   - 미국: `us89.nordvpn.com`, `us5068.nordvpn.com` 등
   - 일본: `jp561.nordvpn.com`, `jp562.nordvpn.com` 등
   - 포트: 항상 1080

## 2. Render 환경 변수 설정

Render 대시보드에서 환경변수 추가:

1. Render 대시보드에서 서비스 선택
2. "Environment" 탭 클릭
3. "Add Environment Variable" 클릭
4. 다음 추가:
   - Key: `PROXY_URL`
   - Value: `socks5://USERNAME:PASSWORD@SERVER.nordvpn.com:1080`

예시:
```
Key: PROXY_URL
Value: socks5://Ab1Cd2Ef3Gh4:MySecretPass123@de987.nordvpn.com:1080
```

**주의**: 비밀번호에 특수문자(`@`, `:`, `/`)가 있으면 URL 인코딩 필요:
- `@` → `%40`
- `:` → `%3A`
- `/` → `%2F`

## 3. 서버 선택 팁

- **미국 서버**: Binance US 규제로 인해 차단될 수 있음
- **유럽 서버**: 독일(`de987.nordvpn.com`), 네덜란드(`nl896.nordvpn.com`) 추천
- **아시아 서버**: 일본(`jp561.nordvpn.com`), 싱가포르(`sg543.nordvpn.com`) 추천

## 4. 로컬 테스트 방법

로컬에서 프록시 연결 테스트 (`.env` 파일 사용):

```python
import requests
import os
from dotenv import load_dotenv

load_dotenv()

proxies = {
    'http': os.getenv('PROXY_URL'),
    'https': os.getenv('PROXY_URL')
}

# IP 확인
response = requests.get('https://api.ipify.org?format=json', proxies=proxies)
print(f"Current IP: {response.json()['ip']}")

# Binance API 테스트
response = requests.get('https://api.binance.com/api/v3/ping', proxies=proxies)
print(f"Binance ping: {response.status_code}")
```

## 5. Render 배포 시 주의사항

1. Render 환경 변수에 `PROXY_URL` 추가
2. 프록시 URL에 특수문자가 있으면 URL 인코딩 필요
3. 연결 실패 시 다른 서버로 변경

## 6. 문제 해결

- **418 에러 지속**: 다른 지역 서버로 변경
- **연결 시간 초과**: 프록시 서버가 다운됐을 수 있음, 다른 서버 시도
- **인증 실패**: NordVPN 대시보드에서 credentials 재확인

## 7. 대안

NordVPN이 작동하지 않는 경우:
1. **Residential Proxy**: IPRoyal, Bright Data 등
2. **다른 VPN 서비스**: ExpressVPN, Surfshark의 SOCKS5
3. **클라우드 프록시**: AWS/GCP에 개인 프록시 서버 구축