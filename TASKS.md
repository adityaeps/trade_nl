# Build tasks

Tracks progress against the build order in `ARCHITECTURE.md` §10. Check
items off as they're completed — Claude Code should update this file at the
end of each working session so progress is visible across sessions, not
just within one.

Legend: `[owner: business]` = a decision only you can make, not something
Claude Code should resolve on its own.

## Sprint 0 — Foundations & spec

- [x] Business rules defined (pricing formula, fulfillment flow, no payment gateway)
- [x] Tech stack chosen (FastAPI + Next.js + Neon + GitHub Actions, all free-tier)
- [x] `ARCHITECTURE.md` written
- [x] `CLAUDE.md` written
- [x] `README.md` written
- [x] Starter device catalog (`seed-data/devices.json`)
- [x] Real iPhone + Samsung questionnaires modeled (`seed-data/questions.json`)
- [ ] Resolve open questions in `seed-data/questions.json`: missing Samsung
      housing question, Samsung screen-condition options, which Samsung
      models get `has_s_pen = true`, "not sure" battery deduction policy
      `[owner: business]`
- [ ] Decide UI language — Dutch, English, or both `[owner: business]`

## Sprint 1 — Data layer

- [x] SQLModel models for every table in `ARCHITECTURE.md` §5
- [x] Alembic migration: initial schema
- [x] Seed script: load `seed-data/devices.json` + `questions.json` into the db
      (`backend/scripts/seed_db.py`, run as `python -m scripts.seed_db`)
- [x] Confirm seed script correctly handles `depends_on`,
      `requires_device_attribute`, and `is_disqualifying` fields — verified
      against a local Postgres: branching resolves to the right parent
      question, S-Pen question carries `requires_device_attribute`, 2
      `rejected` + 7 `manual_review` disqualifying rules loaded correctly.

  Schema additions beyond the original §5 draft — confirmed and folded back
  into `ARCHITECTURE.md` itself (§3, §5) as the source of truth, not just
  left as code comments:
  - `questions.requires_device_attribute` (str, nullable) — storage column
    for device-attribute gating, required by §6, needed by the S-Pen question.
  - `questions.type` enum gained `device_selector` — used by the
    storage-capacity question in `questions.json`.
  - `quotes.customer_name/email/phone` are nullable — `POST /quotes` (§8)
    only takes `{device_id, answers}`; customer details arrive at confirm.
  - `payouts.iban` encrypted at the column level via a Fernet
    `TypeDecorator` (`app/core/crypto.py`), per §5's encryption note.
  - Local dev pinned to Python 3.14 (3.12 unavailable on this machine);
    `requirements.txt` bumped to releases with 3.14 wheels, no
    version-specific code written. §3 now documents this and still specifies
    3.12 at deploy time via Render's `runtime.txt`.

## Sprint 2 — Pricing engine

- [x] `calculate_reference_price()` — competitor average, single-source fallback
- [x] `calculate_quote_price()` — apply deductions
- [x] Disqualification short-circuit (`is_disqualifying` → `rejected`/`manual_review`, skip price calc)
- [x] Branching-question resolution (`depends_on`) before deduction lookup
- [x] Device-attribute gating (`has_s_pen`) filters the question set before it's shown
- [x] Unit tests: single-competitor fallback, stacked deductions, price
      floored at 0, SIM-lock → rejected, water damage → manual_review,
      `powers_on = no` → manual_review, branching skip logic
      (`backend/tests/test_pricing_engine.py`, 13 tests passing)

  **Known deviation from ARCHITECTURE.md §2: `markup_pct` is not applied.**
  §2 specifies `final_price = (reference_price × (1 + markup_pct/100)) −
  deductions`, but `calculate_quote_price()` only subtracts deductions —
  the markup multiplication was never implemented (originally an
  oversight, caught 2026-08-08). Business decision on discovery: **keep it
  off for now**, so customer-facing prices are the raw BuyBack.nl
  reference price and can be verified 1:1 against their site. All
  `base_prices.markup_pct` values were set to `0.00` so stored data
  matches actual behavior rather than implying an uncharged 3%.
  `markup_pct` stays in the schema as an admin-configurable field (§11).
  To re-enable: apply the multiplier in `calculate_quote_price()`, pass
  `markup_pct` through from `api/v1/quotes.py`, and add a unit test —
  the field and plumbing are already there.

## Sprint 3 — Public API

- [x] `GET /devices`, `GET /devices/{slug}`
- [x] `POST /quotes` (create + calculate)
- [x] `GET /quotes/{id}`
- [x] `POST /quotes/{id}/confirm`
- [x] `GET /stores?postal_code=` (endpoint exists per §8; postal_code isn't
      used to sort yet - haversine/geocoding are Sprint 5 per this file's
      own split, not folded in early)

  `GET /devices/{slug}` also returns each question's `deduction_rules` -
  not in the original §5/§8 surface, added so the frontend can show a live
  price/disqualification preview while answering without persisting a
  draft Quote (quotes are frozen at creation, §2 - see Sprint 4 note).

## Sprint 4 — Customer frontend: catalog & questionnaire

- [x] Catalog / brand + model picker
- [x] Device detail page ("up to €X")
- [x] Questionnaire UI with live price recalculation
- [x] Branching-question UI (sub-checklist appears only when parent = "no")
- [x] Disqualification screens: rejected message (SIM-lock) vs. manual-review
      message (water damage, broken screen/housing, won't power on)
- [x] Confirmation page: fulfillment choice + IBAN / account holder form

  Verified end-to-end in browser against the local Postgres: catalog →
  device detail → live branching/estimate → quote creation → both
  disqualification screens → store-fulfillment confirm → payout row
  created. `quote/[id]` renders as a frozen quote *result* screen rather
  than a live "questionnaire with recalculation" as ARCHITECTURE.md §4's
  route comment literally says - the questionnaire itself now lives on
  the device detail page (client-side estimate only), and `POST /quotes`
  is only called once, on submit, to keep "quotes are frozen once
  created" (§2) true instead of persisting draft quotes per keystroke.

  Seeded `backend/scripts/seed_demo_pricing.py` (base_prices + 3 stores)
  so the catalog/confirm pages had something to render before Sprint 7
  existed - devices.json has no pricing and no stores exist yet (Sprint 6).
  Its base_prices are now superseded by real `sync_competitor_prices.py`
  output (Sprint 7) for every device that script covers; the 3 demo stores
  are still standing in for Sprint 6's store CRUD.

### Device images (added outside the original sprint plan)

- [x] `backend/scripts/fetch_device_images.py` — downloads one product image
      per device into `frontend/public/devices/<slug>.png` and sets
      `devices.image_url`. Served by Next.js/Vercel's CDN, so no
      third-party image host or account is needed.
- [x] Catalog + device detail pages render `image_url`, falling back to the
      built-in brand-logo tile if it's null **or** if the file 404s at
      runtime (so a removed image degrades quietly, never a broken icon).

  **⚠ Rights caveat — revisit before launch.** These images are currently
  pulled from BuyBack.nl's product pages. Unlike the price sync (facts,
  with a ToS/robots review behind it), product photography is a
  copyrighted work owned by BuyBack.nl or the manufacturer, and we compete
  with BuyBack for the same sellers. Fetched at the business owner's
  explicit direction on their confirmation of rights — flagged here
  because it's a materially different risk from the price scraping and
  shouldn't get lost.

  Fully reversible: `python -m scripts.fetch_device_images --clear`
  unsets every `image_url` and the UI reverts to placeholders; delete
  `frontend/public/devices/*.png` to remove the files. Provenance for
  every file (source URL, fetch timestamp, size) is recorded in
  `frontend/public/devices/SOURCES.json` so individual images can be
  swapped for owned/licensed replacements one at a time.

  Preferred long-term source: photograph the devices in-house — you
  physically handle every one of these, and owned assets carry no takedown
  or breakage risk. Only `SOURCE` in the script changes; the DB just
  stores a public path.

## Sprint 5 — Store locator

- [ ] Leaflet + OpenStreetMap map integration
- [ ] Nominatim: postal code → lat/lng
- [ ] Haversine nearest-store sorting

## Sprint 6 — Admin: catalog & pricing

- [x] Admin auth (JWT) — `POST /admin/auth/login` + `GET /admin/auth/me`,
      `get_current_admin` dependency guarding every admin route, login page
      and auth-gated `/admin` layout. Accounts created via
      `python -m scripts.create_admin <email> [--payouts]` (password read
      from stdin, never argv).
- [x] Device CRUD (including `has_s_pen` toggle) — `/admin/catalog`
- [x] Base price / markup editor — `/admin/pricing`
- [x] Question builder UI — `/admin/questions`, supports configuring
      `depends_on` (parent question + triggering answer, with the child
      visually indented) and `is_disqualifying` (+ `rejected` /
      `manual_review` status), not just flat lists.

  New table **`admin_users`** (not in ARCHITECTURE.md §5, which never said
  where admin credentials live). `can_view_payouts` is a per-account
  boolean implementing §5's requirement that payouts be readable only by
  admins with a specific payouts permission — enforced by the
  `require_payouts_permission` dependency, ready for Sprint 8's payout
  screens. Deliberately a single flag, not full RBAC, for MVP.

  **Deletes are soft** (`is_active = false`), not hard: quotes reference
  devices and §2 requires stored quotes stay intact, so a hard delete would
  orphan quote history. The UI says "Deactivate"/"Reactivate" accordingly.

  Server-side validation the UI relies on (all covered by 422s, verified):
  `depends_on_question_id`/`depends_on_value` must be set together, can't
  self-reference, and the value must be a real option on the parent
  question; `disqualify_status` is required iff `is_disqualifying`;
  deleting a question that others branch off is refused with a list of
  the dependents rather than silently orphaning them.

  **Replaced `passlib` with `bcrypt` directly.** passlib 1.7.4 (last
  released 2020) is incompatible with bcrypt 5.x and raises a spurious
  "password cannot be longer than 72 bytes" on short passwords. Passwords
  are SHA-256 pre-hashed before bcrypt (same approach as passlib's
  `bcrypt_sha256`) so length is unbounded and no two long passwords
  sharing a 72-byte prefix can collide.

### Catalog import (added outside the original sprint plan)

- [x] `backend/scripts/import_catalog_from_buyback.py` — discovers every
      iPhone / Samsung Galaxy model BuyBack.nl lists (132 found), filters to
      those released within 6 years (`MIN_RELEASE_YEAR = current − 6`, so
      2020+ as of 2026), and upserts one device row per storage variant.
      **92 models → 233 device rows**, 40 models skipped as too old, 0 failed.
      Writes `seed-data/buyback_slugs.json` so the price/image scripts can
      resolve each model without re-deriving BuyBack.nl's irregular slugs.

  Release years are a hardcoded map — BuyBack.nl doesn't publish them and
  "how old is this model" was the filter requested. Models missing from
  that map are skipped with a warning rather than guessed at, so a newly
  listed model is surfaced instead of silently mis-filtered.

  `has_s_pen` is set from a documented default (Note line, S-series Ultra
  from S21 Ultra on, Z Fold from Fold 3 on) — 34 devices flagged. This is
  the open catalog question from `questions.json`; still
  `[owner: business]` to confirm, now with a sensible starting point
  rather than only the S25 Ultra.

  Two parsing bugs found and fixed by running it for real: `"Galaxy S20+"`
  and `"Galaxy S20"` collided on the unique slug index (`+` was stripped
  before slugifying, now becomes `plus`), and 12 mid-range Samsungs label
  storage as `"128GB/4GB"` (storage/RAM) which the storage regex rejected.
  The price sync matches those on the storage part and takes the
  lowest-RAM variant — deliberately conservative, since higher-RAM
  variants generally fetch more and under-quoting beats over-quoting.

## Sprint 7 — Competitor price sync

- [ ] Manual price-entry admin form (first version) — skipped ahead of this
      per explicit request; also blocked on admin auth (Sprint 6)
- [x] `scripts/sync_competitor_prices.py`
- [x] ~~GitHub Actions scheduled workflow~~ → manual-dispatch only
      (`.github/workflows/sync-prices.yml`)
- [x] "Run price sync" button in admin → Pricing (2026-08-15)

  Built out of §10's suggested order (manual form first) at explicit
  request. ToS + robots.txt for both sites reviewed 2026-08-08 - neither
  prohibits automated access; see the script's module docstring for detail.

  - **BuyBack.nl: fully working**, verified live against all 11 seed
    devices with real reference prices now in `base_prices` (replacing the
    Sprint 4 demo/placeholder numbers). Walks their real 5-question
    condition wizard (`/ajax/get_next_model_attr_v2.php`), choosing the
    best-condition answer at each step.
  - **Swappie.nl: blocked, disabled.** Their pricing API
    (`swappie.com/api/sell/api/v3/prices/`) sits behind Cloudflare bot
    protection - returns a JS challenge page to any plain HTTP client
    regardless of headers, confirmed with several realistic browser
    header combinations. `fetch_swappie_price()` is implemented and
    correct (validated against the real API response shape via browser
    inspection), but can't pass that challenge as-is. **Decision (business,
    2026-08-08): accept single-source reference prices from BuyBack.nl
    only for now** rather than add headless-browser (Playwright) infra to
    CI - `calculate_reference_price()` already falls back to a single
    source cleanly (§6), same as it already does for Samsung. Gated off
    via `SWAPPIE_ENABLED = False` in the script (not deleted) so it's a
    one-line flip if Swappie access gets solved later.
  - Model→slug mapping for BuyBack.nl needed explicit overrides for
    Samsung (URL prefix + inconsistent hyphenation) and the iPhone SE -
    `BUYBACK_SLUG_OVERRIDES` covers every device in today's
    `seed-data/devices.json`; new catalog devices need an entry added
    (or matching the naive lowercase-hyphenate fallback) before syncing.
  - **Schedule dropped (business, 2026-08-15).** The daily `cron` is gone —
    the API isn't up around the clock, so the sync now runs on demand from
    the admin UI (Pricing → "Run price sync", `POST /api/v1/admin/price-sync`,
    background thread + progress polling, one run at a time). The workflow
    stays as `workflow_dispatch`-only for when the API is down or asleep.
    Because each device commits on its own, a run cut short keeps what it
    already synced; the "Only devices with no price" checkbox re-runs just
    the stragglers. Consequence worth watching: prices are now only as
    fresh as the last time someone remembered to press the button — the
    `Synced` column and the staleness filter on
    `GET /admin/competitor-prices` are the only things surfacing that.
  - Samsung's BuyBack.nl questionnaire uses different option labels than
    iPhone's (e.g. battery "Goed"/"Normaal"/"Zwak" vs. iPhone's "Ja"/"Nee")
    - the picker falls back to "first listed option" (observed to always
      be best-condition) when no known label matches, logging a warning
      each time so these are auditable, not silent.

## Sprint 8 — Admin: orders & payouts

- [ ] Quote/order list with status filters (including `manual_review`, `rejected`)
- [ ] Payout queue + CSV export for bank bulk upload
- [ ] Mark-as-paid action

## Sprint 9 — Deploy

Code is deploy-ready and pushed to `github.com/adityaeps/trade_nl`. The
four items below all require signing in to a third-party account, so they
need you — see [DEPLOY.md](./DEPLOY.md) for the step-by-step runbook.

- [ ] Database provisioned `[owner: business]` — **now Render Postgres, not
      Neon** (decided 2026-08-16, to keep db and API on one provider).
      `render.yaml` declares `tradein-db` and wires `DATABASE_URL` in via
      `fromDatabase`, so there is no connection string to paste. Free tier
      expires and has no backups — move to paid before real payout data
- [ ] Render backend deployed `[owner: business]` — `render.yaml` blueprint
      is committed; Render prompts for `DATABASE_URL`, `ENCRYPTION_KEY`,
      `CORS_ORIGINS` on first deploy
- [ ] Vercel frontend deployed `[owner: business]` — set Root Directory to
      `frontend` and `NEXT_PUBLIC_API_URL` to the Render URL
- [ ] GitHub Actions secrets configured for the price-sync workflow
      `[owner: business]` — `DATABASE_URL`, `JWT_SECRET`, `ENCRYPTION_KEY`.
      Still worth setting up even though the workflow no longer runs on a
      schedule: it's the fallback way to sync when the API is asleep.

  Prepared and verified locally:
  - `render.yaml` — backend blueprint, Python pinned to 3.12 per §3,
    `alembic upgrade head` on start, `/health` healthcheck.
  - `frontend/vercel.json` + `backend/runtime.txt`.
  - `DEPLOY.md` — full runbook including rollback and the
    `ENCRYPTION_KEY`-must-never-rotate warning (rotating it makes every
    stored IBAN permanently unreadable).
  - `config.py` normalises the `postgresql://` URL managed providers hand
    out to `postgresql+psycopg://`; without it the app dies at startup
    reaching for psycopg2, which isn't installed.
  - Production build passes (`next build`), which caught a TypeScript
    error `next dev` had been hiding, and a missing `/admin` index route.
