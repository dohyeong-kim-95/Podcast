# Podcast

하루 동안 모아 둔 PDF와 이미지 소스를 다음 날 아침 한국어 오디오로 들을 수 있게 해주는 모바일 퍼스트 PWA입니다.

- 프로덕션 프론트엔드: `https://podcast.bubblelab.dev`
- 프론트엔드 배포: Vercel
- 백엔드 배포: FastAPI on Cloud Run

## 핵심 흐름

1. 낮 동안 PDF/이미지를 업로드합니다.
2. 매일 `06:40 KST`에 Cloud Scheduler가 생성 작업을 시작합니다.
3. NotebookLM이 오디오를 만들면 푸시 알림을 보냅니다.
4. 사용자는 앱에서 재생하거나 다운로드합니다.

## 현재 아키텍처

| 구성 | 선택 |
|------|------|
| 프론트엔드 | Next.js 14 App Router PWA |
| 프론트 호스팅 | Vercel |
| 백엔드 | Python FastAPI |
| 백엔드 호스팅 | Google Cloud Run |
| 인증 | Firebase Auth + 백엔드 화이트리스트 검증 |
| 데이터 | Firestore |
| 파일 저장 | Firebase Storage |
| 푸시 | Firebase Cloud Messaging |
| NotebookLM 재인증 | Browserless 새 탭 플로우 |
| 스케줄링 | Cloud Scheduler |

`firebase.json`의 Firebase Hosting 설정은 정적 export fallback 용도로 남아 있지만, 기본 출시 경로는 아닙니다.

## 프로젝트 구조

```text
backend/   FastAPI API, generation pipeline, Firebase admin integration
frontend/  Next.js app, PWA, Firebase Web SDK
docs/      PRD, TRD, launch tasks, deployment notes
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

- 프론트엔드 예시: [`frontend/.env.example`](/home/kimdohyeong/Working_kdh/1_Projects/002_notebooklm_py/Podcast/frontend/.env.example)
- 백엔드 예시: [`backend/.env.example`](/home/kimdohyeong/Working_kdh/1_Projects/002_notebooklm_py/Podcast/backend/.env.example)

프로덕션에서 중요한 값은 아래입니다.

- 프론트엔드: `NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN`, `NEXT_PUBLIC_API_BASE_URL`, `FIREBASE_AUTH_HELPER_ORIGIN`
- 백엔드: `CORS_ORIGINS`, `ALLOWED_EMAILS`, `CLOUD_RUN_URL`, `SCHEDULER_SERVICE_ACCOUNT`, `NB_COOKIE_ENCRYPTION_KEY`, `BROWSERLESS_TOKEN`, `BROWSERLESS_CONNECT_URL_TEMPLATE`, `BROWSERLESS_VIEWER_URL_TEMPLATE`

## 배포 원칙

### 프론트엔드

- Vercel 프로젝트 root는 `frontend/`
- 프로덕션 도메인은 `podcast.bubblelab.dev`
- `STATIC_EXPORT=1`은 Vercel 프로덕션 배포에 사용하지 않습니다

### 백엔드

- Cloud Run에 `backend/`를 배포합니다
- 프로덕션 origin에 맞춰 `CORS_ORIGINS=https://podcast.bubblelab.dev`를 설정해야 합니다
- Scheduler 호출용 `CLOUD_RUN_URL`, `SCHEDULER_SERVICE_ACCOUNT`가 필요합니다

## 검증

로컬에서 바로 할 수 있는 기본 검증은 아래입니다.

```bash
cd frontend && npm run build
docker run --rm -v "$PWD:/work" -w /work python:3.11-slim \
  bash -lc "pip install -q -r backend/requirements.txt pytest && PYTHONPATH=/work/backend pytest backend/tests"
```

배포 후 기본 HTTP 스모크 체크는 아래처럼 실행합니다.

```bash
APP_URL=https://podcast.bubblelab.dev \
API_URL=https://your-cloud-run-service.run.app \
./scripts/smoke-vercel-launch.sh
```

실제 출시 검증은 프로덕션 도메인과 외부 콘솔 설정이 끝난 뒤 진행해야 합니다.

## 문서

- [PRD](/home/kimdohyeong/Working_kdh/1_Projects/002_notebooklm_py/Podcast/docs/prd.md)
- [TRD](/home/kimdohyeong/Working_kdh/1_Projects/002_notebooklm_py/Podcast/docs/trd.md)
- [Launch Tasks](/home/kimdohyeong/Working_kdh/1_Projects/002_notebooklm_py/Podcast/docs/tasks.md)
- [Vercel Deploy](/home/kimdohyeong/Working_kdh/1_Projects/002_notebooklm_py/Podcast/docs/vercel-deploy.md)
- [Launch Checklist](/home/kimdohyeong/Working_kdh/1_Projects/002_notebooklm_py/Podcast/docs/launch-checklist.md)
