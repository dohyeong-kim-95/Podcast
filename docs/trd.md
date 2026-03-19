# Podcast — TRD v1.0

## 1. 시스템 아키텍처

```
┌─────────────────────────────────────────────────┐
│                   사용자 (모바일)                    │
│                  Next.js PWA                      │
│              Firebase Hosting                     │
└────────────────────┬────────────────────────────┘
                     │ HTTPS
                     ▼
┌─────────────────────────────────────────────────┐
│              FastAPI (Cloud Run)                  │
│                                                   │
│  ┌──────────┐ ┌──────────┐ ┌────────────────┐   │
│  │ Upload   │ │ Podcast  │ │ Auth/Session   │   │
│  │ Service  │ │ Service  │ │ Service        │   │
│  └────┬─────┘ └────┬─────┘ └───────┬────────┘   │
└───────┼────────────┼───────────────┼─────────────┘
        │            │               │
        ▼            ▼               ▼
┌──────────┐  ┌───────────┐  ┌──────────────┐
│ Firebase │  │notebooklm │  │Browserless.io│
│ Storage  │  │   -py     │  │(원격 브라우저) │
└──────────┘  └───────────┘  └──────────────┘
        │            │
        ▼            ▼
┌──────────────────────────┐
│   Firebase Firestore     │
│  (메타데이터, 메모리, 쿠키) │
└──────────────────────────┘

┌──────────────────────────┐
│   Cloud Scheduler        │
│   매일 06:40 KST         │──→ Cloud Run POST /api/generate
└──────────────────────────┘
```

## 2. 기술 스택

| 구성요소 | 기술 | 비고 |
|---------|------|------|
| 프론트엔드 | Next.js 14 (App Router) | PWA, Spotify 스타일 다크 UI |
| 호스팅 | Firebase Hosting | 정적 export |
| 백엔드 | Python FastAPI | Cloud Run 배포 |
| 컨테이너 | Google Cloud Run | min 0, max 1 (단일 인스턴스, asyncio 병렬) |
| 인증 | Firebase Auth | Google OAuth |
| DB | Firebase Firestore | 메타데이터, 메모리, 쿠키 |
| 파일 저장 | Firebase Storage | 소스 파일, 팟캐스트 오디오 |
| 팟캐스트 | notebooklm-py 0.3.x | 비공식 NB API |
| 스케줄링 | Cloud Scheduler | 일일 06:40 KST |
| 알림 | FCM (Firebase Cloud Messaging) | PWA Push |
| NB 재인증 | Browserless.io | 원격 Chromium |
| 이미지→PDF | img2pdf | 서버사이드 변환 (코드 간소화를 위해 reportlab 대신 채택) |

## 3. 데이터 모델 (Firestore)

### 3.1 users/{uid}
```json
{
  "email": "user@gmail.com",
  "displayName": "사용자",
  "createdAt": "timestamp",
  "fcmToken": "push_token_string",
  "memory": {
    "interests": "AI, 투자, 배터리 기술",
    "preferredTone": "기술적 깊이 있지만 친근한 톤",
    "preferredDepth": "전문가 수준",
    "customInstructions": "자유 텍스트",
    "feedbackHistory": [
      { "date": "2026-03-18", "rating": "good" },
      { "date": "2026-03-17", "rating": "normal" }
    ]
  }
}
```

### 3.2 users/{uid}/nb_session (단일 문서)
```json
{
  "storageState": "encrypted_json_string",
  "lastUpdated": "timestamp",
  "expiresAt": "timestamp",
  "status": "valid | expiring_soon | expired"
}
```

### 3.3 sources/{sourceId}
```json
{
  "uid": "user_uid",
  "fileName": "screenshot_01.png",
  "originalType": "image/png",
  "convertedType": "application/pdf",
  "originalStoragePath": "sources/{uid}/{date}/{sourceId}.png",
  "convertedStoragePath": "sources/{uid}/{date}/{sourceId}.pdf",
  // thumbnailPath: MVP 스킵. 파일 타입 아이콘(📄/🖼️)으로 대체. P1에서 썸네일 생성 검토
  "uploadedAt": "timestamp",
  "windowDate": "2026-03-19",
  "status": "uploaded | processing | ready | used | deleted"
}
```

### 3.4 podcasts/{podcastId}
```json
{
  "uid": "user_uid",
  "date": "2026-03-19",
  "sourceIds": ["sourceId1", "sourceId2"],
  "sourceCount": 5,
  "audioPath": "podcasts/{uid}/2026-03-19.mp3",
  "durationSeconds": 600,
  "generatedAt": "timestamp",
  "status": "pending | generating | retry_1 | retry_2 | completed | failed",
  "instructionsUsed": "생성 시 사용된 instructions",
  "error": null,
  "feedback": null,
  "downloaded": false
}
```

## 4. API 설계

### 4.1 소스 관리
| 메서드 | 경로 | 설명 |
|--------|------|------|
| POST | `/api/sources/upload` | 파일 업로드 (multipart/form-data) |
| GET | `/api/sources?date=YYYY-MM-DD` | 특정 윈도우 소스 목록 |
| DELETE | `/api/sources/{sourceId}` | 소스 삭제 |

### 4.2 팟캐스트
| 메서드 | 경로 | 설명 |
|--------|------|------|
| POST | `/api/generate` | 전체 사용자 생성 트리거 (Scheduler) |
| POST | `/api/generate/me` | 개별 사용자 수동 생성 트리거 |
| GET | `/api/podcast/today` | 오늘의 팟캐스트 정보 + signed URL |
| POST | `/api/podcast/{id}/feedback` | 피드백 (good/normal/bad) |
| POST | `/api/podcast/{id}/downloaded` | 다운로드 완료 표시 |
| POST | `/api/remind-download` | 다운로드 리마인더 (Scheduler, 22:00 KST) |

### 4.3 메모리
| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | `/api/memory` | 현재 메모리 조회 |
| PUT | `/api/memory` | 메모리 업데이트 |

### 4.4 NB 세션
| 메서드 | 경로 | 설명 |
|--------|------|------|
| POST | `/api/nb-session/start-auth` | Browserless 세션 시작, 뷰어 URL 반환, 폴링 시작 |
| GET | `/api/nb-session/poll/{session_id}` | 폴링 상태 조회 (프론트가 완료 여부 확인용) |
| GET | `/api/nb-session/status` | 쿠키 유효성 상태 |

## 5. 핵심 플로우 상세

### 5.1 팟캐스트 생성 플로우

```
Cloud Scheduler (06:40 KST)
    │
    ▼
POST /api/generate (Scheduler → 전체 사용자 순회)
    │
    ├─ 0. 화이트리스트 전체 사용자 조회, 각 사용자별로 아래 플로우 병렬 실행
    ├─ 0-1. 당일 팟캐스트 status가 completed/generating/retry_1/retry_2인 사용자 → 스킵 (동시 생성 방지)
    ├─ 1. 소스 윈도우 내 소스 조회 (전일 06:40 ~ 당일 06:40)
    ├─ 소스 0개 → 스킵, "소스 없음" 푸시 알림, 종료
    │
    ├─ 2. 사용자 메모리 로드 → instructions 구성
    ├─ 3. NB 쿠키 로드 & 유효성 확인
    │     만료 → 실패, "재인증 필요" 푸시
    │
    ├─ 4. notebooklm-py 실행
    │     a. 노트북 생성
    │     b. Storage에서 소스 다운로드 → 노트북에 전량 추가
    │     c. generate_audio(instructions=...) 호출
    │     d. wait_for_completion (타임아웃 20분)
    │     e. download_audio → Storage 저장
    │     f. 임시 노트북 삭제
    │
    ├─ 실패 → status: retry_1 또는 retry_2로 업데이트
    │     Cloud Scheduler 재시도 정책으로 별도 요청 재호출 (최대 2회)
    │     3회 실패 → status: failed, 수동 트리거 활성화
    │
    ├─ 5. 이전 날 팟캐스트 오디오 삭제
    └─ 6. FCM 푸시 알림
```

### 5.2 이미지→PDF 변환

업로드 시 동기 처리:
1. 원본 이미지 Storage 저장
2. `img2pdf.convert(image_bytes)` → PDF 바이트 생성
3. PDF를 Storage 저장
4. Firestore 소스 문서 업데이트

### 5.3 Browserless.io 재인증

```
"재인증" 버튼 탭
    │
    ├─ 1. POST /api/nb-session/start-auth
    │     → Browserless API로 원격 Chromium 세션 생성
    │     → Playwright로 원격 브라우저에 connect, notebooklm.google.com으로 navigate
    │     → 세션 뷰어 URL + 폴링 ID 반환
    │
    ├─ 2. 프론트에서 뷰어 URL 표시 (iframe 또는 새 탭)
    │     → ⚠️ Google 로그인 페이지가 iframe을 차단할 가능성 높음 (X-Frame-Options: DENY)
    │     → T-059 스파이크 결과에 따라 iframe / window.open() 팝업 / 새 탭 중 확정
    │     → 새 탭 방식 시: 서버 폴링으로 완료 감지 후 원래 탭에서 상태 갱신
    │     → 사용자가 Google 로그인 수행
    │
    ├─ 3. 서버가 Playwright로 로그인 완료 자동 감지 (폴링)
    │     → 2초 간격으로 page.url() 확인
    │     → URL이 notebooklm.google.com/* (로그인 후 리다이렉트)로 변경되면 로그인 완료 판정
    │     → 타임아웃: 5분 (초과 시 세션 종료, 프론트에 실패 응답)
    │     → 로그인 완료 시 browser.contexts[0].storage_state() 호출 → 쿠키/스토리지 추출
    │     ※ 리스크: 폴링 동안 Browserless 세션 유지 필요. 무료 티어 시간 소모하지만
    │       재인증이 월 1~2회이므로 문제 수준 아님
    │
    ├─ 4. 추출한 storage_state를 Fernet(AES) 암호화 → Firestore nb_session 문서 저장
    │     → expiresAt: 현재 + 30일 (추정)
    │     → status: "valid"
    │
    ├─ 5. Browserless 세션 종료 (browser.close())
    └─ 6. 프론트에 "인증 완료" 응답 → iframe 닫기, StatusBanner 갱신
```

**구현 핵심 (Playwright 서버 코드)**:
```python
# start-auth 시 백그라운드 태스크로 폴링 시작
async def poll_login_completion(browser, session_id: str):
    """2초 간격으로 URL 체크, 로그인 완료 시 쿠키 추출"""
    page = browser.contexts[0].pages[0]
    timeout = 300  # 5분

    for _ in range(timeout // 2):
        await asyncio.sleep(2)
        current_url = page.url
        if "notebooklm.google.com" in current_url and "/login" not in current_url:
            # 로그인 완료 감지
            storage_state = await browser.contexts[0].storage_state()
            encrypted = fernet.encrypt(json.dumps(storage_state).encode())
            await save_to_firestore(session_id, encrypted)
            await browser.close()
            return True

    # 타임아웃
    await browser.close()
    return False
```

### 5.4 메모리→Instructions 구성

```python
def build_instructions(memory: dict) -> str:
    parts = ["한국어로 진행해주세요.", "10분 분량으로 만들어주세요."]

    if memory.get("interests"):
        parts.append(f"청취자 관심 분야: {memory['interests']}")
    if memory.get("preferredTone"):
        parts.append(f"톤: {memory['preferredTone']}")
    if memory.get("preferredDepth"):
        parts.append(f"깊이: {memory['preferredDepth']}")
    if memory.get("customInstructions"):
        parts.append(memory["customInstructions"])

    recent = memory.get("feedbackHistory", [])[-10:]
    if recent:
        bad = sum(1 for f in recent if f["rating"] == "bad")
        if bad >= 3:
            parts.append("최근 피드백이 부정적입니다. 더 흥미롭게 만들어주세요.")

    return " ".join(parts)
```

## 6. 프론트엔드 구조

```
app/
├── layout.tsx              # 다크 테마, 하단 네비게이션
├── page.tsx                # 메인: 오늘의 팟캐스트 + 플레이어
├── upload/page.tsx         # 소스 업로드 & 목록
├── memory/page.tsx         # 성향 메모리 설정
├── settings/page.tsx       # NB 세션 관리, 계정
├── components/
│   ├── AudioPlayer.tsx     # 재생/일시정지, 시크바, 배속
│   ├── SourceList.tsx      # 소스 목록 (파일타입 아이콘, 삭제)
│   ├── UploadZone.tsx      # 파일 선택 / 카메라 촬영
│   ├── StatusBanner.tsx    # NB 세션 상태 배너
│   ├── FeedbackBar.tsx     # 좋았다/보통/별로
│   └── BottomNav.tsx       # 하단 네비게이션
├── lib/
│   ├── firebase.ts         # Firebase 초기화
│   ├── api.ts              # API 클라이언트
│   └── auth.ts             # Auth 헬퍼
└── public/
    ├── manifest.json       # PWA 매니페스트
    └── sw.js               # Service Worker (푸시, 백그라운드 재생)
```

## 7. 배포 구성

### 7.1 Cloud Run
- **이미지**: Python 3.11 + FastAPI + notebooklm-py + Playwright (라이브러리만, Chromium 미포함 — Browserless.io 원격 연결)
- **메모리**: 1GB / **CPU**: 1 vCPU
- **인스턴스**: min 0, max 1 (단일 인스턴스에서 asyncio로 5명 병렬 처리)
- **타임아웃**: 25분
- **환경변수**: `FIREBASE_PROJECT_ID`, `ALLOWED_EMAILS`, `NB_COOKIE_ENCRYPTION_KEY`, `BROWSERLESS_API_KEY`, `CLOUD_RUN_URL` (OIDC audience용)

### 7.2 Cloud Scheduler
- **생성 크론**: `40 6 * * *` (Asia/Seoul) → Cloud Run `POST /api/generate`
- **다운로드 리마인더 크론**: `0 22 * * *` (Asia/Seoul) → Cloud Run `POST /api/remind-download`
- **인증**: 서비스 어카운트 OIDC

### 7.3 Dockerfile
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# Chromium 바이너리 미설치: Browserless.io 원격 브라우저 사용
# playwright 라이브러리만으로 browser.connect_over_cdp() 가능
COPY . .
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
```

## 8. 보안

- **사용자 인증**: Firebase Auth ID 토큰 검증 + 이메일 화이트리스트 (최대 5명, 모든 사용자 API)
- **Scheduler 인증**: Cloud Scheduler → Cloud Run 호출 시 서비스 어카운트 OIDC 토큰 사용
  - `/api/generate`, `/api/remind-download` 엔드포인트에 OIDC 검증 미들웨어 적용
  - `google.oauth2.id_token.verify_oauth2_token()` 으로 Authorization 헤더의 OIDC 토큰 검증
  - `audience`는 Cloud Run 서비스 URL (예: `https://podcast-xxxxx-run.app`)
  - 검증 실패 시 403 반환 → 외부에서 임의 호출 방지
  - 구현: `google-auth` 라이브러리 사용
  ```python
  from google.oauth2 import id_token
  from google.auth.transport import requests

  def verify_scheduler_token(authorization: str, expected_audience: str):
      """Cloud Scheduler OIDC 토큰 검증"""
      token = authorization.replace("Bearer ", "")
      claim = id_token.verify_oauth2_token(
          token, requests.Request(), audience=expected_audience
      )
      # claim["email"]이 Scheduler 서비스 어카운트인지 확인
      return claim
  ```
- **NB 쿠키**: Fernet(AES) 암호화 후 Firestore 저장, 키는 환경변수 `NB_COOKIE_ENCRYPTION_KEY`
- **CORS**: Firebase Hosting 도메인만 허용
- **파일 업로드**: 최대 20MB/파일, PDF/이미지 MIME 검증

## 9. 에러 처리

| 에러 | 처리 |
|------|------|
| NB 쿠키 만료 | 생성 중단, "재인증 필요" 푸시 |
| Audio 생성 타임아웃/실패 | 재시도 2회 → 수동 트리거 |
| 이미지→PDF 변환 실패 | 해당 소스 스킵, 나머지로 진행 |
| Browserless 세션 실패 | 에러 표시, 재시도 유도 |
| Storage 용량 초과 | 업로드 차단, 안내 |
| 소스 0개 | 스킵, "소스 없음" 푸시 |
