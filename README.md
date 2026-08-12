# Phone Trade-In Platform (Netherlands)

Web platform for customers to get a price to sell their used Apple/Samsung
phones, based on competitor buyback prices plus a configurable markup, minus
condition-based deductions. See [ARCHITECTURE.md](./ARCHITECTURE.md) for the
full spec — read it before making changes.

Build progress is tracked in [TASKS.md](./TASKS.md).

## Repo layout

- `backend/` — FastAPI + SQLModel API
- `frontend/` — Next.js 14 App Router customer + admin UI
- `seed-data/` — starter device catalog and questionnaire content
- `.github/workflows/` — scheduled competitor price sync

## Local development

### Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then fill in DATABASE_URL (Neon connection string), JWT_SECRET, ENCRYPTION_KEY
alembic upgrade head
python -m scripts.seed_db
uvicorn app.main:app --reload
```

API runs at `http://localhost:8000`. Health check: `GET /health`.

### Frontend

```bash
cd frontend
npm install
cp .env.local.example .env.local   # set NEXT_PUBLIC_API_URL
npm run dev
```

App runs at `http://localhost:3000`.

### Tests

```bash
cd backend
pytest
```

## Notes

- Local dev used Python 3.14 (Python 3.12 specified in ARCHITECTURE.md §3 was
  not available on this machine). No version-specific code was used; switch
  interpreters if strict parity matters.
  # TODO(assumption): confirm Python 3.12 vs whatever's actually deployed on Render.
