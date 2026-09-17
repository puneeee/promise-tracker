# Promise Tracker

Promise Tracker is a private accountability app for personal commitments and invite-only groups. Track recurring habits, measurable goals, and date-range promises; log progress with notes; and see transparent progress inside a trusted group.

**Live app:** [puneeee.github.io/promise-tracker](https://puneeee.github.io/promise-tracker/)
**API:** [promisetracker.onrender.com](https://promisetracker.onrender.com)

## What works today

- Google sign-in with a browser-session fallback designed for GitHub Pages + Render.
- Private personal space and private, invite-only group spaces.
- Display names: set your name from the profile control; it appears on promises you create in groups.
- Promise types: check-off, quantity, duration, cumulative, percentage, and custom quantity.
- Daily, weekly, and monthly recurring periods. Progress and check-off completion reset automatically at the next period.
- Date-range promises with start/end validation and completed/archived views.
- Progress check-ins with optional notes, cumulative history, and a graph.
- Promise editing, duplicate, archive, and restore.
- Group invite links, optional admin-approval join requests, membership roster, owner/admin roles, and owner-only group deletion.
- Group promise filters by category and member.

## Local development

### Prerequisites

- Node.js 20+
- Python 3.11+

### Backend

```powershell
cd backend
..venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

The backend uses a local SQLite database by default. For Google sign-in locally, copy `.env.example` values into your environment and configure a local Google OAuth redirect URL.

### Frontend

In a second terminal:

```powershell
cd frontend
npm install
npm run dev
```

Open the Vite URL, usually `http://localhost:5173`.

In development, the API supplies a local demo identity when Google OAuth is not enabled.

## Production configuration

The frontend is deployed to GitHub Pages and the FastAPI API is deployed to Render with PostgreSQL.

Set these Render environment variables:

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | Render PostgreSQL connection string |
| `APP_ENV` | `production` |
| `GOOGLE_CLIENT_ID` | OAuth web-client ID |
| `GOOGLE_CLIENT_SECRET` | OAuth web-client secret |
| `SESSION_SECRET` | Random server secret used to sign sessions |
| `API_URL` | Public API origin, for example `https://promisetracker.onrender.com` |
| `FRONTEND_URL` | Public frontend URL, for example `https://puneeee.github.io/promise-tracker/` |

Configure this Google OAuth redirect URI exactly:

```text
https://promisetracker.onrender.com/auth/google/callback
```

Do not commit any secret, database URL, or OAuth client secret.

## Verification

```powershell
cd frontend
npm run build
```

```powershell
cd backend
..venv\Scripts\python.exe -m compileall app
..venv\Scripts\python.exe -m unittest discover -s tests -v
```

## Documentation

- [Current product plan](docs/chapter3/03_Promise_Engine.md)
- [FAQ](docs/FAQ.md)

## Current limitations

Browser push reminders, Google Calendar group check-ins, owner/admin promise locking, activity feeds, notification scheduling, and native apps are planned but not implemented yet. See the product plan for the current roadmap.
