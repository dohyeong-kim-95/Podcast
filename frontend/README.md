# Frontend

Next.js 14 App Router frontend for the Podcast PWA.

Primary production target:

- frontend hosting: Vercel
- production domain: `https://podcast.bubblelab.dev`
- backend API: existing Cloud Run service via `NEXT_PUBLIC_API_BASE_URL`

## Local development

```bash
npm install
npm run dev
```

Default local URL: `http://localhost:3000`

## Environment variables

Copy from `frontend/.env.example` and set:

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

## Auth and deployment notes

- `signInWithRedirect()` is used for Google login.
- On Vercel, `/__/auth/:path*` is rewritten to the Firebase helper origin in [next.config.mjs](./next.config.mjs).
- `public/sw.js` intentionally skips the reserved `/__/` namespace so the auth helper flow is not intercepted.
- Do not set `STATIC_EXPORT=1` for the Vercel production deployment.

## Build

```bash
npm run build
```

## Fallback path

The repo still supports static export for Firebase Hosting when `STATIC_EXPORT=1` is set, but that is a fallback path, not the primary launch target.

## Related docs

- `../docs/trd.md`
- `../docs/vercel-deploy.md`
