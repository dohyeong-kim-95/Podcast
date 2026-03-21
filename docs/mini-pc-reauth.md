# MiniPC Reauth Host

이 문서는 `reauth.bubblelab.dev`를 미니PC에서 운영해 NotebookLM 모바일 재인증을 제공하는 절차를 정리합니다.

## 목표 구조

- `podcast.bubblelab.dev`: Vercel 프론트엔드
- Cloud Run backend: API, generation, push
- `reauth.bubblelab.dev`: miniPC의 self-hosted remote browser

현재 전제:

- authoritative DNS는 Vercel nameserver가 관리한다
- miniPC는 공인 IP가 있는 공유기 뒤에 있다
- 공유기 포트포워딩으로 `80`, `443`을 miniPC에 연결한다

## 1. backend env

Cloud Run backend에는 아래 값이 필요합니다.

```env
REAUTH_HOST_BASE_URL=https://reauth.bubblelab.dev
REAUTH_HOST_API_KEY=<long-random-api-key>
REAUTH_CALLBACK_TOKEN=<long-random-callback-token>
```

## 2. miniPC env

미니PC에는 [reauth_host/.env.example](/home/kimdohyeong/Working_kdh/1_Projects/002_notebooklm_py/Podcast/reauth_host/.env.example) 을 복사해 `.env`로 둡니다.

핵심 값:

```env
REAUTH_HOST_PUBLIC_BASE_URL=https://reauth.bubblelab.dev
REAUTH_PUBLIC_HOSTNAME=reauth.bubblelab.dev
REAUTH_HOST_API_KEY=<same-as-backend>
```

`REAUTH_CALLBACK_TOKEN`은 miniPC `.env`에는 직접 넣지 않습니다. backend가 세션 생성 시 callback payload 안에 전달합니다.

## 3. DNS / public ingress

Vercel DNS에서 아래 레코드를 추가합니다.

```text
Type: A
Name: reauth
Value: <현재 공인 IP>
TTL: 기본값
```

그리고 공유기에서 아래 포트를 miniPC 내부 IP로 포워딩합니다.

- TCP `80` -> miniPC `80`
- TCP `443` -> miniPC `443`

권장:

- miniPC 내부 IP는 DHCP 예약 또는 고정 IP로 유지
- `reauth`용 공인 IP가 바뀌는 환경이면 DDNS를 따로 고려

## 4. 배포

미니PC에서:

```bash
cd reauth_host
cp .env.example .env
docker compose -f compose.yml up -d --build
```

`compose.yml`은 `caddy`를 함께 띄워 HTTPS를 직접 종료합니다.

## 5. 동작 확인

1. `https://reauth.bubblelab.dev/health`가 `{"status":"ok"}` 를 반환
2. backend `/api/nb-session/start-auth` 호출 시 `viewerUrl`이 `reauth.bubblelab.dev` 기준으로 생성
3. 휴대폰에서 `viewerUrl`을 열면 noVNC 화면이 표시
4. NotebookLM 로그인 완료 후 backend `/api/nb-session/internal/update`가 호출되고 `nb_sessions`가 갱신

## 6. 보안 규칙

- viewer URL은 세션별 1회용 토큰을 포함
- 동시 세션은 처음엔 `1`로 제한
- 세션 TTL은 `10~15분`
- 완료/실패/타임아웃 시 브라우저 프로필 디렉터리 삭제
- `REAUTH_HOST_API_KEY` 와 `REAUTH_CALLBACK_TOKEN` 은 충분히 긴 랜덤 값 사용
