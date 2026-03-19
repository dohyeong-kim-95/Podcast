# Podcast — Launch Tasks

`2026-03-19` 기준의 출시용 태스크 문서다. 기존 구현 히스토리를 계속 늘리는 대신, 현재 코드베이스를 `podcast.bubblelab.dev`로 안정적으로 올리기 위해 남은 일만 정리한다.

## 0. 현재 상태

이미 코드로 갖춘 기반은 다음과 같다.

- [x] Next.js 앱 구조와 핵심 화면 (`/`, `/upload`, `/memory`, `/settings`, `/login`)
- [x] Firebase Auth 로그인 + 백엔드 화이트리스트 검증
- [x] 소스 업로드/목록/삭제
- [x] 이미지 -> PDF 변환
- [x] 자동 생성 API와 수동 재생성 API
- [x] 오늘의 팟캐스트 재생, 다운로드, 피드백
- [x] NotebookLM 세션 상태 조회와 Browserless 새 탭 재인증 플로우
- [x] PWA 설치 프롬프트, 서비스 워커, 오프라인 폴백
- [x] FCM 토큰 등록과 알림 발송 코드
- [x] Vercel용 Firebase Auth helper rewrite 코드

남은 일은 "새 기능 구현"보다 "프로덕션 설정과 실환경 검증"에 가깝다.

---

## Phase 1. 프로덕션 인프라 정렬

### T-100: Vercel 프로젝트 생성 및 `podcast.bubblelab.dev` 연결
- [ ] Vercel에 저장소 연결
- [ ] 프로젝트 root를 `frontend/`로 지정
- [ ] 프로덕션 환경변수 입력
- [ ] `podcast.bubblelab.dev` 커스텀 도메인 연결
- [ ] HTTPS로 메인 페이지와 로그인 페이지 정상 로드 확인
- 완료 기준: `https://podcast.bubblelab.dev`에서 앱이 뜨고 정적 자산 404가 없다

### T-101: Firebase Auth를 Vercel 커스텀 도메인에 맞게 정렬
- [ ] Firebase Authorized domains에 `podcast.bubblelab.dev` 추가
- [ ] Vercel env에 `NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN=podcast.bubblelab.dev` 설정
- [ ] `FIREBASE_AUTH_HELPER_ORIGIN=https://dailylmpodcast.firebaseapp.com` 확인
- [ ] `https://podcast.bubblelab.dev/__/auth/handler` redirect happy-path 검증
- 완료 기준: 프로덕션 도메인에서 `signInWithRedirect()` 로그인 왕복이 성공한다

### T-102: Cloud Run 운영 환경변수와 CORS 정리
- [ ] `CORS_ORIGINS=https://podcast.bubblelab.dev` 반영
- [ ] `ALLOWED_EMAILS`, `CLOUD_RUN_URL`, `SCHEDULER_SERVICE_ACCOUNT` 점검
- [ ] `NB_COOKIE_ENCRYPTION_KEY`, `BROWSERLESS_TOKEN`, `BROWSERLESS_*_URL_TEMPLATE` 설정
- [ ] Cloud Run 서비스 계정 권한 확인 (Firestore, Storage, FCM)
- 완료 기준: 프로덕션 프론트에서 `POST /api/auth/verify`와 일반 사용자 API 호출이 CORS 없이 성공한다

### T-103: Cloud Scheduler 운영 연결
- [ ] 생성 잡 `40 6 * * *` Asia/Seoul 생성
- [ ] 리마인더 잡 `0 22 * * *` Asia/Seoul 생성
- [ ] 두 잡 모두 OIDC로 Cloud Run 호출
- [ ] 수동 실행으로 `/api/generate`, `/api/remind-download` 응답 확인
- 완료 기준: 스케줄러가 인증 오류 없이 Cloud Run 엔드포인트를 호출한다

---

## Phase 2. 실환경 E2E 검증

### T-110: 로그인 및 기본 내비게이션 E2E
- [ ] 모바일 브라우저에서 로그인
- [ ] 로그인 직후 화이트리스트 검증
- [ ] `/upload`, `/memory`, `/settings` 이동 확인
- [ ] 로그아웃 후 `/login` 복귀 확인
- 완료 기준: 프로덕션 도메인에서 인증 관련 막힘이 없다

### T-111: 업로드 -> 생성 -> 재생 전체 플로우 검증
- [ ] PDF 1개, 이미지 1개 업로드
- [ ] 소스 목록 반영 확인
- [ ] `POST /api/generate/me`로 수동 생성
- [ ] 완료 후 재생/다운로드/피드백 저장 확인
- 완료 기준: 한 명의 사용자가 하루 루프를 수동으로 끝까지 재현할 수 있다

### T-112: NotebookLM 재인증 실기기 검증
- [ ] `/settings`에서 새 탭 재인증 시작
- [ ] Browserless viewer가 실제 모바일에서 열린다
- [ ] NotebookLM 로그인 후 `nb_session/current` 저장 확인
- [ ] 홈 배너와 설정 화면 상태가 자동 갱신되는지 확인
- 완료 기준: 실제 사용자 기기에서 세션 저장까지 끝난다

### T-113: 푸시 알림 및 PWA 검증
- [ ] 앱 설치 프롬프트 확인
- [ ] 서비스 워커 등록 확인
- [ ] 푸시 권한 허용 후 `push-token` 저장 확인
- [ ] 생성 완료 알림 수신 확인
- [ ] 다운로드 리마인더 알림 수신 확인
- 완료 기준: 최소 1개 실사용 브라우저 조합에서 설치 + 푸시가 재현된다

---

## Phase 3. 자동화와 운영 안전장치

### T-120: 프론트엔드 브라우저 E2E 하네스 추가
- [ ] 로그인 이후 보호 라우트 진입
- [ ] 업로드 화면 상호작용
- [ ] 메모리 저장
- [ ] 홈 화면 상태 분기 검증
- 완료 기준: 배포 전 최소 smoke 테스트를 자동으로 돌릴 수 있다

### T-121: 배포 스모크 체크리스트와 운영 런북 작성
- [ ] 로그인 실패 시 확인할 항목 정리
- [ ] CORS 실패 시 확인 절차 정리
- [ ] Browserless 실패 시 확인 절차 정리
- [ ] FCM 미수신 시 확인 절차 정리
- 완료 기준: 장애가 나도 확인 순서가 문서화되어 있다

### T-122: 로그/관측성 최소 기준 정리
- [ ] Cloud Run 로그에서 generation, nb-session, push 실패를 식별할 수 있게 필터 정리
- [ ] 스케줄러 실패 탐지 방법 정리
- [ ] 운영자가 확인할 기본 대시보드 또는 로그 쿼리 정리
- 완료 기준: "왜 실패했는지"를 로그에서 바로 찾을 수 있다

---

## Phase 4. 런치

### T-130: 화이트리스트 카나리 런치
- [ ] 1~2명 사용자만 먼저 허용
- [ ] 3일 연속 업로드/생성/청취 루프 확인
- [ ] 재인증 1회 이상 리허설
- 완료 기준: 실제 사용 패턴에서 반복 동작이 확인된다

### T-131: 정식 오픈 체크리스트
- [ ] 최종 화이트리스트 반영
- [ ] 도메인/SSL/환경변수 고정
- [ ] 스케줄러 활성화
- [ ] 비상시 fallback 경로 확인
- 완료 기준: 서비스가 사람 손을 덜 타고 운영 가능한 상태다

---

## Phase 5. 출시 후 후보

### T-200: 과거 에피소드 히스토리
- [ ] 하루치만 보관하는 현재 정책을 완화할지 결정

### T-201: URL 소스 수집
- [ ] 파일 업로드 외 입력 경로 추가

### T-202: 트랜스크립트/요약 노출
- [ ] 오디오 외 텍스트 소비 옵션 추가

### T-203: API 커스텀 도메인 분리
- [ ] 필요 시 `api.bubblelab.dev` 등으로 분리 검토

---

## 우선순위 요약

가장 먼저 끝내야 하는 순서는 아래다.

1. `T-100` ~ `T-103`: Vercel/Firebase/Cloud Run/Scheduler 정렬
2. `T-110` ~ `T-113`: 실제 기기 기반 E2E 검증
3. `T-130` ~ `T-131`: 카나리 후 정식 런치

지금 시점에서 가장 큰 리스크는 기능 미구현이 아니라, 프로덕션 도메인에서의 인증/재인증/푸시 정합성이다.
