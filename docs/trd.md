# Podcast — TRD (Supabase + Cloud Run + Vercel + MiniPC Reauth Host)

## 1. 목표

현재 코드베이스를 기준으로, 프론트엔드는 Vercel의 `podcast.bubblelab.dev`에서 서비스하고 백엔드는 FastAPI + Cloud Run을 유지하되, Firebase 의존성을 Supabase와 표준 Web Push로 교체한다.

## 2. 시스템 아키텍처

```text
사용자 브라우저 / 모바일 PWA
        │
        ▼
Vercel (Next.js 14 App Router)
- custom domain: podcast.bubblelab.dev
- Supabase Google OAuth
- service worker / manifest / app shell
        │
        │ HTTPS + Supabase access token
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
        ├─ Supabase Auth
        ├─ Supabase Postgres
        ├─ Supabase Storage
        ├─ MiniPC reauth host (reauth.bubblelab.dev)
        ├─ notebooklm-py
        └─ Web Push (VAPID)

Cloud Scheduler
- 06:40 KST -> POST /api/generate
- 22:00 KST -> POST /api/remind-download
```

## 3. 프론트엔드 설계

### 페이지 구조

```text
/login
/auth/callback
/
/upload
/memory
/settings
/offline
```

### 인증

- `@supabase/supabase-js`를 사용한다
- 로그인은 `signInWithOAuth({ provider: "google" })`
- redirect URL은 `https://podcast.bubblelab.dev/auth/callback`
- callback 페이지에서 `exchangeCodeForSession()`으로 세션을 확정한다
- 프론트는 Supabase access token을 백엔드 `Authorization: Bearer`로 전달한다

### PWA / 푸시

- `manifest.json`과 `sw.js`를 유지한다
- 서비스 워커는 표준 `push` / `notificationclick` 이벤트를 처리한다
- 브라우저 `PushManager.subscribe()` 결과를 `PushSubscription` JSON으로 백엔드에 저장한다

## 4. 백엔드 설계

### 인증 레이어

- 사용자 API: Supabase access token 검증 + `ALLOWED_EMAILS` 화이트리스트
- 내부 스케줄러 API: Google OIDC 토큰 검증 + `CLOUD_RUN_URL` audience 확인 + `SCHEDULER_SERVICE_ACCOUNT` 이메일 확인

### 데이터 레이어

- `psycopg`로 Supabase Postgres에 직접 연결한다
- 이유:
  - `generate/me` 락을 SQL transaction으로 처리하기 쉽다
  - 상태 전이를 row 단위로 명확히 관리할 수 있다

### 파일 레이어

- `sources` 버킷:
  - `sources/{uid}/{YYYY-MM-DD}/{sourceId}.{ext}`
  - 이미지 업로드 시 같은 basename의 `.pdf` 변환본 저장
- `podcasts` 버킷:
  - `podcasts/{uid}/{YYYY-MM-DD}.mp3`
- 재생 URL은 백엔드가 서명 URL을 생성해 내려준다

### 푸시 레이어

- FCM 대신 `pywebpush`
- 사용자별 `PushSubscription` JSON을 저장한다
- payload는 `{ title, body, data: { url } }` 형태를 사용한다

## 5. 데이터 모델

SQL migration 기준 파일: [supabase/migrations/20260320_init.sql](/home/kimdohyeong/Working_kdh/1_Projects/002_notebooklm_py/Podcast/supabase/migrations/20260320_init.sql)

주요 테이블:

- `profiles`
- `user_memory`
- `sources`
- `podcasts`
- `nb_sessions`
- `nb_auth_sessions`
- `push_subscriptions`

핵심 인덱스:

- `sources(user_id, window_date, uploaded_at)`
- `podcasts(user_id, date)` unique
- `nb_auth_sessions(user_id, updated_at desc)`

## 6. 주요 플로우

### 로그인

1. 프론트가 Supabase Google OAuth를 시작한다.
2. `/auth/callback`에서 세션을 확정한다.
3. 프론트가 `POST /api/auth/verify`를 호출한다.
4. 백엔드가 토큰과 화이트리스트를 검증하고 `profiles`를 upsert 한다.

### 소스 업로드

1. 백엔드가 MIME + 매직바이트를 검증한다.
2. 원본을 Supabase Storage `sources` 버킷에 저장한다.
3. 메타데이터를 `sources` 테이블에 저장한다.
4. 이미지면 PDF 변환본을 추가 저장하고 row를 갱신한다.

### 팟캐스트 생성

1. 스케줄러 또는 수동 요청이 들어온다.
2. 백엔드는 SQL row lock으로 당일 상태를 선점한다.
3. 수집 윈도우의 소스를 조회해 PDF만 NotebookLM에 전달한다.
4. 생성된 MP3를 `podcasts` 버킷에 저장한다.
5. `podcasts` row를 `completed`로 갱신하고 웹 푸시를 보낸다.

### NotebookLM 재인증

1. 백엔드가 miniPC reauth host에 새 세션 생성을 요청한다.
2. `nb_auth_sessions`에 `pending` 상태와 `viewer_url`을 저장한다.
3. 사용자가 휴대폰에서 `viewer_url`을 열고 원격 Chromium 안에서 NotebookLM 로그인을 완료한다.
4. miniPC reauth host가 `storage_state`를 백엔드 콜백으로 전달한다.
5. 백엔드가 `storage_state`를 암호화해 `nb_sessions`에 저장한다.

## 7. 환경변수

### 프론트엔드

- `NEXT_PUBLIC_SUPABASE_URL`
- `NEXT_PUBLIC_SUPABASE_ANON_KEY`
- `NEXT_PUBLIC_WEB_PUSH_PUBLIC_KEY`
- `NEXT_PUBLIC_API_BASE_URL`

### 백엔드

- `SUPABASE_URL`
- `SUPABASE_ANON_KEY`
- `SUPABASE_SERVICE_ROLE_KEY`
- `SUPABASE_DB_URL`
- `SUPABASE_STORAGE_BUCKET_SOURCES`
- `SUPABASE_STORAGE_BUCKET_PODCASTS`
- `VAPID_PUBLIC_KEY`
- `VAPID_PRIVATE_KEY`
- `VAPID_SUBJECT`
- `CORS_ORIGINS`
- `ALLOWED_EMAILS`
- `CLOUD_RUN_URL`
- `SCHEDULER_SERVICE_ACCOUNT`
- `NB_COOKIE_ENCRYPTION_KEY`
- `REAUTH_HOST_BASE_URL`
- `REAUTH_HOST_API_KEY`
- `REAUTH_CALLBACK_TOKEN`

## 8. 남은 운영 리스크

- Supabase OAuth provider 설정과 redirect URL 오설정
- Supabase Storage bucket/policy 미구성
- VAPID key pair 미설정
- miniPC reauth host 가용성과 NotebookLM 외부 변화
