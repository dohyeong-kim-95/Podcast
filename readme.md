# Podcast

하루 동안 모은 PDF와 이미지 소스를 다음 날 아침 한국어 오디오 팟캐스트로 만들어 주는 모바일 퍼스트 PWA입니다. 프론트는 Vercel, 백엔드는 Cloud Run, 인증/데이터/스토리지는 Supabase, NotebookLM 재인증은 miniPC 기반 self-hosted remote browser로 운영합니다.

## 현재 서비스 위치

| 구성 | 현재 서비스 위치 | 비고 |
|------|------------------|------|
| 프론트엔드 PWA | Vercel, `https://podcast.bubblelab.dev` | 사용자 앱 진입점 |
| 백엔드 API | Google Cloud Run, 서비스명 `podcast-api` (`asia-northeast3`) | 실제 `run.app` URL은 Cloud Run 서비스 URL과 Vercel env를 기준으로 확인 |
| NotebookLM 재인증 호스트 | miniPC + Docker + Caddy, `https://reauth.bubblelab.dev` | 모바일에서 원격 브라우저로 직접 로그인 |
| 인증 | Supabase Auth | Google OAuth + 백엔드 화이트리스트 검증 |
| DB / 파일 저장 | Supabase Postgres / Supabase Storage | 사용자 메모리, 세션, 팟캐스트 메타데이터, 업로드 파일 |
| 스케줄링 | Google Cloud Scheduler | 매일 `06:40 KST` 생성, `22:00 KST` 리마인드 |
| 푸시 알림 | Web Push (VAPID) | PWA 다운로드 리마인드, 생성 완료 알림 |

## 앱이 하는 일

1. 사용자가 낮 동안 PDF 또는 이미지를 업로드합니다.
2. 시스템이 한국 시간 기준 생성 윈도우에 들어온 소스만 모읍니다.
3. NotebookLM으로 한국어 오디오를 생성합니다.
4. 생성이 끝나면 앱에서 바로 재생하거나 다운로드할 수 있습니다.
5. 필요하면 사용자가 휴대폰에서 NotebookLM 세션을 다시 인증할 수 있습니다.

## 핵심 기능

- Google OAuth 로그인
- PDF / 이미지 업로드
- 사용자 메모리 설정 기반 프롬프트 생성
- 일일 자동 생성
- 수동 즉시 생성 버튼
- PWA 설치 및 Web Push
- 모바일 원격 브라우저 기반 NotebookLM 재인증

## 시스템 구성

| 구성 | 기술 |
|------|------|
| 프론트엔드 | Next.js 14 App Router, TypeScript, Tailwind, PWA |
| 백엔드 | FastAPI, Python 3.11 |
| 인증 | Supabase Auth |
| 데이터베이스 | Supabase Postgres |
| 파일 저장 | Supabase Storage |
| 알림 | pywebpush / VAPID |
| 재인증 호스트 | FastAPI + noVNC/websockify + Chromium + Playwright + Caddy |

## 저장소 구조

```text
backend/        FastAPI API, generation pipeline, Supabase integration
frontend/       Next.js PWA
reauth_host/    miniPC에서 띄우는 원격 브라우저 서비스
docs/           PRD, TRD, 배포 메모, 체크리스트
supabase/       SQL migration assets
scripts/        스모크 체크 스크립트
```

## 주요 동작 흐름

### 1. 로그인

- 프론트엔드는 Supabase Google OAuth로 로그인합니다.
- 백엔드는 액세스 토큰을 다시 검증하고, `ALLOWED_EMAILS` 기준으로 접근을 제한할 수 있습니다.

### 2. 업로드

- 사용자는 PDF나 이미지를 업로드합니다.
- 이미지는 서버에서 PDF로 변환될 수 있습니다.
- 업로드 파일은 Supabase Storage에 저장되고 메타데이터는 Postgres에 기록됩니다.

### 3. NotebookLM 재인증

- 사용자가 `/settings`에서 재인증을 시작합니다.
- 백엔드는 miniPC의 `reauth_host`에 세션 생성을 요청합니다.
- 사용자는 `https://reauth.bubblelab.dev`에서 원격 Chromium을 열고 휴대폰으로 직접 로그인합니다.
- miniPC가 `storageState`를 추출해 백엔드에 콜백합니다.

### 4. 팟캐스트 생성

- 기본 생성은 Cloud Scheduler가 매일 `06:40 KST`에 시작합니다.
- 사용자는 홈 화면에서 `즉시 팟캐스트 생성` 버튼으로 수동 생성을 시작할 수 있습니다.
- 수동 생성은 하루에 1회만 허용됩니다.
- 생성 완료 후 앱은 오늘자 팟캐스트를 자동으로 표시합니다.

## 로컬 개발

### 프론트엔드

```bash
cd frontend
npm install
npm run dev
```

기본 개발 주소:

```text
http://localhost:3000
```

### 백엔드

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8080
```

기본 개발 주소:

```text
http://localhost:8080
```

### miniPC reauth host

```bash
cd reauth_host
cp .env.example .env
docker compose -f compose.yml up -d --build
```

기본 health check:

```text
https://reauth.bubblelab.dev/health
```

## 환경변수와 비밀정보

실제 `.env`, 비밀키, 인증서, `secrets/` 디렉터리는 커밋하지 않습니다. 저장소에는 예시 파일만 둡니다.

- 프론트엔드 예시: [frontend/.env.example](/home/kimdohyeong/Working_kdh/1_Projects/002_notebooklm_py/Podcast/frontend/.env.example)
- 백엔드 예시: [backend/.env.example](/home/kimdohyeong/Working_kdh/1_Projects/002_notebooklm_py/Podcast/backend/.env.example)
- miniPC reauth host 예시: [reauth_host/.env.example](/home/kimdohyeong/Working_kdh/1_Projects/002_notebooklm_py/Podcast/reauth_host/.env.example)

주요 환경변수:

- 프론트엔드
  - `NEXT_PUBLIC_SUPABASE_URL`
  - `NEXT_PUBLIC_SUPABASE_ANON_KEY`
  - `NEXT_PUBLIC_WEB_PUSH_PUBLIC_KEY`
  - `NEXT_PUBLIC_API_BASE_URL`
- 백엔드
  - `SUPABASE_URL`
  - `SUPABASE_ANON_KEY`
  - `SUPABASE_SERVICE_ROLE_KEY`
  - `SUPABASE_DB_URL`
  - `CORS_ORIGINS`
  - `ALLOWED_EMAILS`
  - `CLOUD_RUN_URL`
  - `SCHEDULER_SERVICE_ACCOUNT`
  - `NB_COOKIE_ENCRYPTION_KEY`
  - `REAUTH_HOST_BASE_URL`
  - `REAUTH_HOST_API_KEY`
  - `REAUTH_CALLBACK_TOKEN`
  - `VAPID_PUBLIC_KEY`
  - `VAPID_PRIVATE_KEY`
  - `VAPID_SUBJECT`
- miniPC reauth host
  - `REAUTH_HOST_PUBLIC_BASE_URL`
  - `REAUTH_PUBLIC_HOSTNAME`
  - `REAUTH_HOST_API_KEY`

## 배포 요약

### 프론트엔드 배포

- 플랫폼: Vercel
- Root Directory: `frontend/`
- 프로덕션 도메인: `podcast.bubblelab.dev`
- Supabase redirect URL:
  - `https://podcast.bubblelab.dev/auth/callback`

### 백엔드 배포

- 플랫폼: Google Cloud Run
- 소스 디렉터리: `backend/`
- 프론트의 `NEXT_PUBLIC_API_BASE_URL`이 가리키는 Cloud Run URL과 일치해야 합니다.
- 프로덕션 CORS는 `https://podcast.bubblelab.dev` 를 허용해야 합니다.

예시:

```bash
gcloud run deploy podcast-api \
  --source backend \
  --region asia-northeast3 \
  --allow-unauthenticated
```

### miniPC reauth host 배포

- 플랫폼: self-hosted miniPC
- 서비스 디렉터리: `reauth_host/`
- 외부 공개 주소: `https://reauth.bubblelab.dev`
- DNS: Vercel DNS에서 `reauth` 레코드를 miniPC 공인 IP로 연결
- 네트워크: 공유기에서 `80/443` 포트포워딩 필요

상세 가이드:

- [MiniPC Reauth Host](/home/kimdohyeong/Working_kdh/1_Projects/002_notebooklm_py/Podcast/docs/mini-pc-reauth.md)

## 기본 검증

```bash
python -m compileall backend/app
bash -n scripts/smoke-vercel-launch.sh
```

배포 후 HTTP 스모크 체크:

```bash
APP_URL=https://podcast.bubblelab.dev \
API_URL=https://your-cloud-run-service.run.app \
./scripts/smoke-vercel-launch.sh
```

수동 확인 항목:

- 로그인 가능
- 업로드 가능
- NotebookLM 재인증 가능
- 즉시 팟캐스트 생성 버튼 동작
- 오늘의 팟캐스트 재생 / 다운로드 가능

## TODO

- 앱 동작 속도 개선
  - 첫 진입 로딩 시간 단축
  - 팟캐스트 생성 대기 UX 개선
  - 생성 진행 상태를 더 세밀하게 표시
  - 안전한 범위에서 소스 준비/업로드 이후 처리를 병렬화

## 참고 문서

- [Migration Tasks](/home/kimdohyeong/Working_kdh/1_Projects/002_notebooklm_py/Podcast/migration_tasks.md)
- [PRD](/home/kimdohyeong/Working_kdh/1_Projects/002_notebooklm_py/Podcast/docs/prd.md)
- [TRD](/home/kimdohyeong/Working_kdh/1_Projects/002_notebooklm_py/Podcast/docs/trd.md)
- [Launch Tasks](/home/kimdohyeong/Working_kdh/1_Projects/002_notebooklm_py/Podcast/docs/tasks.md)
- [Launch Checklist](/home/kimdohyeong/Working_kdh/1_Projects/002_notebooklm_py/Podcast/docs/launch-checklist.md)
- [MiniPC Reauth Host](/home/kimdohyeong/Working_kdh/1_Projects/002_notebooklm_py/Podcast/docs/mini-pc-reauth.md)
