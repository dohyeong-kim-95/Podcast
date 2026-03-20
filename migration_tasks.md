# Firebase -> Supabase Migration Tasks

## Goal

Remove all Firebase dependencies from the project and replace them with:

- Supabase Auth for Google sign-in
- Supabase Postgres for application data
- Supabase Storage for file storage
- Standard Web Push (VAPID) for browser notifications

This migration is complete only when:

- no runtime code depends on Firebase client SDK or Firebase Admin SDK
- no backend API depends on Firestore, Firebase Storage, or FCM
- all current user-facing flows work on Supabase-backed infrastructure

## Target Architecture

### Frontend

- Next.js authenticates with Supabase Auth
- Google login uses Supabase OAuth
- frontend sends Supabase access token to backend as `Authorization: Bearer <token>`
- service worker handles standard Web Push notifications

### Backend

- FastAPI verifies Supabase user tokens
- FastAPI reads/writes Postgres instead of Firestore
- FastAPI uploads/downloads/signs files from Supabase Storage
- FastAPI sends Web Push notifications with VAPID instead of FCM

### Data Model

- `profiles`
- `user_memory`
- `sources`
- `podcasts`
- `nb_sessions`
- `nb_auth_sessions`
- `push_subscriptions`

### Storage Buckets

- `sources`
- `podcasts`

## Execution Plan

### Phase 1. Inventory and schema design

- [done] Identify every Firebase usage point in frontend, backend, tests, and docs
- [done] Define the Postgres schema that replaces Firestore documents/subcollections
- [done] Define Supabase Storage bucket layout and object path rules
- [done] Define Web Push replacement for FCM token flow

Completion criteria:

- all Firebase-backed entities have a Supabase-backed replacement
- migration scope is explicit enough to implement without guessing

### Phase 2. Supabase foundation

- [done] Add backend Supabase/Postgres configuration layer
- [done] Add frontend Supabase client configuration layer
- [done] Add SQL migration for tables, indexes, and constraints
- [done] Add Supabase env examples for frontend and backend

Completion criteria:

- project has concrete env names and migration SQL
- runtime code can initialize Supabase/Postgres without Firebase

### Phase 3. Auth migration

- [done] Replace frontend Firebase auth state with Supabase session state
- [done] Replace Google sign-in flow with Supabase OAuth flow
- [done] Add auth callback handling for Supabase redirect
- [done] Replace backend Firebase token verification with Supabase token verification
- [done] Preserve email allowlist behavior on backend

Completion criteria:

- login, logout, session restore, and backend verification work without Firebase

### Phase 4. Data and storage migration

- [done] Replace Firestore-backed profile/memory reads and writes with Postgres queries
- [done] Replace Firestore-backed source metadata with Postgres queries
- [done] Replace Firestore-backed podcast metadata with Postgres queries
- [done] Replace Firestore-backed NotebookLM session/auth-session state with Postgres queries
- [done] Replace Firebase Storage upload/download/delete/signing with Supabase Storage
- [done] Preserve generation locking semantics for `generate/me`

Completion criteria:

- all API routes read/write Supabase-backed data only
- source upload, podcast generation, signed playback URL, and cleanup work without Firebase

### Phase 5. Push migration

- [done] Replace FCM token registration with PushSubscription registration
- [done] Replace Firebase messaging client logic with browser Push API logic
- [done] Replace FCM service worker handling with standard `push` event handling
- [done] Replace backend FCM send flow with VAPID-based Web Push sender
- [done] Keep generation-complete and reminder notifications working at code/test level

Completion criteria:

- browser push registration and delivery work without Firebase/FCM

### Phase 6. Documentation and verification

- [done] Rewrite docs/env examples from Firebase to Supabase
- [done] Remove obsolete Firebase/Vercel auth-helper guidance
- [done] Update deployment and launch checklist for Supabase
- [done] Run frontend build
- [done] Run backend tests and fix regressions
- [done] List the console/manual steps the user must perform in Supabase/Vercel/Cloud Run

Completion criteria:

- repo docs match the new architecture
- local validation is complete
- remaining manual work is explicit

## Known Manual Steps

These cannot be fully completed from the CLI alone and will be handed back clearly at the end:

- run [supabase/migrations/20260320_init.sql](/home/kimdohyeong/Working_kdh/1_Projects/002_notebooklm_py/Podcast/supabase/migrations/20260320_init.sql) in Supabase SQL Editor
- create private Storage buckets `sources` and `podcasts`
- set Supabase Auth `Site URL` to `https://podcast.bubblelab.dev`
- add Supabase Auth redirect URLs:
  - `https://podcast.bubblelab.dev/auth/callback`
  - `http://localhost:3000/auth/callback`
- enable Supabase Google provider and register the Google OAuth callback URL that Supabase shows for project `ocjsumocbjrfxgavmjze`
- provide `anon key`, `service_role key`, and `SUPABASE_DB_URL`
- configure VAPID key pair and production env values in Vercel/Cloud Run
- apply Cloud Run env/secrets and redeploy the API service
- run `./scripts/smoke-vercel-launch.sh` against the real Vercel/Cloud Run URLs
- verify production flows on `https://podcast.bubblelab.dev`: login, upload, generate, Browserless re-auth, push permission, and push delivery
