# Promise Tracker

An accountability app for personal commitments and private groups. The first working slice provides personal/group spaces, flexible promise tracking, append-only progress history, group visibility, locking foundations, and a polished React dashboard.

## Run locally

From the project root, start the backend with:

```powershell
.\backend\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --reload --port 8000
```

Start the frontend in a second terminal:

```powershell
cd frontend
npm run dev
```

Then open the local address Vite prints, normally `http://localhost:5173`.

The current development identity is `you@example.com`. Google OAuth, Google Calendar check-ins, invitation approval, reminders, and the remaining role-management endpoints are the next implementation milestones; their behaviour and rules are captured in [the V1 plan](docs/chapter3/03_Promise_Engine.md).

## Verification

```powershell
cd frontend
npm run build
```

```powershell
cd backend
.\.venv\Scripts\python.exe -m compileall app
```
