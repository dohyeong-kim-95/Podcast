# Vercel Deployment (`podcast.bubblelab.dev`)

이 프로젝트의 프론트엔드는 Vercel에, 백엔드는 Cloud Run에 배포합니다.

## 1. Vercel 프로젝트

- 저장소 연결
- Root Directory: `frontend`
- Framework Preset: `Next.js`
- Output Directory: 비워둠
- `STATIC_EXPORT=1`은 프로덕션에 넣지 않음

## 2. Vercel env

```env
NEXT_PUBLIC_SUPABASE_URL=https://ocjsumocbjrfxgavmjze.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=...
NEXT_PUBLIC_WEB_PUSH_PUBLIC_KEY=...
NEXT_PUBLIC_API_BASE_URL=https://<cloud-run-service>.run.app
```

## 3. Supabase Auth 설정

Supabase Dashboard -> Authentication -> URL Configuration

Site URL:

```text
https://podcast.bubblelab.dev
```

허용할 redirect URL:

```text
https://podcast.bubblelab.dev/auth/callback
http://localhost:3000/auth/callback
```

Google provider도 활성화해야 합니다.
Google Cloud OAuth 클라이언트에는 Supabase가 보여주는 callback URL을 등록해야 합니다.
현재 프로젝트 기준 callback URL:

```text
https://ocjsumocbjrfxgavmjze.supabase.co/auth/v1/callback
```

## 4. 도메인

- `podcast.bubblelab.dev`를 Vercel 프로젝트에 연결
- 연결 후 `https://podcast.bubblelab.dev/login`이 열리는지 확인

## 5. 배포 후 기본 확인

```bash
APP_URL=https://podcast.bubblelab.dev \
API_URL=https://<cloud-run-service>.run.app \
./scripts/smoke-vercel-launch.sh
```

## 6. 수동 확인

- Supabase Google 로그인 성공
- `/auth/callback`에서 세션 확정
- `/settings`에서 알림 권한 요청 성공
- 업로드/재생/self-hosted remote-browser 재인증 동작 확인
