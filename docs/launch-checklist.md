# Launch Checklist

이 문서는 `podcast.bubblelab.dev` 기준의 출시 체크리스트입니다. 로컬에서 끝낼 수 있는 일과 콘솔/실기기에서 해야 하는 일을 분리했습니다.

## 1. 로컬에서 먼저 확인

### 코드/문서 정합성
- [ ] `docs/prd.md`, `docs/trd.md`, `docs/tasks.md`가 현재 방향과 맞는다
- [ ] `readme.md`가 Vercel + Cloud Run 구조를 기준으로 설명한다
- [ ] `frontend/.env.example`, `backend/.env.example`이 실제 코드에서 읽는 env와 맞다

### 로컬 검증
- [ ] `cd frontend && npm run build`
- [ ] 아래 Docker 명령으로 백엔드 테스트를 실행했다

```bash
docker run --rm -v "$PWD:/work" -w /work python:3.11-slim \
  bash -lc "pip install -q -r backend/requirements.txt pytest && PYTHONPATH=/work/backend pytest backend/tests"
```

- [ ] `bash -n scripts/smoke-vercel-launch.sh`
- [ ] 변경된 배포 민감 파일 diff를 수동 검토했다

## 2. Vercel

- [ ] 저장소를 Vercel에 연결했다
- [ ] root를 `frontend/`로 설정했다
- [ ] 아래 env를 입력했다

```env
NEXT_PUBLIC_FIREBASE_API_KEY=...
NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN=podcast.bubblelab.dev
NEXT_PUBLIC_FIREBASE_PROJECT_ID=dailylmpodcast
NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET=dailylmpodcast.firebasestorage.app
NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID=...
NEXT_PUBLIC_FIREBASE_APP_ID=...
NEXT_PUBLIC_FIREBASE_VAPID_KEY=...
NEXT_PUBLIC_API_BASE_URL=https://<cloud-run-service>.run.app
FIREBASE_AUTH_HELPER_ORIGIN=https://dailylmpodcast.firebaseapp.com
```

- [ ] `podcast.bubblelab.dev`를 연결했다
- [ ] `STATIC_EXPORT=1`을 넣지 않았다

## 3. Firebase Console

- [ ] Authentication Authorized domains에 `podcast.bubblelab.dev`를 추가했다
- [ ] 필요 시 `https://podcast.bubblelab.dev/__/auth/handler` redirect 경로를 확인했다
- [ ] FCM Web Push용 VAPID 키를 확인했다

## 4. Cloud Run

- [ ] 서비스가 최신 코드로 배포됐다
- [ ] 아래 env/secrets가 반영됐다

```env
ALLOWED_EMAILS=...
CORS_ORIGINS=https://podcast.bubblelab.dev
CLOUD_RUN_URL=https://<cloud-run-service>.run.app
SCHEDULER_SERVICE_ACCOUNT=<scheduler-service-account-email>
NB_COOKIE_ENCRYPTION_KEY=...
BROWSERLESS_TOKEN=...
BROWSERLESS_CONNECT_URL_TEMPLATE=...
BROWSERLESS_VIEWER_URL_TEMPLATE=...
NB_AUTH_TARGET_URL=https://notebooklm.google.com
NB_AUTH_TIMEOUT_SECONDS=300
AUDIO_TIMEOUT_SECONDS=1200
GENERATE_MAX_CONCURRENCY=4
NB_SESSION_EXPIRING_SOON_DAYS=7
```

- [ ] Firestore/Storage/FCM 권한이 있는 서비스 계정을 사용한다
- [ ] `GET /health`가 200을 반환한다

## 5. Cloud Scheduler

- [ ] `POST /api/generate` 잡을 만들었다
  - 스케줄: `40 6 * * *`
  - 타임존: `Asia/Seoul`
- [ ] `POST /api/remind-download` 잡을 만들었다
  - 스케줄: `0 22 * * *`
  - 타임존: `Asia/Seoul`
- [ ] 두 잡 모두 OIDC로 Cloud Run을 호출한다
- [ ] 두 잡 모두 수동 실행 테스트를 했다

## 6. 실기기 검증

- [ ] 아래 스모크 스크립트를 한 번 실행했다

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
- [ ] Browserless 새 탭 재인증 성공
- [ ] PWA 설치 프롬프트 확인
- [ ] 푸시 권한 허용 및 `push-token` 저장 확인
- [ ] 생성 완료 알림 수신 확인
- [ ] 다운로드 리마인더 알림 수신 확인

## 7. 장애 시 가장 먼저 볼 것

### 로그인 실패
- `NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN`
- Firebase Authorized domains
- `/__/auth/*` rewrite 동작

### API 호출 실패
- `NEXT_PUBLIC_API_BASE_URL`
- `CORS_ORIGINS`
- Cloud Run 배포 URL

### NotebookLM 재인증 실패
- `BROWSERLESS_TOKEN`
- `BROWSERLESS_CONNECT_URL_TEMPLATE`
- `BROWSERLESS_VIEWER_URL_TEMPLATE`
- 실제 모바일 브라우저의 새 탭 차단 여부

### 스케줄러 실패
- `CLOUD_RUN_URL`
- `SCHEDULER_SERVICE_ACCOUNT`
- Cloud Scheduler OIDC 설정

### 푸시 미수신
- VAPID 키
- 브라우저 알림 권한
- `push-token` 저장 여부
- FCM 토큰이 오래된 값인지 여부

## 8. 롤백/우회

- 프론트 배포에 문제가 생기면 Vercel 배포를 되돌리고, API는 그대로 유지합니다
- Vercel 쪽 Auth helper가 막히면 Firebase Hosting static export 경로는 fallback으로 남아 있지만, 현재 기본 운영 경로는 아닙니다
- Browserless/FCM은 코드보다 환경값 문제일 가능성이 크므로 먼저 설정을 확인합니다
