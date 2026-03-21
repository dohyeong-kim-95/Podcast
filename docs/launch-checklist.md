# Launch Checklist

이 문서는 `podcast.bubblelab.dev` 기준의 Supabase 출시 체크리스트입니다.

## 1. 로컬 확인

- [ ] `frontend/.env.example`, `backend/.env.example`이 실제 코드와 맞다
- [ ] [migration_tasks.md](/home/kimdohyeong/Working_kdh/1_Projects/002_notebooklm_py/Podcast/migration_tasks.md), [docs/prd.md](/home/kimdohyeong/Working_kdh/1_Projects/002_notebooklm_py/Podcast/docs/prd.md), [docs/trd.md](/home/kimdohyeong/Working_kdh/1_Projects/002_notebooklm_py/Podcast/docs/trd.md)가 현재 구조와 맞다
- [ ] `cd frontend && npm run build`
- [ ] `python -m compileall backend/app`
- [ ] `bash -n scripts/smoke-vercel-launch.sh`

## 2. Supabase

- [ ] 프로젝트 URL 확인: `https://ocjsumocbjrfxgavmjze.supabase.co`
- [ ] `Project Settings -> API`에서 `anon key`, `service_role key`를 확보했다
- [ ] SQL Editor에서 [supabase/migrations/20260320_init.sql](/home/kimdohyeong/Working_kdh/1_Projects/002_notebooklm_py/Podcast/supabase/migrations/20260320_init.sql)을 실행했다
- [ ] Storage에 private 버킷 `sources`, `podcasts`를 만들었다
- [ ] `Authentication -> URL Configuration`의 `Site URL`을 `https://podcast.bubblelab.dev`로 설정했다
- [ ] Google provider를 활성화했다
- [ ] Google OAuth 클라이언트에 Supabase가 안내하는 callback URL(`https://ocjsumocbjrfxgavmjze.supabase.co/auth/v1/callback`)을 등록했다
- [ ] Auth redirect URL에 아래를 추가했다

```text
https://podcast.bubblelab.dev/auth/callback
http://localhost:3000/auth/callback
```

## 3. Vercel

- [ ] 저장소를 Vercel에 연결했다
- [ ] root를 `frontend/`로 설정했다
- [ ] `podcast.bubblelab.dev`를 연결했다
- [ ] 아래 env를 입력했다

```env
NEXT_PUBLIC_SUPABASE_URL=https://ocjsumocbjrfxgavmjze.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=...
NEXT_PUBLIC_WEB_PUSH_PUBLIC_KEY=...
NEXT_PUBLIC_API_BASE_URL=https://<cloud-run-service>.run.app
```

- [ ] `STATIC_EXPORT=1`을 넣지 않았다
- [ ] env 변경 후 프로덕션을 다시 배포했다

## 4. Cloud Run

- [ ] 서비스가 최신 코드로 배포됐다
- [ ] 아래 env/secrets가 반영됐다

```env
SUPABASE_URL=https://ocjsumocbjrfxgavmjze.supabase.co
SUPABASE_ANON_KEY=...
SUPABASE_SERVICE_ROLE_KEY=...
SUPABASE_DB_URL=postgresql://...
SUPABASE_STORAGE_BUCKET_SOURCES=sources
SUPABASE_STORAGE_BUCKET_PODCASTS=podcasts
ALLOWED_EMAILS=...
CORS_ORIGINS=https://podcast.bubblelab.dev
CLOUD_RUN_URL=https://<cloud-run-service>.run.app
SCHEDULER_SERVICE_ACCOUNT=<scheduler-service-account-email>
NB_COOKIE_ENCRYPTION_KEY=...
REAUTH_HOST_BASE_URL=https://reauth.bubblelab.dev
REAUTH_HOST_API_KEY=...
REAUTH_CALLBACK_TOKEN=...
VAPID_PUBLIC_KEY=...
VAPID_PRIVATE_KEY=...
VAPID_SUBJECT=mailto:admin@bubblelab.dev
```

- [ ] `GET /health`가 200을 반환한다

## 5. MiniPC Reauth Host

- [ ] `reauth.bubblelab.dev`를 miniPC에 연결했다
- [ ] [docs/mini-pc-reauth.md](/home/kimdohyeong/Working_kdh/1_Projects/002_notebooklm_py/Podcast/docs/mini-pc-reauth.md) 기준으로 `reauth_host/`를 배포했다
- [ ] 아래 env가 miniPC `.env`에 반영됐다

```env
REAUTH_HOST_PUBLIC_BASE_URL=https://reauth.bubblelab.dev
REAUTH_PUBLIC_HOSTNAME=reauth.bubblelab.dev
REAUTH_HOST_API_KEY=...
```

- [ ] Vercel DNS에 `reauth` A 레코드를 추가했다
- [ ] 공유기에서 `80`, `443`을 miniPC로 포트포워딩했다
- [ ] `https://reauth.bubblelab.dev/health`가 200을 반환한다

## 6. Cloud Scheduler

- [ ] `POST /api/generate` 잡을 만들었다
  - 스케줄: `40 6 * * *`
  - 타임존: `Asia/Seoul`
- [ ] `POST /api/remind-download` 잡을 만들었다
  - 스케줄: `0 22 * * *`
  - 타임존: `Asia/Seoul`
- [ ] 두 잡 모두 OIDC로 Cloud Run을 호출한다

## 7. 실기기 검증

- [ ] 아래 스모크 스크립트를 실행했다

```bash
APP_URL=https://podcast.bubblelab.dev \
API_URL=https://<cloud-run-service>.run.app \
./scripts/smoke-vercel-launch.sh
```

- [ ] `https://podcast.bubblelab.dev`에서 Google 로그인 성공
- [ ] `/upload`, `/memory`, `/settings` 접근 가능
- [ ] PDF와 이미지 업로드 성공
- [ ] `POST /api/generate/me` 이후 생성 완료 확인
- [ ] 오디오 재생/다운로드/피드백 저장 확인
- [ ] 휴대폰에서 `viewerUrl`을 열어 원격 Chromium 재인증 성공
- [ ] PWA 설치 프롬프트 확인
- [ ] 알림 권한 허용 및 PushSubscription 저장 확인
- [ ] 생성 완료 알림 수신 확인
- [ ] 다운로드 리마인더 알림 수신 확인

## 8. 문제 발생 시 우선 확인

### 로그인 실패

- Supabase Google provider 활성화 여부
- redirect URL 등록 여부
- `NEXT_PUBLIC_SUPABASE_URL`
- `NEXT_PUBLIC_SUPABASE_ANON_KEY`

### API 호출 실패

- `NEXT_PUBLIC_API_BASE_URL`
- `CORS_ORIGINS`
- Cloud Run 배포 URL

### NotebookLM 재인증 실패

- `REAUTH_HOST_BASE_URL`
- `REAUTH_HOST_API_KEY`
- `REAUTH_CALLBACK_TOKEN`
- miniPC의 `reauth_host`와 `caddy` 컨테이너 상태

### 푸시 미수신

- `NEXT_PUBLIC_WEB_PUSH_PUBLIC_KEY`
- `VAPID_PRIVATE_KEY`
- 브라우저 알림 권한
- `push_subscriptions` row 저장 여부
