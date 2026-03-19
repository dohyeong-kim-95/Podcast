# Podcast — TRD (Vercel + Cloud Run)

## 1. 목표

현재 코드베이스를 기준으로, 프론트엔드는 Vercel의 `podcast.bubblelab.dev`에서 서비스하고 백엔드는 FastAPI + Cloud Run을 유지하는 운영 구조를 정의한다.

핵심 판단은 다음과 같다.

- 프론트엔드만 Vercel로 올린다
- 백엔드 재작성 없이 기존 FastAPI를 계속 사용한다
- Firebase Auth redirect, PWA, 푸시, NotebookLM 재인증이 커스텀 도메인에서 실제로 동작해야 한다
- `STATIC_EXPORT=1` 기반 Firebase Hosting 배포는 보조 경로로 남기되, 기본 프로덕션 경로는 아니다

## 2. 시스템 아키텍처

```text
사용자 브라우저 / 모바일 PWA
        │
        ▼
Vercel (Next.js 14 App Router)
- custom domain: podcast.bubblelab.dev
- /__/auth/* rewrite -> <firebase-project>.firebaseapp.com
- static assets / service worker / app shell
        │
        │ HTTPS + Firebase ID token
        ▼
Cloud Run (FastAPI)
- /api/auth/verify
- /api/sources/*
- /api/generate, /api/generate/me
- /api/podcasts/*
- /api/memory
- /api/nb-session/*
- /api/push-token, /api/remind-download
        │
        ├─ Firestore
        ├─ Firebase Storage
        ├─ Firebase Auth Admin
        ├─ Firebase Cloud Messaging
        ├─ Browserless
        └─ notebooklm-py

Cloud Scheduler
- 06:40 KST -> POST /api/generate
- 22:00 KST -> POST /api/remind-download
```

## 3. 배포 결정

### 3.1 프론트엔드
- 플랫폼: Vercel
- 프로젝트 루트: `frontend/`
- 빌드: `npm run build`
- 런타임: 일반 Next.js 빌드
- 커스텀 도메인: `podcast.bubblelab.dev`

### 3.2 백엔드
- 플랫폼: Google Cloud Run
- 이미지: `backend/Dockerfile`
- 포트: `8080`
- 인증: Firebase ID 토큰 + Scheduler OIDC
- 권장 역할: 앱 API 전담

### 3.3 왜 이 구조를 유지하는가
- 이미 코드가 이 구조로 대부분 구현되어 있다
- Vercel은 프론트 배포와 커스텀 도메인 운영에 적합하다
- NotebookLM, Browserless, Firebase Admin, 장시간 오디오 생성은 Cloud Run 쪽이 더 자연스럽다
- 리스크가 가장 낮다

## 4. 프론트엔드 설계

### 4.1 페이지 구조

```text
/login              Google 로그인
/                   오늘의 팟캐스트, 상태 배너, 재생, 재시도
/upload             소스 업로드/목록/삭제
/memory             메모리 설정
/settings           NotebookLM 세션 + 푸시 알림 설정
/offline            오프라인 폴백
```

### 4.2 인증 처리
- Firebase Auth의 `signInWithRedirect()` 사용
- 로그인 이후 브라우저에서 Cloud Run `POST /api/auth/verify` 호출
- 백엔드는 ID 토큰 검증 후 화이트리스트 체크
- 화이트리스트 거부 시 프론트는 즉시 로그아웃

### 4.3 Vercel에서의 Firebase redirect 처리

Vercel에서 `signInWithRedirect()`를 안정적으로 쓰기 위해 다음 전제를 둔다.

- `NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN=podcast.bubblelab.dev`
- `frontend/next.config.mjs`에서 `/__/auth/:path*`를 Firebase helper origin으로 rewrite
- `FIREBASE_AUTH_HELPER_ORIGIN` 기본값은 `https://<project>.firebaseapp.com`
- 서비스 워커는 `/__/` 네임스페이스를 가로채지 않는다

이 조합이 맞아야 `https://podcast.bubblelab.dev/__/auth/handler`가 정상 동작한다.

### 4.4 PWA
- `manifest.json` 제공
- `sw.js` 등록
- 기본 app shell 캐시: `/`, `/offline`, `/manifest.json`
- foreground FCM 수신 시 브라우저 알림 표시
- 설치 프롬프트 제공

## 5. 백엔드 설계

### 5.1 라우터 구성

| 영역 | 경로 |
|------|------|
| health | `GET /health` |
| auth | `POST /api/auth/verify` |
| sources | `POST /api/sources/upload`, `GET /api/sources`, `DELETE /api/sources/{source_id}` |
| generation | `POST /api/generate`, `POST /api/generate/me` |
| podcast | `GET /api/podcasts/today`, `POST /api/podcasts/{podcast_id}/feedback`, `POST /api/podcasts/{podcast_id}/downloaded` |
| memory | `GET /api/memory`, `PUT /api/memory` |
| NB session | `POST /api/nb-session/start-auth`, `GET /api/nb-session/poll/{session_id}`, `GET /api/nb-session/status` |
| push | `POST /api/push-token`, `POST /api/remind-download` |

### 5.2 인증 레이어
- 사용자 API: Firebase ID 토큰 검증 + `ALLOWED_EMAILS` 화이트리스트
- 내부 스케줄러 API: Google OIDC 토큰 검증 + `CLOUD_RUN_URL` audience 확인 + `SCHEDULER_SERVICE_ACCOUNT` 이메일 확인

### 5.3 생성 파이프라인
- 수집 윈도우: 전일 06:40 KST ~ 당일 06:40 KST
- 사용자별 Firestore 상태 문서를 보고 중복 실행 방지
- 유효한 PDF 소스만 NotebookLM에 전달
- 생성 완료 후 Storage에 MP3 저장
- 이전 날짜 오디오는 삭제
- 실패 시 `retry_1`, `retry_2`, `failed` 상태로 관리

### 5.4 NotebookLM 재인증
- Browserless 세션 URL과 viewer URL은 환경변수 템플릿으로 생성
- 프론트는 새 탭을 열고, 백엔드는 Browserless에 연결해 NotebookLM 로그인 완료를 폴링한다
- 완료 시 `storage_state`를 암호화해 Firestore에 저장한다

## 6. 데이터 모델

### 6.1 `users/{uid}`

```json
{
  "email": "user@gmail.com",
  "displayName": "사용자",
  "createdAt": "timestamp",
  "lastLoginAt": "timestamp",
  "fcmToken": "token",
  "fcmTokenUpdatedAt": "timestamp",
  "memory": {
    "interests": "AI, 투자",
    "tone": "친근하지만 정확하게",
    "preferredTone": "친근하지만 정확하게",
    "depth": "실무자 관점",
    "preferredDepth": "실무자 관점",
    "custom": "핵심 요약 먼저",
    "customInstructions": "핵심 요약 먼저",
    "feedbackHistory": [
      { "date": "2026-03-18", "rating": "good" }
    ]
  }
}
```

### 6.2 `users/{uid}/nb_session/current`

```json
{
  "storageState": "encrypted-string",
  "lastUpdated": "timestamp",
  "expiresAt": "timestamp",
  "status": "valid",
  "authFlow": "new_tab"
}
```

파생 상태는 API에서 `valid | expiring_soon | expired | missing`으로 정규화한다.

### 6.3 `users/{uid}/nb_auth_sessions/{sessionId}`

```json
{
  "status": "pending | running | completed | timed_out | failed",
  "viewerUrl": "https://...",
  "authFlow": "new_tab",
  "startedAt": "timestamp",
  "updatedAt": "timestamp",
  "completedAt": "timestamp",
  "error": null
}
```

추가로 `users/{uid}/nb_auth_sessions/current` 문서에 현재 진행 중인 세션을 복제해 빠르게 조회한다.

### 6.4 `sources/{sourceId}`

```json
{
  "uid": "user_uid",
  "fileName": "capture.png",
  "originalType": "image/png",
  "convertedType": "application/pdf",
  "originalStoragePath": "sources/{uid}/{date}/{sourceId}.png",
  "convertedStoragePath": "sources/{uid}/{date}/{sourceId}.pdf",
  "uploadedAt": "timestamp",
  "windowDate": "2026-03-19",
  "status": "uploaded | ready | used"
}
```

### 6.5 `podcasts/{uid-YYYY-MM-DD}`

```json
{
  "uid": "user_uid",
  "date": "2026-03-19",
  "status": "generating | retry_1 | retry_2 | completed | failed | no_sources",
  "sourceIds": ["source1", "source2"],
  "sourceCount": 2,
  "audioPath": "podcasts/{uid}/2026-03-19.mp3",
  "durationSeconds": 600,
  "generatedAt": "timestamp",
  "instructionsUsed": "string",
  "error": null,
  "feedback": "good",
  "downloaded": false
}
```

## 7. 주요 플로우

### 7.1 로그인 플로우
1. 사용자가 `podcast.bubblelab.dev/login`에서 Google 로그인을 시작한다.
2. Firebase Redirect Helper가 `/__/auth/*` rewrite를 통해 처리된다.
3. 로그인 성공 후 프론트가 Cloud Run `POST /api/auth/verify`를 호출한다.
4. 백엔드가 화이트리스트를 검증하고 Firestore 사용자 문서를 upsert 한다.

### 7.2 업로드 플로우
1. 브라우저가 파일을 선택한다.
2. 프론트는 XHR로 업로드 진행률을 표시한다.
3. 백엔드는 MIME + 매직바이트 검증 후 Storage에 원본을 저장한다.
4. 이미지면 PDF 변환본도 저장하고 `convertedStoragePath`를 기록한다.
5. Firestore `sources` 문서가 생성된다.

### 7.3 자동 생성 플로우
1. Cloud Scheduler가 `POST /api/generate`를 호출한다.
2. 백엔드는 `ALLOWED_EMAILS`에 있는 사용자 문서를 조회한다.
3. 사용자별로 소스 윈도우, 메모리, NB 세션을 읽는다.
4. NotebookLM에 소스를 추가하고 오디오를 생성한다.
5. 결과 MP3를 Storage에 저장하고, Firestore 상태를 `completed`로 갱신한다.
6. FCM으로 알림을 보낸다.

### 7.4 수동 재생성 플로우
1. 사용자가 앱 홈에서 `다시 생성`을 누른다.
2. 백엔드는 Firestore transaction으로 해당 날짜의 생성 권한을 선점한다.
3. 백그라운드 태스크로 동일한 생성 파이프라인을 실행한다.

### 7.5 재인증 플로우
1. 사용자가 설정 화면에서 재인증을 시작한다.
2. 백엔드는 Browserless 세션 정보를 만들고 Firestore에 pending 상태를 저장한다.
3. 프론트는 새 탭으로 viewer URL을 연다.
4. 서버가 NotebookLM 로그인 완료를 감지하면 storage state를 저장한다.
5. 프론트는 poll API로 완료 상태를 확인한다.

### 7.6 푸시 토큰 동기화
- 앱 진입, 포커스 복귀, foreground message 수신 시점에 FCM 토큰 동기화
- 로컬 캐시 토큰과 다를 때만 `POST /api/push-token` 호출

## 8. 환경변수

### 8.1 Vercel 프론트엔드

| 이름 | 용도 |
|------|------|
| `NEXT_PUBLIC_FIREBASE_API_KEY` | Firebase Web SDK |
| `NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN` | 프로덕션에서는 `podcast.bubblelab.dev` |
| `NEXT_PUBLIC_FIREBASE_PROJECT_ID` | Firebase 프로젝트 ID |
| `NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET` | Firebase Storage 버킷 |
| `NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID` | FCM sender ID |
| `NEXT_PUBLIC_FIREBASE_APP_ID` | Firebase app ID |
| `NEXT_PUBLIC_FIREBASE_VAPID_KEY` | Web Push VAPID 키 |
| `NEXT_PUBLIC_API_BASE_URL` | Cloud Run API base URL |
| `FIREBASE_AUTH_HELPER_ORIGIN` | 보통 `https://<project>.firebaseapp.com` |

### 8.2 Cloud Run 백엔드

| 이름 | 용도 |
|------|------|
| `GOOGLE_APPLICATION_CREDENTIALS` | 로컬 개발용 서비스 계정 키 경로 |
| `ALLOWED_EMAILS` | 화이트리스트 이메일 목록 |
| `CORS_ORIGINS` | 허용 origin. 프로덕션은 `https://podcast.bubblelab.dev` 포함 |
| `CLOUD_RUN_URL` | Scheduler OIDC audience |
| `SCHEDULER_SERVICE_ACCOUNT` | Scheduler가 사용할 서비스 계정 이메일 |
| `NB_COOKIE_ENCRYPTION_KEY` | NotebookLM 세션 암호화 키 |
| `BROWSERLESS_TOKEN` | Browserless 인증 토큰 |
| `BROWSERLESS_CONNECT_URL_TEMPLATE` | CDP 연결 URL 템플릿 |
| `BROWSERLESS_VIEWER_URL_TEMPLATE` | 사용자용 viewer URL 템플릿 |
| `NB_AUTH_TARGET_URL` | 기본값 `https://notebooklm.google.com` |
| `NB_AUTH_TIMEOUT_SECONDS` | 재인증 타임아웃 |
| `AUDIO_TIMEOUT_SECONDS` | 오디오 생성 타임아웃 |
| `GENERATE_MAX_CONCURRENCY` | 동시 생성 제한 |
| `NB_SESSION_EXPIRING_SOON_DAYS` | 만료 임박 기준 일수 |

## 9. 운영 체크포인트

### 9.1 Vercel
- 프로젝트 root를 `frontend`로 둔다
- `STATIC_EXPORT=1`을 프로덕션 Vercel 환경에 넣지 않는다
- `podcast.bubblelab.dev`를 Vercel 프로젝트에 연결한다

### 9.2 Firebase Console
- Authentication Authorized domains에 `podcast.bubblelab.dev` 추가
- 필요 시 OAuth redirect handler 경로 허용

### 9.3 Cloud Run
- `CORS_ORIGINS=https://podcast.bubblelab.dev`
- ADC 또는 서비스 계정 권한으로 Firestore, Storage, FCM 사용 가능해야 한다

### 9.4 Cloud Scheduler
- 생성 잡: `40 6 * * *` Asia/Seoul
- 리마인더 잡: `0 22 * * *` Asia/Seoul
- 두 잡 모두 OIDC로 Cloud Run 호출

## 10. 알려진 리스크

- Browserless 새 탭 플로우는 실제 모바일 기기에서 반드시 검증해야 한다
- FCM Web Push는 브라우저별 제약이 있으므로 실사용 브라우저 범위를 정해야 한다
- `notebooklm-py`와 쿠키 기반 인증은 외부 서비스 변경에 취약하다
- 현재 API는 `run.app` 도메인을 사용하므로 CORS/운영환경 설정 실수가 가장 흔한 장애 원인이 된다
