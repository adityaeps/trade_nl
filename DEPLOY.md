# Deployment

Frontend and backend deploy **separately**, per ARCHITECTURE.md §3:

| Piece | Host | Deploys from |
|---|---|---|
| Database | Render Postgres (free tier) | declared in `render.yaml` |
| Backend (FastAPI) | Render | `backend/` via `render.yaml` |
| Frontend (Next.js) | Vercel | `frontend/` |
| Price sync | Admin UI button (Pricing → "Run price sync"); GitHub Actions manual dispatch as fallback | `.github/workflows/sync-prices.yml` |

Order matters: **Render (db + backend) → Vercel**. The blueprint creates the
database and the API together; the frontend then needs the backend URL.

---

## 1. Database (Render Postgres)

Decided 2026-08-16: Postgres is **Render-managed**, not Neon — database and
API on one provider. This is a deviation from ARCHITECTURE.md §3; nothing in
the app cares, since `app/core/config.py` rewrites `postgresql://` to
`postgresql+psycopg://` whoever hands out the URL.

`render.yaml` declares the instance (`tradein-db`) and wires `DATABASE_URL`
into the API with `fromDatabase`, so **there is no connection string to
paste** — the blueprint creates both together. Pick region **Frankfurt** so
NL customer data (`payouts.iban`, contact details) stays in the EU.

> ⚠️ Free Postgres on Render **expires and is deleted** after a fixed window
> (verify the current term in the dashboard — recently 30 days). Move to a
> paid instance before any real customer or payout data lands in it.

Schema and seed data are **not** applied here — `alembic upgrade head` runs
in the API's start command on first deploy, and seeding is a one-off, see
step 4.

## 2. Render (backend)

1. **New → Blueprint**, point at this repo. Render reads `render.yaml` and
   creates `tradein-db` + `tradein-api` together.
2. It will prompt for the two secrets marked `sync: false`:

   | Variable | Value |
   |---|---|
   | `ENCRYPTION_KEY` | generate with the command below |
   | `CORS_ORIGINS` | leave blank for now — fill in after step 3 |

   ```bash
   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
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
   **paid-plan feature**, so on free you run these from your own machine
   pointed at the database's *external* connection string (Render dashboard
   → the database → Info → External Database URL):

   ```bash
   cd backend && export DATABASE_URL='<external url>'
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
- **Database** — Render's free Postgres tier has **no backups and no
  point-in-time restore** (that starts on the paid tiers), so there is
  currently nothing to roll back to. Take a `pg_dump` before anything
  destructive. A rollback across a migration is also *not* automatic:
  `alembic downgrade` must be run deliberately.
