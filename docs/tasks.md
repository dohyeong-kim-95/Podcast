# Launch Tasks

## T-200 Supabase foundation

- [x] Firebase 제거 방향 확정
- [x] Supabase/Postgres/Web Push 마이그레이션 계획 작성
- [x] SQL migration 파일 추가
- [ ] Supabase SQL migration 실행
- [ ] Supabase Storage 버킷 생성

## T-201 Frontend auth migration

- [x] Firebase Web SDK 제거
- [x] Supabase browser client 추가
- [x] Google OAuth 로그인 전환
- [x] `/auth/callback` 추가
- [x] API 인증 헤더를 Supabase access token으로 교체
- [ ] Supabase Auth redirect URL 콘솔 설정

## T-202 Backend data migration

- [x] Firebase Admin 제거
- [x] Postgres 연결 레이어 추가
- [x] Supabase Auth 검증 레이어 추가
- [x] source/memory/nb_session/podcast/push 라우터를 Supabase/Postgres 기준으로 전환
- [x] 레거시 Firebase 전제 테스트 정리

## T-203 Storage migration

- [x] Source 업로드 경로를 Supabase Storage 기준으로 교체
- [x] Podcast MP3 저장 경로를 Supabase Storage 기준으로 교체
- [x] signed URL 생성 로직 추가
- [ ] 실제 Supabase bucket/policy로 실환경 검증

## T-204 Push migration

- [x] FCM 토큰 대신 PushSubscription 저장 구조로 변경
- [x] 서비스 워커를 표준 `push` 이벤트 기반으로 변경
- [x] `pywebpush` 기반 알림 발송 로직 추가
- [ ] VAPID 키 설정
- [ ] 실기기 푸시 수신 검증

## T-205 Deployment/docs

- [x] `readme.md`를 Supabase 기준으로 갱신
- [x] PRD/TRD/Launch Checklist 갱신
- [x] frontend/backend env example 갱신
- [ ] Cloud Run env 실제 반영
- [ ] Vercel env 실제 반영

## T-206 Verification

- [x] `frontend npm run build`
- [x] `python -m compileall backend/app`
- [x] 백엔드 테스트를 새 구조 기준으로 정리 후 재실행
- [ ] `scripts/smoke-vercel-launch.sh` 실 URL로 실행
- [ ] production login/upload/generate/re-auth/push 실검증
