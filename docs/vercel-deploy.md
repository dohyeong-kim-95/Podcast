# Vercel Deployment (`podcast.bubblelab.dev`)

This project can be deployed with:

- frontend: Vercel
- backend: existing FastAPI on Cloud Run

That is the lowest-risk path. No backend rewrite is required.

## 1. Vercel project

- Import the repo into Vercel.
- Set the project root to `frontend`.
- Build command: `npm run build`
- Output directory: leave empty for normal Next.js deployment
- Do not set `STATIC_EXPORT=1` on Vercel

## 2. Required Vercel environment variables

Set these in the Vercel project:

```env
NEXT_PUBLIC_FIREBASE_API_KEY=...
NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN=podcast.bubblelab.dev
NEXT_PUBLIC_FIREBASE_PROJECT_ID=dailylmpodcast
NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET=dailylmpodcast.firebasestorage.app
NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID=...
NEXT_PUBLIC_FIREBASE_APP_ID=...
NEXT_PUBLIC_FIREBASE_VAPID_KEY=...
NEXT_PUBLIC_API_BASE_URL=https://<your-cloud-run-service>.run.app
FIREBASE_AUTH_HELPER_ORIGIN=https://dailylmpodcast.firebaseapp.com
```

`NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN` must match the domain that serves the app.
Use `NEXT_PUBLIC_API_BASE_URL` consistently across the frontend; do not rely on alternate aliases.

## 3. Why the auth proxy is needed

Firebase documents that if you host the app with a service other than Firebase and keep using `signInWithRedirect()`, you should proxy `/__/auth/*` to `<project>.firebaseapp.com` and update `authDomain`.

This repo is now set up for that:

- [next.config.mjs](/home/kimdohyeong/Working_kdh/1_Projects/002_notebooklm_py/Podcast/frontend/next.config.mjs) proxies `/__/auth/:path*`
- [sw.js](/home/kimdohyeong/Working_kdh/1_Projects/002_notebooklm_py/Podcast/frontend/public/sw.js) skips the reserved `/__/` namespace

## 4. Vercel custom domain

Add `podcast.bubblelab.dev` to the Vercel project and follow the DNS instructions shown by Vercel.

For subdomains, Vercel's documentation says the domain is typically configured with a `CNAME` record, but you should use the exact value shown by `vercel domains inspect` or the dashboard because project-specific values may differ.

## 5. Firebase console changes

In Firebase Authentication:

- add `podcast.bubblelab.dev` to Authorized domains

If you use any provider-specific OAuth client settings outside Firebase defaults, also allow:

- `https://podcast.bubblelab.dev/__/auth/handler`

## 6. Backend settings

On Cloud Run, update:

```env
CORS_ORIGINS=https://podcast.bubblelab.dev
ALLOWED_EMAILS=user1@gmail.com,user2@gmail.com
CLOUD_RUN_URL=https://<your-cloud-run-service>.run.app
SCHEDULER_SERVICE_ACCOUNT=<scheduler-service-account-email>
NB_COOKIE_ENCRYPTION_KEY=...
BROWSERLESS_TOKEN=...
BROWSERLESS_CONNECT_URL_TEMPLATE=wss://...{session_id}...{token}
BROWSERLESS_VIEWER_URL_TEMPLATE=https://.../sessions/{session_id}?token={token}
```

If you want preview deployments to work against production backend, also add the preview domain(s).

## 7. Recommended DNS layout

- `podcast.bubblelab.dev` -> Vercel
- API stays on `run.app` for now

You can move the API to a custom subdomain later, but it is not required for the frontend launch.

## 8. Verification checklist

After deploy:

1. Open `https://podcast.bubblelab.dev`
2. Confirm Google login works
3. Confirm `POST /api/auth/verify` succeeds
4. Confirm `/upload`, `/memory`, `/settings` all load
5. Confirm `GET /health` works on the backend URL
6. Confirm login redirect path `https://podcast.bubblelab.dev/__/auth/handler` returns successfully
7. Confirm service worker registration still works
8. Confirm push permission flow still stores `fcmToken`

You can automate the basic HTTP checks with:

```bash
APP_URL=https://podcast.bubblelab.dev \
API_URL=https://<your-cloud-run-service>.run.app \
./scripts/smoke-vercel-launch.sh
```

## 9. Rollback hints

Use the smallest rollback that restores service:

1. If only the frontend deploy is broken, roll back to the previous successful Vercel deployment and leave Cloud Run unchanged.
2. If the frontend is healthy but API calls fail, revert Cloud Run config or image separately; avoid changing DNS at the same time.
3. Only repoint `podcast.bubblelab.dev` away from Vercel if you already have another warmed-up frontend target with matching Firebase Auth settings.

Changing DNS and backend config together is the highest-risk rollback path. Avoid it unless the simpler rollback options have already failed.
