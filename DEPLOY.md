# Deployment

Frontend and backend deploy **separately**, per ARCHITECTURE.md §3:

| Piece | Host | Deploys from |
|---|---|---|
| Database | Neon (free tier, EU/Frankfurt) | — |
| Backend (FastAPI) | Render | `backend/` via `render.yaml` |
| Frontend (Next.js) | Vercel | `frontend/` |
| Price sync | Admin UI button (Pricing → "Run price sync"); GitHub Actions manual dispatch as fallback | `.github/workflows/sync-prices.yml` |

Order matters: **Neon → Render → Vercel**. The backend needs the database
URL, and the frontend needs the backend URL.

---

## 1. Database (Neon)

1. Create a project at [neon.tech](https://neon.tech) — region
   **EU (Frankfurt)**. NL customer data (`payouts.iban`, contact details)
   belongs in the EU, and it keeps latency low for NL customers.
2. Copy the **Connection string** from the project dashboard. It looks like:
   `postgresql://neondb_owner:pass@ep-xxx.eu-central-1.aws.neon.tech/neondb?sslmode=require`
3. Keep `?sslmode=require` on the end — Neon rejects plaintext connections.
   No other reformatting needed: `app/core/config.py` rewrites
   `postgresql://` to `postgresql+psycopg://` itself.

> A Render-managed Postgres was used briefly on 2026-08-16 and migrated to
> Neon the same day: Render's free tier is **deleted on expiry** and has no
> backups. Neon's free tier auto-suspends after ~5 min idle instead — a cold
> first request is slow, but nothing is destroyed.

Schema and seed data are **not** applied here — `alembic upgrade head` runs
in the API's start command on first deploy, and seeding is a one-off, see
step 4.

## 2. Render (backend)

1. **New → Blueprint**, point at this repo. Render reads `render.yaml` and
   creates `tradein-api`.
2. It will prompt for the three secrets marked `sync: false`:

   | Variable | Value |
   |---|---|
   | `DATABASE_URL` | the Neon connection string from step 1 |
   | `ENCRYPTION_KEY` | generate with the command below |
   | `CORS_ORIGINS` | leave blank for now — fill in after step 3 |

   ```bash
   # Stdlib only - works in any terminal. A Fernet key is just 32 random
   # bytes, base64url-encoded; importing cryptography here would need the
   # project venv, which a plain `python3` on macOS does not have.
   python3 -c "import base64, os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())"
   ```

   > ⚠️ **`ENCRYPTION_KEY` must never change once real payouts exist.** It
   > decrypts `payouts.iban`; rotating it makes every stored IBAN
   > permanently unreadable. Store it in a password manager now.
   > `JWT_SECRET` is auto-generated and *is* safe to rotate — doing so only
   > signs out active admin sessions.

3. Wait for the deploy, then confirm: `curl https://<your-app>.onrender.com/health`
   → `{"status":"ok"}`

   The free plan sleeps after ~15 min idle, so the first request after a
   quiet period takes ~30s. §3 flags upgrading to Starter ($7/mo) before
   real customer traffic for this reason.

## 3. Vercel (frontend)

The app lives in `frontend/`, not the repo root — set the root directory or
Vercel will fail to find the Next.js app.

**Dashboard:** Import the repo → set **Root Directory** to `frontend`.

**CLI:**
```bash
npm i -g vercel
cd frontend && vercel        # preview
vercel --prod                # production
```

Set one environment variable, for all environments:

| Variable | Value |
|---|---|
| `NEXT_PUBLIC_API_URL` | `https://<your-app>.onrender.com` (no trailing slash) |

It's `NEXT_PUBLIC_*`, so it's inlined at **build** time — after changing it
you must redeploy, not just restart.

## 4. Close the loop

1. **CORS** — set `CORS_ORIGINS` on Render to the Vercel URL
   (`https://trade-nl.vercel.app`), then redeploy. Without this the browser
   blocks every API call and the catalog silently renders empty.
2. **Seed devices + questionnaire** — one-off. Render's Shell tab is a
   **paid-plan feature**, so on free you run these from your own machine,
   pointed at the Neon connection string from step 1:

   ```bash
   cd backend && export DATABASE_URL='<neon connection string>'
   .venv/bin/python -m scripts.seed_db
   ```

   Loads `seed-data/devices.json` + `questions.json`, and is idempotent.
   Note this is only the **11-device seed set**, not the full catalog — see
   step 4.

3. **Create an admin user** — nothing can log in until this runs:

   ```bash
   .venv/bin/python -m scripts.create_admin you@example.com --payouts
   ```

   Prompts for the password on stdin (never argv, never shell history);
   minimum 12 characters. `--payouts` grants the §5 payouts permission —
   omit it for general staff.

4. **Populate the full catalog.** The seed set is 11 devices with no
   prices. The real 233-device catalog came from the importer plus sync
   runs, so either re-run them against the deployed database (slow — each
   device is scraped one at a time):

   ```bash
   .venv/bin/python -m scripts.import_catalog_from_buyback
   .venv/bin/python -m scripts.sync_competitor_prices
   ```

   …or copy what a working local database already has, which is faster and
   produces identical rows:

   ```bash
   pg_dump "$LOCAL_URL" -t devices -t base_prices -t competitor_prices \
     -t price_history --data-only | psql "$DATABASE_URL"
   ```

   Either way, run `unset DATABASE_URL` afterwards or your local work will
   keep writing to production.

   Device images are separate — `fetch_device_images.py` is a local,
   commit-the-output step:
   ```bash
   .venv/bin/python -m scripts.fetch_device_images   # see caveat below
   ```

   > `fetch_device_images.py` writes files into `frontend/public/devices/`,
   > which only helps at **build** time on Vercel — Render's filesystem is
   > ephemeral and isn't served by the frontend. Run it locally, commit the
   > images, and let Vercel serve them (that's how the 233 committed PNGs
   > got there). Moving to object storage would decouple this; see the
   > rights caveat in TASKS.md before scaling image handling further.

5. **GitHub Actions secrets** — add `DATABASE_URL`, `JWT_SECRET`,
   `ENCRYPTION_KEY` under Settings → Secrets → Actions so the price sync can
   reach the database directly (§7 — it bypasses the API by design). Use the
   database's **external** connection string here, not the internal one:
   GitHub's runners are outside Render's network. The workflow
   has no schedule: run it from Actions → "Sync competitor prices" → Run
   workflow. Day to day, staff use the admin UI button instead (Pricing →
   "Run price sync"); this workflow is the fallback for when the API is
   down or spun down.

## Verifying a deploy

```bash
curl https://<render-app>.onrender.com/health
curl https://<render-app>.onrender.com/api/v1/devices | head -c 300
```
Then open the Vercel URL: the catalog should list devices with prices and
images, and `/admin/login` should accept your admin user.

## Rollback

- **Vercel** — Deployments tab → previous build → *Promote to Production*. Instant.
- **Render** — Events tab → *Rollback* to a previous deploy.
- **Database** — Neon keeps point-in-time history and can restore by
  creating a branch at an earlier timestamp; the free plan's retention
  window is short (verify the current term in the Neon dashboard), so don't
  treat it as a backup strategy for real payout data. A rollback across a
  migration is *not* automatic either: `alembic downgrade` must be run
  deliberately.
