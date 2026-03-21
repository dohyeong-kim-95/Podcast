# Podcast — PRD (Supabase Launch Edition)

## 1. 제품 정의

**Podcast**는 하루 동안 모은 PDF와 이미지 소스를 바탕으로, 다음 날 아침 개인 맞춤형 한국어 오디오 요약을 들을 수 있게 해주는 모바일 퍼스트 PWA다.

- 프로덕션 진입점: `https://podcast.bubblelab.dev`
- 출시 형태: 소규모 화이트리스트 사용자용 비공개 서비스
- 운영 원칙: 프론트는 Vercel, 백엔드는 Cloud Run, 사용자 계정/데이터/스토리지는 Supabase를 사용한다

## 2. 이번 출시의 기준

- 사용자는 `podcast.bubblelab.dev`에서 앱을 연다
- Google 로그인은 Supabase Auth로 처리한다
- 데이터는 Supabase Postgres에 저장한다
- 파일은 Supabase Storage에 저장한다
- 푸시는 FCM이 아니라 표준 Web Push(VAPID)로 보낸다
- NotebookLM 재인증, 오디오 생성, 스케줄링은 기존 FastAPI + Cloud Run 구조를 유지한다

## 3. 목표 사용자

- 본인 포함 최대 5명 내외의 화이트리스트 사용자
- 낮 동안 문서와 스크린샷을 많이 저장하지만 다시 읽을 시간이 부족한 사용자
- 통근, 산책, 운동 시간에 전날 모은 정보를 오디오로 소비하고 싶은 사용자

## 4. 핵심 사용자 시나리오

1. 사용자는 `podcast.bubblelab.dev`에서 Google 로그인 후 소스를 업로드한다.
2. 매일 06:40 KST 기준으로 전일 06:40부터 당일 06:40까지의 소스가 수집 윈도우로 묶인다.
3. 스케줄러가 백엔드를 호출해 사용자별 팟캐스트 생성을 시작한다.
4. 생성이 끝나면 웹 푸시 알림이 도착한다.
5. 사용자는 앱에서 바로 재생하거나 다운로드한다.
6. NotebookLM 세션이 만료되면 설정 화면에서 self-hosted remote browser 재인증을 수행한다.

## 5. 출시 목표

### 제품 목표

- 로그인부터 업로드, 생성, 재생, 다운로드까지 전체 흐름이 `podcast.bubblelab.dev`에서 안정적으로 동작한다
- 예외 상황이 사용자에게 명확히 보인다
- Supabase 전환 이후 Firebase 콘솔 의존 없이 운영할 수 있다

### 운영 목표

- Vercel 배포와 Cloud Run 배포가 서로 독립적으로 롤백 가능하다
- 사용자 데이터와 파일 경로 규칙이 Supabase 기준으로 일관된다
- 환경변수와 콘솔 설정이 문서와 정확히 일치한다

## 6. 출시 범위

### P0

- Supabase Google 로그인
- 이메일 화이트리스트 기반 접근 제어
- PDF/PNG/JPEG/WEBP 업로드
- 이미지 업로드 시 서버 PDF 변환
- 당일 소스 목록 조회/삭제
- 매일 06:40 KST 자동 생성
- 수동 재생성
- 오늘의 팟캐스트 조회/재생/다운로드
- 청취 피드백 저장
- NotebookLM 세션 상태 표시와 재인증
- PWA 설치와 웹 푸시 알림

### P1

- 과거 에피소드 히스토리
- URL 소스 직접 수집
- 운영 대시보드

## 7. 비목표

- 백엔드를 Vercel Functions로 이관
- 공개 가입 서비스로 확장
- 팀/권한 모델 설계
- 완전한 오프라인 재생 앱

## 8. 성공 기준

- 로그인 성공 후 메인 화면 진입 실패가 없어야 한다
- 소스가 있는 날의 자동 생성 성공률 90% 이상
- NotebookLM 세션 만료 시 사용자가 스스로 재인증을 완료할 수 있다
- `podcast.bubblelab.dev` 기준으로 PWA 설치와 웹 푸시가 재현 가능하다

## 9. 제약과 리스크

- `notebooklm-py`는 비공식 라이브러리다
- NotebookLM 인증은 쿠키 기반이므로 주기적 재인증이 필요하다
- self-hosted remote browser와 Web Push는 실제 배포 도메인/HTTPS에서만 최종 검증 가능하다
- Supabase Auth redirect URL, Google provider 설정, Web Push VAPID 키가 어긋나면 로그인/알림이 바로 깨진다
- 로컬 자동 검증은 통과했지만 production 콘솔 설정과 실기기 검증이 남아 있다
