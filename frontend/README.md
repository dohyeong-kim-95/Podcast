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
NEXT_PUBLIC_SUPABASE_URL=https://ocjsumocbjrfxgavmjze.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=...
NEXT_PUBLIC_WEB_PUSH_PUBLIC_KEY=...
NEXT_PUBLIC_API_BASE_URL=https://<cloud-run-service>.run.app
```

## Auth and deployment notes

- Supabase Google OAuth is used for login.
- Add `https://podcast.bubblelab.dev/auth/callback` to Supabase Auth redirect URLs.
- Add `http://localhost:3000/auth/callback` for local development.
- `public/sw.js` handles standard Web Push notifications via the browser Push API.
- Do not set `STATIC_EXPORT=1` for the Vercel production deployment.

## Build

```bash
npm run build
```

## Fallback path

The repo still supports static export when `STATIC_EXPORT=1` is set, but the primary launch path is the Vercel deployment on `https://podcast.bubblelab.dev`.

## Related docs

- `../docs/trd.md`
- `../docs/vercel-deploy.md`
