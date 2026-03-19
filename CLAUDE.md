# Podcast — Project Conventions

## Project Structure
- `backend/` — Python FastAPI (Cloud Run)
- `frontend/` — Next.js 14 App Router (Firebase Hosting)
- `docs/` — PRD, TRD, tasks

## Backend (Python)
- Python 3.11, FastAPI
- Run: `cd backend && uvicorn app.main:app --reload --port 8080`
- Test: `cd backend && python -m pytest`
- Code style: snake_case, type hints, async functions
- Router files in `app/routers/`, services in `app/services/`, Pydantic models in `app/models/`

## Frontend (Next.js)
- Next.js 14 with App Router, TypeScript, Tailwind CSS
- Run: `cd frontend && npm run dev`
- Build: `cd frontend && npm run build`
- Lint: `cd frontend && npm run lint`
- Pages in `src/app/`, components in `src/components/`, utilities in `src/lib/`
- Mobile-first, dark theme (Spotify style)

## Naming Conventions
- Backend: snake_case (Python)
- Frontend: camelCase for variables/functions, PascalCase for components
- API routes: `/api/{resource}` (RESTful)
- Firestore collections: lowercase plural (users, sources, podcasts)

## Key Dependencies
- Backend: fastapi, firebase-admin, google-auth, img2pdf, cryptography, httpx
- Frontend: next, react, tailwindcss, firebase

## Environment Variables
- See `backend/.env.example` for required backend env vars
