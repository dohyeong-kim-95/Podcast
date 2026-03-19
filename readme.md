# 🎙️ Podcast

하루 동안 수집한 PDF·스크린샷을 매일 아침 7시에 10분짜리 한국어 AI 팟캐스트로 만들어주는 모바일 웹앱.

## 컨셉

> "어제 내가 본 것들을, 오늘 아침 팟캐스트로 듣는다"

1. 하루 동안 PDF/스크린샷을 앱에 업로드
2. 매일 아침 06:40에 자동으로 NotebookLM Audio Overview 생성
3. 07:00에 푸시 알림 → 통근·운동 시간에 팟캐스트 청취

## 아키텍처

| 구성요소 | 기술 |
|---------|------|
| 프론트엔드 | Next.js 14 PWA (Spotify 스타일 다크 UI) |
| 호스팅 | Firebase Hosting |
| 백엔드 | Python FastAPI, Google Cloud Run (max 5 인스턴스) |
| 인증 | Firebase Auth (Google OAuth) |
| DB | Firebase Firestore |
| 파일 저장 | Firebase Storage |
| 팟캐스트 생성 | notebooklm-py (비공식 NB API) |
| 스케줄링 | Cloud Scheduler (매일 06:40 KST) |
| 알림 | FCM PWA Push |
| NB 재인증 | Browserless.io (원격 브라우저) |

## 프로젝트 구조

```
podcast/
├── backend/                 # Python FastAPI
│   ├── app/
│   │   ├── main.py         # FastAPI 앱
│   │   ├── routers/        # API 라우터
│   │   ├── services/       # 비즈니스 로직
│   │   └── models/         # Pydantic 모델
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/                # Next.js
│   ├── app/                # App Router 페이지
│   ├── components/         # UI 컴포넌트
│   ├── lib/                # Firebase, API 클라이언트
│   └── public/             # PWA 매니페스트, SW
├── docs/
│   ├── prd.md
│   ├── trd.md
│   └── tasks.md
└── README.md
```

## 로컬 개발

### 백엔드
```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
uvicorn app.main:app --reload --port 8080
```

### 프론트엔드
```bash
cd frontend
npm install
npm run dev
```

### 환경변수

```env
# backend
FIREBASE_PROJECT_ID=your-project-id
GOOGLE_APPLICATION_CREDENTIALS=path/to/service-account.json
ALLOWED_EMAILS=user1@gmail.com,user2@gmail.com
NB_COOKIE_ENCRYPTION_KEY=your-fernet-key
BROWSERLESS_API_KEY=your-browserless-key
```

## 배포

```bash
# Cloud Run 배포
cd backend
gcloud run deploy podcast-api \
  --source . \
  --region asia-northeast3 \
  --timeout 1500 \
  --memory 1Gi \
  --min-instances 0 \
  --max-instances 5

# Firebase Hosting 배포
cd frontend
npm run build
firebase deploy --only hosting
```

## 주요 제약사항

- **notebooklm-py**는 비공식 라이브러리로, Google API 변경 시 서비스 중단 가능
- NB 세션 쿠키는 수 주~90일 주기로 만료되므로 주기적 재인증 필요
- Firebase Spark(무료) 플랜 한도: Storage 5GB, Firestore 1GB
- 최대 5명 소규모 그룹 프로젝트 용도

## 문서

- [PRD](docs/prd.md) — 제품 요구사항
- [TRD](docs/trd.md) — 기술 설계
- [tasks.md](docs/tasks.md) — 구현 태스크
