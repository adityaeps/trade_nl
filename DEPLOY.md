# Deployment

Frontend and backend deploy **separately**, per ARCHITECTURE.md §3:

| Piece | Host | Deploys from |
|---|---|---|
| Database | Neon (free tier) | — |
| Backend (FastAPI) | Render | `backend/` via `render.yaml` |
| Frontend (Next.js) | Vercel | `frontend/` |
| Price sync | Admin UI button (Pricing → "Run price sync"); GitHub Actions manual dispatch as fallback | `.github/workflows/sync-prices.yml` |

Order matters: **Neon → Render → Vercel**. The backend needs the database
URL, and the frontend needs the backend URL.

---

## 1. Neon (database)

1. Create a project at [neon.tech](https://neon.tech) — region **EU (Frankfurt)**
   keeps latency low for NL customers and keeps personal data in the EU
   (relevant: `payouts.iban` and customer contact details).
2. Copy the connection string. It looks like:
   `postgresql://user:pass@ep-xxx.eu-central-1.aws.neon.tech/neondb?sslmode=require`
3. Keep it for step 2 — no need to reformat it. `app/core/config.py`
   rewrites `postgresql://` to `postgresql+psycopg://` automatically.

Schema and seed data are **not** applied here yet — Render does that on
first deploy (`alembic upgrade head` runs in its start command). Seeding
the questionnaire is a one-off, see step 4.

## 2. Render (backend)

1. **New → Blueprint**, point at this repo. Render reads `render.yaml`.
2. It will prompt for the three secrets marked `sync: false`:

   | Variable | Value |
   |---|---|
   | `DATABASE_URL` | the Neon string from step 1 |
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
2. **Seed the questionnaire** — one-off, from Render's Shell tab:
   ```bash
   python -m scripts.seed_db
   ```
   This loads `seed-data/questions.json`. It's idempotent.
3. **Create an admin user** — see `scripts/create_admin.py`.
4. **Populate the catalog** — either run the importers from the Render
   shell, or dump/restore from local:
   ```bash
   python -m scripts.import_catalog_from_buyback
   python -m scripts.sync_competitor_prices
   python -m scripts.fetch_device_images   # writes into frontend/public — see caveat below
   ```

   > `fetch_device_images.py` writes files into `frontend/public/devices/`,
   > which only helps at **build** time on Vercel — Render's filesystem is
   > ephemeral and isn't served by the frontend. Run it locally, commit the
   > images, and let Vercel serve them (that's how the 233 committed PNGs
   > got there). Moving to object storage would decouple this; see the
   > rights caveat in TASKS.md before scaling image handling further.

5. **GitHub Actions secrets** — add `DATABASE_URL`, `JWT_SECRET`,
   `ENCRYPTION_KEY` under Settings → Secrets → Actions so the price sync can
   reach Neon directly (§7 — it bypasses the API by design). The workflow
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
- **Database** — Neon keeps point-in-time history; restore via branch.
  Note that a rollback across a migration is *not* automatic: `alembic
  downgrade` must be run deliberately.
