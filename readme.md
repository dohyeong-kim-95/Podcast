# Podcast

하루 동안 모은 PDF와 이미지 소스를 다음 날 아침 한국어 오디오로 들을 수 있게 해주는 모바일 퍼스트 PWA입니다.

- 프로덕션 프론트엔드: `https://podcast.bubblelab.dev`
- 프론트엔드 배포: Vercel
- 백엔드 배포: FastAPI on Cloud Run
- 인증/데이터/스토리지: Supabase

## 현재 아키텍처

| 구성 | 선택 |
|------|------|
| 프론트엔드 | Next.js 14 App Router PWA |
| 프론트 호스팅 | Vercel |
| 백엔드 | Python FastAPI |
| 백엔드 호스팅 | Google Cloud Run |
| 인증 | Supabase Auth + 백엔드 화이트리스트 검증 |
| 데이터 | Supabase Postgres |
| 파일 저장 | Supabase Storage |
| 푸시 | 표준 Web Push (VAPID) |
| NotebookLM 재인증 | self-hosted remote browser on miniPC |
| 스케줄링 | Cloud Scheduler |

## 핵심 흐름

1. 낮 동안 PDF/이미지를 업로드합니다.
2. 매일 `06:40 KST`에 Cloud Scheduler가 생성 작업을 시작합니다.
3. NotebookLM이 오디오를 만들면 웹 푸시 알림을 보냅니다.
4. 사용자는 앱에서 재생하거나 다운로드합니다.

## 프로젝트 구조

```text
backend/   FastAPI API, generation pipeline, Supabase/Postgres integration
frontend/  Next.js app, PWA, Supabase Auth client
reauth_host/ MiniPC-hosted remote browser service for mobile NotebookLM reauth
docs/      PRD, TRD, tasks, deployment notes
supabase/  SQL migration assets
.codex/    project agents
```

## 로컬 개발

### 백엔드

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8080
```

### 프론트엔드

```bash
cd frontend
npm install
npm run dev
```

## 환경변수

- 프론트엔드 예시: [frontend/.env.example](/home/kimdohyeong/Working_kdh/1_Projects/002_notebooklm_py/Podcast/frontend/.env.example)
- 백엔드 예시: [backend/.env.example](/home/kimdohyeong/Working_kdh/1_Projects/002_notebooklm_py/Podcast/backend/.env.example)

프로덕션에서 중요한 값은 아래입니다.

- 프론트엔드: `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`, `NEXT_PUBLIC_WEB_PUSH_PUBLIC_KEY`, `NEXT_PUBLIC_API_BASE_URL`
- 백엔드: `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_DB_URL`, `CORS_ORIGINS`, `ALLOWED_EMAILS`, `CLOUD_RUN_URL`, `SCHEDULER_SERVICE_ACCOUNT`, `NB_COOKIE_ENCRYPTION_KEY`, `REAUTH_HOST_BASE_URL`, `REAUTH_HOST_API_KEY`, `REAUTH_CALLBACK_TOKEN`, `VAPID_PRIVATE_KEY`, `VAPID_SUBJECT`
- 미니PC reauth host: [reauth_host/.env.example](/home/kimdohyeong/Working_kdh/1_Projects/002_notebooklm_py/Podcast/reauth_host/.env.example)

## 배포 원칙

### 프론트엔드

- Vercel 프로젝트 root는 `frontend/`
- 프로덕션 도메인은 `podcast.bubblelab.dev`
- Supabase Auth redirect URL에 `https://podcast.bubblelab.dev/auth/callback`을 넣어야 합니다
- `STATIC_EXPORT=1`은 Vercel 프로덕션 배포에 사용하지 않습니다

### 백엔드

- Cloud Run에 `backend/`를 배포합니다
- Supabase Postgres와 Supabase Storage를 사용합니다
- 프로덕션 origin에 맞춰 `CORS_ORIGINS=https://podcast.bubblelab.dev`를 설정해야 합니다
- Scheduler 호출용 `CLOUD_RUN_URL`, `SCHEDULER_SERVICE_ACCOUNT`가 필요합니다
- NotebookLM 재인증용 miniPC host를 `reauth.bubblelab.dev` 같은 별도 서브도메인으로 노출해야 합니다

### MiniPC Reauth Host

- `reauth_host/`를 항상 켜져 있는 miniPC에 배포합니다
- public hostname은 `reauth.bubblelab.dev`처럼 별도 origin을 사용합니다
- Vercel DNS에서 `reauth` 레코드를 miniPC 공인 IP로 연결하고, 공유기에서 `80/443` 포트포워딩을 해야 합니다
- setup guide: [MiniPC Reauth Host](/home/kimdohyeong/Working_kdh/1_Projects/002_notebooklm_py/Podcast/docs/mini-pc-reauth.md)

## 검증

```bash
cd frontend && npm run build
python -m compileall backend/app
bash -n scripts/smoke-vercel-launch.sh
```

배포 후 기본 HTTP 스모크 체크:

```bash
APP_URL=https://podcast.bubblelab.dev \
API_URL=https://your-cloud-run-service.run.app \
./scripts/smoke-vercel-launch.sh
```

## 문서

- [Migration Tasks](/home/kimdohyeong/Working_kdh/1_Projects/002_notebooklm_py/Podcast/migration_tasks.md)
- [PRD](/home/kimdohyeong/Working_kdh/1_Projects/002_notebooklm_py/Podcast/docs/prd.md)
- [TRD](/home/kimdohyeong/Working_kdh/1_Projects/002_notebooklm_py/Podcast/docs/trd.md)
- [Launch Tasks](/home/kimdohyeong/Working_kdh/1_Projects/002_notebooklm_py/Podcast/docs/tasks.md)
- [Launch Checklist](/home/kimdohyeong/Working_kdh/1_Projects/002_notebooklm_py/Podcast/docs/launch-checklist.md)
- [MiniPC Reauth Host](/home/kimdohyeong/Working_kdh/1_Projects/002_notebooklm_py/Podcast/docs/mini-pc-reauth.md)
