# Podcast — tasks.md

MVP 구현 태스크. 의존성 순서대로 정렬. 각 태스크는 독립적으로 테스트 가능한 단위.

---

## Phase 0: 프로젝트 셋업

### T-000: 모노레포 구조 초기화 ✅
- [x] 프로젝트 루트 생성 (`podcast/`)
- [x] `backend/` (Python FastAPI) 디렉토리 구조
- [x] `frontend/` (Next.js) 디렉토리 구조
- [x] `.gitignore`, `README.md`
- [x] `CLAUDE.md` 작성 (프로젝트 컨벤션)
- **완료 기준**: `backend/` 에서 FastAPI hello world, `frontend/` 에서 Next.js dev 서버 기동 ✅

### T-001: Firebase 프로젝트 설정 ✅
- [x] Firebase 설정 파일 생성 (`firebase.json`, `.firebaserc`)
- [x] Firestore 보안 규칙 작성 (`firestore.rules`)
- [x] Storage 보안 규칙 작성 (`storage.rules`)
- [x] Firebase JS SDK 설치 및 초기화 코드 작성 (`frontend/src/lib/firebase.ts`)
- [x] 환경변수 템플릿 작성 (`frontend/.env.example`)
- [x] Firebase 프로젝트 생성 (`dailylmpodcast`)
- [x] Firestore 활성화
- [x] Storage 활성화
- [x] Authentication 활성화 (Google 프로바이더)
- [x] 웹앱 등록 및 Firebase config 값 `.env.local` 반영
- [ ] Hosting 활성화 (Phase 8 배포 시점에 진행)
- [ ] 서비스 어카운트 키 생성 (백엔드용, Cloud Run 배포 시 필요)
- **완료 기준**: Firebase 콘솔에서 모든 서비스 활성 확인 ✅ (Hosting 제외)

### T-002: Cloud Run + Cloud Scheduler 기본 설정 ✅
- [ ] GCP 프로젝트에 Cloud Run API 활성화 (수동)
- [ ] Cloud Scheduler API 활성화 (수동)
- [ ] 서비스 어카운트 생성 (Scheduler → Cloud Run 호출용, 수동)
- [x] Dockerfile 작성 (Python 3.11 slim, Chromium 미포함 — Browserless.io 원격 연결)
- [x] 테스트 엔드포인트 (`GET /health`) 구현 및 로컬 동작 확인
- **완료 기준**: Cloud Run에 헬스체크 엔드포인트 배포 성공, Scheduler에서 호출 확인
- **참고**: Dockerfile + health endpoint 코드 완료. GCP 서비스 활성화 및 배포는 수동 필요

---

## Phase 1: 인증 & 기본 API

### T-010: Firebase Auth 연동 (백엔드) ✅
- [x] `firebase-admin` SDK 초기화
- [x] ID 토큰 검증 미들웨어 구현 (사용자 API용)
- [x] 이메일 화이트리스트 체크 (환경변수 `ALLOWED_EMAILS`)
- [x] Scheduler OIDC 토큰 검증 미들웨어 구현 (내부 API용: `/api/generate`, `/api/remind-download`)
  - `google.oauth2.id_token.verify_oauth2_token()` 사용
  - `audience`: Cloud Run 서비스 URL (환경변수 `CLOUD_RUN_URL`)
  - Scheduler 서비스 어카운트 이메일 검증
- [x] `POST /api/auth/verify` 엔드포인트
- **완료 기준**: 사용자 API는 Firebase ID 토큰 + 화이트리스트, 내부 API는 OIDC 토큰으로만 접근 가능 ✅

### T-011: Firebase Auth 연동 (프론트엔드) ✅
- [x] Firebase SDK 초기화 (`lib/firebase.ts`)
- [x] Google OAuth 로그인 페이지
- [x] 인증 상태 관리 (Context/Provider)
- [x] 보호 라우트 (미인증 → 로그인 리다이렉트)
- **완료 기준**: 모바일에서 Google 로그인 → 메인 페이지 접근 가능 ✅

---

## Phase 1-QA: 인증 품질 개선

### T-012: Storage Rules 중복 write 제거 ✅
- [x] `storage.rules`에서 첫 번째 `allow read, write` 규칙을 `allow read, delete`로 변경
- [x] 20MB 제한이 달린 `allow create, update`만 쓰기 허용하도록 수정
- **완료 기준**: 20MB 초과 파일 업로드 시 Firebase Rules가 실제 차단 ✅

### T-013: 모바일 로그인 signInWithPopup → signInWithRedirect ✅
- [x] `auth-context.tsx`에서 `signInWithRedirect` + `getRedirectResult` 적용
- [x] 모바일 환경에서 popup 차단 문제 해소
- **완료 기준**: 모바일 브라우저에서 Google 로그인 정상 동작 ✅

### T-014: 로그인 직후 백엔드 /api/auth/verify 호출 ✅
- [x] Firebase 로그인 성공 후 ID 토큰으로 `/api/auth/verify` 호출
- [x] 화이트리스트 거부(403) 시 즉시 sign out + 에러 메시지 표시
- [x] `ProtectedRoute`에서 verify 상태(verified/denied/pending) 관리
- **완료 기준**: 화이트리스트에 없는 이메일로 로그인 시 즉시 로그아웃 + 안내 메시지 ✅

---

## Phase 2: 소스 업로드

### T-019: CORS origin 명시적 관리 ✅
- [x] `backend/app/main.py`에서 `allow_origins=["*"]`를 Firebase Hosting 도메인으로 제한
- [x] `allow_credentials=True`와 함께 동작하도록 origin 목록 관리
- [x] `CORS_ORIGINS` 환경변수로 origin 목록 관리
- **완료 기준**: 허용된 origin에서만 API 호출 가능, credentials 정상 동작 ✅

### T-020: 파일 업로드 API ✅
- [x] `POST /api/sources/upload` (multipart/form-data)
- [x] MIME 타입 검증 (PDF, PNG, JPG, JPEG, WEBP)
- [x] 파일 크기 제한 (20MB)
- [x] Firebase Storage에 원본 저장 (`sources/{uid}/{date}/{sourceId}.ext`)
- [x] Firestore에 소스 메타데이터 문서 생성
- **완료 기준**: curl로 PDF/이미지 업로드 → Storage에 파일, Firestore에 문서 확인 ✅

### T-021: 이미지→PDF 변환 ✅
- [x] `img2pdf.convert()`로 이미지→PDF 변환 (Pillow+reportlab 대비 코드 간소화)
- [x] 변환된 PDF를 Storage에 저장
- [x] Firestore 소스 문서 `convertedType` 업데이트
- **의존**: T-020
- **완료 기준**: PNG 업로드 → Storage에 .pdf 파일 생성 확인 ✅

### T-022: 소스 목록 & 삭제 API ✅
- [x] `GET /api/sources?date=YYYY-MM-DD` (윈도우 내 소스 목록)
- [x] `DELETE /api/sources/{sourceId}` (Storage 파일 + Firestore 문서 삭제)
- **의존**: T-020
- **완료 기준**: 업로드 후 목록 조회, 삭제 후 목록에서 제거 확인 ✅

### T-023: 업로드 UI ✅
- [x] `UploadZone` 컴포넌트 (파일 선택 버튼, 다중 선택)
- [x] 업로드 진행률 표시
- [x] `SourceList` 컴포넌트 (파일명, 시각, 파일타입 아이콘 📄/🖼️ — 썸네일은 P1)
- [x] 소스 삭제 버튼 (확인 다이얼로그)
- [x] `upload/page.tsx` 페이지 조립
- **의존**: T-011, T-020, T-022
- **완료 기준**: 모바일에서 이미지/PDF 업로드 → 목록에 표시 → 삭제 가능 ✅

---

## Phase 2-QA: 소스 업로드 품질 개선

### T-024: storagePath 분리 (originalStoragePath / convertedStoragePath) ✅
- [x] Firestore `sources` 문서의 `storagePath` 단일 필드를 `originalStoragePath` + `convertedStoragePath`로 분리
- [x] 이미지→PDF 변환 시 `convertedStoragePath`만 업데이트, 원본 경로는 보존
- [x] 삭제 시 두 경로를 각각 삭제 (MIME 역추론 제거)
- [x] TRD 데이터 모델 반영, 프론트 Source 인터페이스 업데이트
- **완료 기준**: 이미지 업로드 → 원본/변환본 경로 분리 저장, 삭제 시 누락 없이 양쪽 삭제 ✅

### T-025: Firestore 복합 인덱스 선언 ✅
- [x] `firestore.indexes.json`에 sources 컬렉션 복합 인덱스 추가
  - `uid` (ASC) + `windowDate` (ASC) + `status` (ASC) + `uploadedAt` (ASC)
- [x] `list_sources` 쿼리 (uid ==, windowDate ==, status in, orderBy uploadedAt) 대응
- **완료 기준**: `firebase deploy --only firestore:indexes` 시 인덱스 자동 생성, 배포 환경에서 인덱스 에러 없음 ✅

### T-026: 서버 측 파일 매직바이트 검증 ✅
- [x] `validate_file_content()` 함수: PDF 시그니처 (`%PDF`), PNG (`\x89PNG`), JPEG (`\xff\xd8\xff`), WEBP (`RIFF....WEBP`) 검증
- [x] 업로드 라우트에서 MIME 검증 후 매직바이트 검증 추가
- [x] 단위 테스트 9개 추가 (각 타입 valid/invalid + unknown type)
- **완료 기준**: MIME만 맞고 실제 내용이 다른 파일 업로드 시 400 에러 ✅

---

## Phase 3: 팟캐스트 생성

### T-030: notebooklm-py 통합 서비스 ✅
- [x] `NotebookLMClient` 래퍼 클래스 (쿠키 로드, 에러 핸들링)
- [x] 노트북 CRUD (생성, 삭제)
- [x] 소스 추가 (로컬 PDF 파일 → 노트북)
- [x] Audio Overview 생성 (`generate_audio` + `wait_for_completion`)
- [x] 오디오 다운로드 (`download_audio`)
- **완료 기준**: 수동으로 쿠키 세팅 → PDF 소스 → 오디오 생성 → mp3 다운로드 성공 ✅

### T-031: 메모리→Instructions 구성 ✅
- [x] `build_instructions(memory)` 함수 구현
- [x] 관심 분야, 톤, 깊이, 커스텀 텍스트, 피드백 반영
- [x] 기본값 처리 (메모리 비어있을 때)
- **완료 기준**: 다양한 메모리 입력에 대해 올바른 instructions 문자열 생성 확인 ✅

### T-032: 팟캐스트 생성 파이프라인 ✅
- [x] `POST /api/generate` 엔드포인트
- [x] 소스 윈도우 조회 (전일 06:40 ~ 당일 06:40)
- [x] 당일 팟캐스트 status가 `completed`, `generating`, `retry_1`, `retry_2`인 사용자 스킵 (Scheduler 재시도 시 중복 생성 방지)
- [x] 소스 0개 체크 → 스킵 + 푸시 알림
- [x] NB 쿠키 유효성 체크
- [x] T-030 서비스 호출 (노트북 생성 → 소스 추가 → 오디오 생성)
- [x] 생성된 mp3를 Storage에 저장 (`podcasts/{uid}/{date}.mp3`)
- [x] Firestore 팟캐스트 문서 생성/업데이트
- [x] 이전 날 팟캐스트 오디오 삭제 (Storage)
- [x] 사용 완료된 소스 파일 정리 (Storage, 선택적)
- [x] 전체 사용자 순회 생성 (병렬 처리)
- [x] 개별 사용자 수동 트리거 엔드포인트 (`POST /api/generate/me`)
- [x] 재시도는 Cloud Scheduler 재시도 정책으로 처리 (별도 요청, 최대 2회)
- **의존**: T-030, T-031
- **완료 기준**: 소스가 있는 상태에서 `/api/generate` 호출 → mp3 생성, Firestore 문서 완성 ✅

### T-032-1: Scheduler OIDC 서비스 계정 이메일 검증 보강 ✅
- [x] `verify_scheduler_token`에 서비스 계정 이메일 검증 추가 (`SCHEDULER_SERVICE_ACCOUNT`)
- [x] audience 검증 + 이메일 검증 이중 체크
- **완료 기준**: 올바른 서비스 계정에서 발급된 OIDC 토큰만 내부 API 접근 가능 ✅

### T-032-2: 테스트 케이스 확장 ✅
- [x] Scheduler OIDC 검증 테스트 (유효/무효 서비스 계정)
- [ ] 프론트 ProtectedRoute + verify 연동 테스트
- [ ] 화이트리스트 거부 시 로그아웃 플로우 테스트
- **완료 기준**: 인증 관련 경계 케이스 커버리지 확보 (백엔드 테스트 완료, 프론트엔드 테스트는 Phase 8에서)

### T-033: Cloud Scheduler 연결
- [ ] 생성 크론잡: `40 6 * * *` (Asia/Seoul) → `POST /api/generate` (GCP 콘솔에서 수동 설정)
- [ ] 리마인더 크론잡: `0 22 * * *` (Asia/Seoul) → `POST /api/remind-download` (GCP 콘솔에서 수동 설정)
- [ ] 두 크론잡 모두 OIDC 인증 설정 (audience: Cloud Run URL)
- [x] T-010에서 구현한 OIDC 미들웨어가 적용되어 있는지 확인
- [ ] Cloud Scheduler 재시도 정책 설정 (최대 2회, 5분 간격)
- **의존**: T-032, T-002, T-010
- **완료 기준**: 매일 06:40 생성 트리거 + 22:00 리마인더 트리거 동작 확인
- **참고**: 엔드포인트 및 OIDC 미들웨어 코드 완료. Cloud Scheduler 크론잡은 GCP 콘솔에서 수동 설정 필요

---

## Phase 3-QA: 팟캐스트 생성 품질 개선

### T-034: generate/me 중복 실행 레이스 컨디션 방지 ✅
- [x] `POST /api/generate/me`에서 상태 확인 + generating 전환을 Firestore transaction으로 원자화
- [x] 동시 요청 시 두 번째 요청이 409 반환하도록 보장
- **완료 기준**: 동시에 두 번 호출해도 _generate_for_user가 한 번만 실행됨 ✅

### T-035: NB 세션 expiresAt 서버 측 검증 ✅
- [x] `load_nb_session()`에서 status뿐 아니라 expiresAt <= now도 체크하여 만료 판정
- [x] Firestore status 갱신이 늦어도 서버가 실제 만료를 감지
- **완료 기준**: expiresAt이 지난 세션은 status 값과 무관하게 ValueError 발생 ✅

### T-036: NB 세션 복호화/손상 예외 정규화 ✅
- [x] `decrypt_storage_state()`에서 Fernet InvalidToken, JSONDecodeError 등을 ValueError로 정규화
- [x] `_generate_for_user()`가 NB 세션 관련 예외를 일관되게 nb_session 실패로 분류 (재시도 대상 생성 실패와 분리)
- **완료 기준**: 키 불일치·데이터 손상 시 재시도 없이 즉시 failed(nb_session) 처리 ✅

### T-037: build_instructions() 필드명 alias 대응 ✅
- [x] Phase 5 메모리 API 필드명(tone, depth, custom)과 현재 필드명(preferredTone, preferredDepth, customInstructions) 양쪽 모두 지원
- [x] 테스트 케이스에 alias 필드명 검증 추가
- **완료 기준**: 어느 필드명으로 저장되어도 instructions에 반영됨 ✅

### T-038: no_sources 상태 모델 정리 ✅
- [x] 소스 없음 시 status="completed" 대신 status="no_sources" 사용
- [x] Phase 4 조회 API에서 no_sources를 별도 상태로 분기 가능하도록 정리
- [x] _generate_for_user()의 _SKIP_STATUSES에 "no_sources" 추가
- **완료 기준**: 오디오 없는 completed가 존재하지 않음, 조회 API에서 상태별 명확한 분기 ✅

---

## Phase 4: 팟캐스트 재생 & 피드백

### T-040: 팟캐스트 조회 API
- [ ] `GET /api/podcast/today` (오늘 팟캐스트 정보 + signed download URL)
- [ ] 상태별 응답: completed → 오디오 URL, generating → 진행 중, failed → 수동 트리거 안내, none → 소스 없음
- **의존**: T-032
- **완료 기준**: 팟캐스트 상태별로 올바른 응답 반환

### T-041: 오디오 플레이어 UI
- [ ] `AudioPlayer` 컴포넌트 (HTML5 Audio 기반)
- [ ] 재생/일시정지 토글
- [ ] 시크바 (드래그 가능)
- [ ] 배속 조절 (1x / 1.5x / 2x)
- [ ] 다운로드 버튼 (mp3 로컬 저장)
- [ ] 다운로드 완료 시 `POST /api/podcast/{id}/downloaded` 호출 (200 OK 응답, body 없음) → Firestore `downloaded: true` 업데이트
- [ ] 메인 페이지(`page.tsx`)에 통합
- **의존**: T-040, T-011
- **완료 기준**: 모바일에서 팟캐스트 재생, 배속 변경, 다운로드 동작

### T-042: 피드백 기능
- [ ] `FeedbackBar` 컴포넌트 (좋았다 / 보통 / 별로 버튼)
- [ ] `POST /api/podcast/{id}/feedback` API
- [ ] Firestore 팟캐스트 문서 `feedback` 필드 업데이트
- [ ] 사용자 메모리 `feedbackHistory`에 추가
- **의존**: T-040
- **완료 기준**: 피드백 선택 → Firestore에 반영 확인

### T-043: 수동 트리거 버튼
- [ ] 메인 페이지에서 팟캐스트 상태가 `failed`일 때 "다시 생성" 버튼 표시
- [ ] 버튼 클릭 → `POST /api/generate/me` 호출
- [ ] 생성 중 로딩 상태 표시
- **의존**: T-041, T-032
- **완료 기준**: 실패 상태에서 수동 트리거 → 재생성 진행

---

## Phase 5: 사용자 메모리

### T-050: 메모리 API
- [ ] `GET /api/memory` (사용자 메모리 조회)
- [ ] `PUT /api/memory` (메모리 업데이트: interests, tone, depth, custom)
- **완료 기준**: 메모리 CRUD 동작 확인

### T-051: 메모리 설정 UI
- [ ] `memory/page.tsx` 페이지
- [ ] 관심 분야 텍스트 입력
- [ ] 선호 톤 텍스트 입력
- [ ] 깊이 수준 텍스트 입력
- [ ] 자유 텍스트 (커스텀 instructions)
- [ ] 저장 버튼 → API 호출
- **의존**: T-050, T-011
- **완료 기준**: 메모리 입력 → 저장 → 다시 열면 기존 값 표시

### T-052: 피드백 히스토리 업데이트 원자화
- [ ] 피드백 저장 시 `memory` 전체 덮어쓰기 대신 `arrayUnion` 또는 부분 업데이트 사용
- [ ] 메모리 설정과 피드백이 동시에 수정될 때 마지막 쓰기 승리(last-write-wins) 방지
- **의존**: T-050
- **완료 기준**: 메모리 설정과 피드백 동시 수정 시 데이터 유실 없음

---

## Phase 6: NB 인증 관리

### T-059: Browserless 뷰어 모바일 스파이크 (선행 검증)
- [ ] Browserless.io 무료 티어로 원격 세션 생성
- [ ] live view URL을 모바일 iframe에 삽입 테스트
  - `X-Frame-Options` / CSP 헤더 확인
  - 모바일 터치 이벤트 정상 전달 여부
  - Google 로그인 페이지 iframe 차단 여부 (`accounts.google.com`은 `X-Frame-Options: DENY` 가능성 높음)
- [ ] iframe 실패 시 대안 검증: `window.open()` 팝업 또는 새 탭 방식
  - 새 탭에서 로그인 → 서버 폴링으로 완료 감지 → 원래 탭에서 상태 갱신
- [ ] 결과에 따라 T-060, T-061 구현 방식 확정
- **완료 기준**: 모바일에서 Browserless 뷰어 표시 방식 결정 (iframe / 팝업 / 새 탭)
- **소요 추정**: 2~4시간

### T-060: Browserless.io 재인증 API
- [ ] `POST /api/nb-session/start-auth`
  - Browserless API로 원격 Chromium 세션 생성
  - Playwright `browser.connect()` → `notebooklm.google.com` navigate
  - 세션 뷰어 URL 반환
  - 백그라운드 태스크로 로그인 완료 폴링 시작
- [ ] 로그인 완료 자동 감지 (서버 폴링)
  - 2초 간격 `page.url()` 체크
  - URL이 `notebooklm.google.com/*` (로그인 후 리다이렉트)로 변경 시 완료 판정
  - 타임아웃 5분 초과 시 세션 종료 + 실패 응답
  - 완료 시 `browser.contexts[0].storage_state()` 호출 → 쿠키/스토리지 추출
- [ ] 쿠키 저장
  - Fernet(AES) 암호화 → Firestore `nb_session` 문서 저장
  - `expiresAt`: 현재 + 30일 (추정)
  - `status`: "valid" 업데이트
  - Browserless 세션 종료 (`browser.close()`)
- [ ] `GET /api/nb-session/status` (유효/만료임박/만료)
- **완료 기준**: Browserless 세션에서 Google 로그인 → 서버가 자동 감지 → 쿠키 추출·저장 → status valid

### T-061: NB 세션 관리 UI
- [ ] `settings/page.tsx`에 NB 세션 상태 표시
- [ ] "재인증" 버튼 → Browserless 뷰어를 iframe/팝업으로 표시
- [ ] 인증 완료 감지 → 뷰어 닫기, 상태 갱신
- [ ] `StatusBanner` 컴포넌트 (만료 시 앱 상단 배너)
- **의존**: T-060
- **완료 기준**: 모바일에서 재인증 플로우 전체 동작

---

## Phase 7: PWA & 알림

### T-070: PWA 설정
- [ ] `manifest.json` (앱 이름, 아이콘, 테마 컬러, display: standalone)
- [ ] Service Worker 등록
- [ ] 오프라인 폴백 페이지
- [ ] 홈 화면 추가 프롬프트
- **완료 기준**: 모바일 크롬에서 "홈 화면에 추가" → 앱처럼 실행

### T-071: 다운로드 리마인더 푸시
- [ ] `POST /api/remind-download` 엔드포인트
- [ ] 오늘의 팟캐스트가 있고 `downloaded: false`인 사용자에게 푸시
- [ ] Cloud Scheduler 크론잡 추가 (`0 22 * * *`, Asia/Seoul)
- [ ] 푸시 알림 탭 → 앱 열기 → 다운로드 유도
- **의존**: T-070, T-040
- **완료 기준**: 22:00에 미다운로드 사용자에게 리마인더 수신

### T-072: 푸시 알림
- [ ] FCM 설정 (프론트 + 백엔드)
- [ ] 사용자 FCM 토큰 등록 (`fcmToken` Firestore 저장)
- [ ] FCM 토큰 갱신 처리: `onTokenRefresh` (또는 `onMessage` 시 토큰 체크) 콜백 등록
  - 브라우저가 토큰을 갱신하면 Firestore `users/{uid}.fcmToken` 자동 업데이트
  - 구현: `messaging.onTokenRefresh(() => { getToken().then(token => updateFirestore(token)) })`
  - 이걸 안 하면 토큰 만료 후 푸시 알림이 안 옴
- [ ] 팟캐스트 생성 완료 시 푸시 발송
- [ ] 소스 없음 / NB 세션 만료 시 푸시 발송
- [ ] Service Worker에서 알림 클릭 → 앱 열기
- **의존**: T-070
- **완료 기준**: 팟캐스트 생성 후 모바일에 푸시 알림 수신, 토큰 갱신 시 Firestore 자동 업데이트

---

## Phase 8: UI 마무리 & 배포

### T-080: Spotify 스타일 다크 UI
- [ ] 전역 다크 테마 (Tailwind CSS)
- [ ] 하단 네비게이션 바 (`BottomNav`: 홈/업로드/메모리/설정)
- [ ] 모바일 최적화 (터치 타겟, 스크롤, safe area)
- [ ] 로딩/에러 상태 UI
- [ ] 업로드 UX 개선: 바이트 기반 진행률, 다중 파일 에러 누적 표시, 허용되지 않은 파일 안내 메시지
- **완료 기준**: 모바일에서 전체 플로우 터치 UX 쾌적

### T-080-1: 업로드 크기 검사 스트리밍 전환
- [ ] `await file.read()` 전체 메모리 적재 방식 → 스트리밍/청크 기반 크기 검증
- [ ] Cloud Run 메모리 최적화 (동시 업로드 대비)
- **완료 기준**: 20MB 제한 유지하면서 메모리 사용량 감소

### T-080-2: 팟캐스트 생성 동시성 제한 (Semaphore)
- [ ] `/api/generate`의 asyncio.gather()에 semaphore 적용하여 동시 NotebookLM 호출 수 제한
- [ ] Cloud Run 메모리/리소스 사용량 최적화
- **완료 기준**: 다수 사용자 동시 생성 시 리소스 과부하 없음

### T-080-3: NotebookLM 호출 타임아웃 적용
- [ ] `AUDIO_TIMEOUT_SECONDS`를 실제 asyncio.wait_for()로 적용
- [ ] 타임아웃 시 적절한 에러 상태(failed) 설정
- **완료 기준**: 외부 서비스 무응답 시 일정 시간 후 정리 및 실패 처리

### T-080-4: notebooklm-py 버전 고정
- [ ] requirements.txt에서 `notebooklm-py>=0.3.0` → 정확한 버전 핀 고정
- [ ] 배포 재현성 확보
- **완료 기준**: 재설치 시 동일 버전 보장

### T-081: Firebase Hosting 배포
- [ ] Next.js static export 설정
- [ ] `firebase.json` 설정 (hosting + Cloud Run 프록시)
- [ ] GitHub Actions CI/CD (선택)
- **완료 기준**: `https://podcast-xxxxx.web.app` 에서 앱 접근 가능

### T-082: E2E 테스트
- [ ] 업로드 → 소스 목록 확인
- [ ] 수동 팟캐스트 생성 → 재생 → 다운로드
- [ ] 메모리 설정 → 생성 시 instructions 반영 확인
- [ ] NB 재인증 플로우
- [ ] 푸시 알림 수신
- [ ] 프론트엔드 업로드 플로우 통합 테스트 (UI 컴포넌트 테스트 포함)
- **완료 기준**: 전체 일상 시나리오 1회 정상 완료

---

## 태스크 의존성 요약

```
T-000, T-001, T-002 (병렬)
    │
    ▼
T-010 → T-011 (인증)
    │
    ▼
T-012, T-013, T-014 (Phase 1-QA, 병렬)
    │
    ▼
T-019 → T-020 → T-021 → T-022 → T-023 (소스 업로드)
    │
    ▼
T-024, T-025, T-026 (Phase 2-QA, 병렬)
    │
    ▼
T-030 → T-031 → T-032 → T-032-1, T-032-2 (병렬) → T-033 (팟캐스트 생성)
    │
    ▼
T-034, T-035, T-036, T-037, T-038 (Phase 3-QA, 병렬)
    │
    ▼
T-040 → T-041, T-042, T-043 (재생 & 피드백, 병렬)
    │
    ▼
T-050 → T-051 → T-052 (메모리 + 피드백 원자화)
    │
T-060 → T-061 (NB 인증, Phase 1 이후 언제든 가능)
    │
    ▼
T-070 → T-071, T-072 (PWA & 알림)
    │
    ▼
T-080, T-080-2, T-080-3, T-080-4 → T-081 → T-082 (마무리)
```
