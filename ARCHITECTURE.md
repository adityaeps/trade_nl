# Phone Trade-In Platform (Netherlands) — Architecture & Build Spec

## 1. What this is

A web platform where customers get a price to sell their used Apple and Samsung
phones, based on averaging competitor buyback prices (Swappie.nl for Apple,
BuyBack.nl for Apple + Samsung) plus a configurable markup, then reduced by
condition-based deductions from a questionnaire. Customers drop the device off
at a nearby partner store or ship it via courier. Payout is a manual bank
transfer — there is no payment gateway or online checkout in this system.

Read this file before writing any code. It is the source of truth for scope,
data model, and API surface. Where something isn't specified, prefer the
simplest option that matches the patterns already established here, and leave
a `# TODO(assumption): ...` comment rather than silently deciding.

## 2. Business rules (do not deviate without asking)

- **Pricing formula**: `final_price = (reference_price × (1 + markup_pct/100)) − deductions`
  - `reference_price` = average of available competitor prices for that exact
    device (fallback to single source if only one competitor lists it — true
    today for most Samsung models, since only BuyBack.nl covers Samsung).
  - `markup_pct` is set per device (or per liquidity tier), not global.
  - Deductions come from questionnaire answers, each either a flat amount or
    a percentage of `reference_price`.
- **Quotes are frozen once created.** A quote stores its own calculated price
  independent of later changes to `base_prices`. It has a `valid_until`
  (default: 7 days). Do not recompute a quote's price from live data after
  creation — only a fresh quote request produces a fresh price.
- **No online payment.** Payout is a bank transfer, done manually by staff
  from the admin panel's payout queue. The app's job is to capture
  `iban` + `account_holder_name` and track payout status — never to move
  money itself.
- **Two fulfillment paths**: `store` (customer visits a partner location) or
  `courier` (customer ships the device). Both lead to a device inspection
  step before payout is authorized.
- **Competitor prices are never fetched live during a customer request.**
  They're synced into the database by a separate job that staff start by
  hand; customer-facing reads only ever hit our own DB. See §7.

## 3. Tech stack

| Layer | Choice | Notes |
|---|---|---|
| Backend | Python 3.12, FastAPI, SQLModel, Pydantic v2 | One service, modular by domain (not microservices). Pin to 3.12 at deploy time (Render `runtime.txt`); local dev on this machine used 3.14 since 3.12 wasn't installed — no version-specific code was written, `requirements.txt` versions were bumped to releases with 3.14 wheels. Repin to 3.12-compatible versions if the deploy target build fails. |
| Migrations | Alembic | |
| Frontend | Next.js 14 (App Router), TypeScript, Tailwind CSS | |
| Database | PostgreSQL (Neon, free tier) | |
| Background jobs | Admin-triggered thread in the API, plus a manual-dispatch GitHub Actions workflow | Competitor price sync only. No cron: the API isn't up around the clock, and the business wants the sync run while someone is watching it — see §7 |
| Maps / geocoding | Leaflet.js + OpenStreetMap tiles, Nominatim | Free, no API key needed |
| Backend hosting | Render (free tier for dev; Starter $7/mo before real customer traffic, to avoid cold-start delays) | |
| Frontend hosting | Vercel (free tier) | |
| Auth | JWT-based, admin only. No customer accounts for MVP — quotes are looked up by ID/token, not login. | |
| Payments | None. Payout tracked in-app, executed manually via business banking. | |

**Explicitly out of scope for MVP** (don't build unless asked):
- Payment gateway / checkout of any kind
- Customer login/accounts
- Redis or any caching layer
- Automated PostNL courier label generation (start with a manually issued/emailed label)
- Multi-currency (EUR only)
- Multi-language UI (build in English or Dutch — confirm which before frontend work starts; don't build i18n scaffolding speculatively)

## 4. Repository structure

```
phone-tradein-nl/
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── core/
│   │   │   ├── config.py          # env var loading (pydantic-settings)
│   │   │   └── security.py        # JWT auth for admin routes
│   │   ├── models/                # SQLModel table classes, one file per table
│   │   │   ├── device.py
│   │   │   ├── pricing.py         # BasePrice, CompetitorPrice, PriceHistory
│   │   │   ├── questionnaire.py   # QuestionSet, Question, DeductionRule
│   │   │   ├── quote.py
│   │   │   ├── store.py
│   │   │   └── payout.py
│   │   ├── schemas/                # Pydantic request/response models
│   │   ├── api/
│   │   │   └── v1/
│   │   │       ├── devices.py
│   │   │       ├── quotes.py
│   │   │       ├── stores.py
│   │   │       └── admin/
│   │   │           ├── auth.py
│   │   │           ├── devices.py
│   │   │           ├── pricing.py
│   │   │           ├── questionnaire.py
│   │   │           ├── quotes.py
│   │   │           ├── stores.py
│   │   │           └── payouts.py
│   │   ├── services/
│   │   │   ├── pricing_engine.py   # pure functions, no I/O — see §6
│   │   │   ├── geocoding.py        # Nominatim lookup + haversine distance
│   │   │   └── price_sync_runner.py # admin-triggered sync + its progress (§7)
│   │   └── db/
│   │       ├── session.py
│   │       └── base.py
│   ├── alembic/
│   ├── scripts/
│   │   └── sync_competitor_prices.py   # CLI + the admin button's worker (§7)
│   ├── tests/
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── app/
│   │   ├── (customer)/
│   │   │   ├── page.tsx                    # catalog / brand+model picker
│   │   │   ├── devices/[slug]/page.tsx     # device detail, "up to €X"
│   │   │   ├── quote/[id]/page.tsx         # questionnaire, live price
│   │   │   └── quote/[id]/confirm/page.tsx # fulfillment choice + IBAN capture
│   │   └── admin/
│   │       ├── layout.tsx                  # auth-gated
│   │       ├── catalog/page.tsx
│   │       ├── pricing/page.tsx
│   │       ├── questions/page.tsx
│   │       ├── stores/page.tsx
│   │       ├── orders/page.tsx
│   │       └── payouts/page.tsx
│   ├── components/
│   ├── lib/
│   └── package.json
├── .github/
│   └── workflows/
│       └── sync-prices.yml
├── ARCHITECTURE.md
├── CLAUDE.md
└── README.md
```

## 5. Data model

```
devices
  id                 uuid, pk
  brand              enum: apple | samsung
  model              text            e.g. "iPhone 14 Pro"
  storage_gb         int
  color              text, nullable
  category           enum: phone | tablet | watch   (future-proofing; phone only for MVP)
  has_s_pen          bool, default false
    -- Samsung-only attribute. Gates whether the S-Pen condition question
    -- appears in that device's questionnaire (via depends_on on a
    -- device-level check, not a prior answer — see §6 note on device
    -- attribute gating vs. answer-based branching).
  slug               text, unique
  image_url          text, nullable
  is_active          bool
  created_at, updated_at

base_prices
  id                 pk
  device_id          fk -> devices, unique
  base_price         numeric(8,2)
  liquidity_tier     enum: high | medium | low
  markup_pct         numeric(5,2)     e.g. 3.00 means +3%
  last_synced_at     timestamp
  updated_at

competitor_prices
  id                 pk
  device_id          fk -> devices
  competitor_name    text            'swappie' | 'buyback'
  price              numeric(8,2)
  condition_tier     text            competitor's own label, e.g. "good"
  source_url         text
  checked_at         timestamp

price_history         -- append-only, for admin trend charts
  id                 pk
  device_id          fk -> devices
  base_price         numeric(8,2)
  recorded_at        timestamp

question_sets
  id                 pk
  category           enum: phone | tablet | watch
  brand              enum: apple | samsung, nullable
    -- nullable so a future category can be brand-agnostic, but phone
    -- question sets are brand-specific today: iPhone and Samsung diverge
    -- on biometric type (Face ID vs fingerprint), the S-Pen question,
    -- and how battery health is checked. A device's (category, brand)
    -- determines which question_set it uses.
  name               text

questions
  id                 pk
  question_set_id    fk -> question_sets
  text               text
  type               enum: single_select | multi_select | boolean | device_selector
    -- device_selector: not a deduction question - selects which device row
    -- (and base_price) the rest of the quote is calculated against, e.g.
    -- "What is the storage capacity?" See seed-data/questions.json and §6.
  display_order      int
  options            jsonb           [{label, value}, ...]
  depends_on_question_id  fk -> questions, nullable
  depends_on_value        text, nullable
    -- if set, this question only appears when the parent question
    -- (depends_on_question_id) was answered with depends_on_value.
    -- Powers branching flows like "does everything work?" -> if "no",
    -- show a per-function checklist (Face ID, charging, cameras, etc.)
  requires_device_attribute  text, nullable
    -- if set (e.g. "has_s_pen"), this question only appears for devices
    -- where that boolean column on `devices` is true. This is the storage
    -- for the device-attribute gating described below and in §6 - filter
    -- against the device row, not a prior answer, before rendering.

deduction_rules
  id                 pk
  question_id        fk -> questions
  option_value       text
  deduction_type     enum: percentage | fixed
  deduction_value    numeric(8,2)
  is_disqualifying   bool, default false
  disqualify_status  enum: rejected | manual_review, nullable
    -- if is_disqualifying is true, selecting this option skips normal
    -- price calculation entirely (deduction_value is ignored) and the
    -- quote's status is set to disqualify_status instead. Used for
    -- SIM-lock ('rejected' — no price at all) and water damage
    -- ('manual_review' — staff decides after physical inspection).
    -- See §6.

quotes
  id                 uuid, pk
  device_id          fk -> devices
  answers            jsonb           snapshot: {question_id: answer_value}
  base_price_at_quote numeric(8,2)   snapshot, for audit
  calculated_price   numeric(8,2)    frozen final price
  status             enum: pending | confirmed | expired | inspected | paid |
                          manual_review | rejected
    -- manual_review: a disqualifying-but-inspectable answer was given
    --   (e.g. water damage) — no automatic price shown, staff reviews
    --   after the device physically arrives.
    -- rejected: a hard-exclusion answer was given (e.g. SIM-locked) —
    --   no price offered, no inspection needed.
  fulfillment_method enum: store | courier, nullable until confirmed
  store_id           fk -> stores, nullable
  customer_name      text, nullable until confirmed
  customer_email     text, nullable until confirmed
  customer_phone     text, nullable until confirmed
    -- POST /quotes (§8) only takes {device_id, answers} - customer details
    -- aren't collected until POST /quotes/{id}/confirm, so these can't be
    -- required at creation time.
  valid_until        timestamp
  created_at, updated_at

stores
  id                 pk
  name               text
  address_line       text
  city               text
  postal_code        text
  lat, lng           float
  opening_hours       jsonb
  is_active          bool

payouts
  id                 pk
  quote_id           fk -> quotes, unique
  iban               text (encrypted at rest)
  account_holder_name text
  amount             numeric(8,2)
  status             enum: pending | paid
  paid_at            timestamp, nullable
  created_at
```

**Encryption note**: `iban` should be encrypted at the application or column
level (e.g. `pgcrypto`, or application-layer encryption before insert) — not
stored in plaintext. Implemented as a Fernet-based SQLAlchemy `TypeDecorator`
(`backend/app/core/crypto.py`, keyed by the `ENCRYPTION_KEY` env var) applied
to the `payouts.iban` column, so the column stores ciphertext and application
code always sees plaintext transparently. Payout records should only be readable by admin roles
with a specific `payouts` permission, not the general admin role.

## 6. Pricing engine (`services/pricing_engine.py`)

Keep this module pure — no DB or HTTP calls inside it — so it's easy to unit
test. Two core functions:

```python
def calculate_reference_price(competitor_prices: list[CompetitorPrice]) -> Decimal:
    """Average of available competitor prices. Falls back to the single
    available price if only one competitor lists the device."""

def calculate_quote_price(
    base_price: Decimal,
    answers: dict[str, str],
    deduction_rules: list[DeductionRule],
) -> Decimal:
    """Applies each matching deduction rule to base_price and returns the
    final price, floored at 0."""
```

The API layer (`api/v1/quotes.py`) is responsible for fetching the current
`base_price` and the device's `deduction_rules`, calling these functions, and
persisting the result as a frozen `Quote`.

**Disqualifying answers short-circuit pricing.** Before running the normal
deduction math, check whether any submitted answer matches a
`deduction_rules` row with `is_disqualifying = true`. If so, skip
`calculate_quote_price` entirely and set the quote's `status` to that rule's
`disqualify_status` (`rejected` for SIM-lock, `manual_review` for water
damage) with no `calculated_price`. The frontend shows a clear explanation
instead of a price in this case.

**Branching questions are resolved before deduction lookup**, not during it.
Given the full answer set, first filter out any question whose
`depends_on_question_id`/`depends_on_value` doesn't match what was actually
answered — a customer who said "yes, everything works" never sees or answers
the per-function checklist, so those questions simply aren't in the answer
set and contribute no deductions. Device-level gating (like `has_s_pen`)
works the same way but checks the device row instead of a prior answer —
filter the question set against the device's attributes before rendering it
to the customer at all, so incompatible questions never appear in the first
place.

## 7. Competitor price sync (`scripts/sync_competitor_prices.py`)

- **Manual trigger only — nothing runs it on a schedule.** The original
  daily `cron` in `.github/workflows/sync-prices.yml` was removed at the
  business's request: the API isn't up around the clock, and they want the
  sync run while someone is watching the result. Two ways to start it:
  - **Admin UI** (the day-to-day path): Pricing → "Run price sync" →
    `POST /api/v1/admin/price-sync`, which runs `sync_device()` on a
    background thread via `app/services/price_sync_runner.py` and reports
    progress through `GET /api/v1/admin/price-sync`. One run at a time
    (a second request gets a 409); run state is in-process memory, so it
    resets on restart and assumes a single API instance.
  - **GitHub Actions**, `workflow_dispatch` only, connecting directly to
    the Neon database — the fallback for when the API itself is down or
    asleep.
- Each device commits on its own, so a run cut short (instance sleeps,
  restart, closed laptop) keeps everything it already synced; re-run with
  `missing_only` to pick up the rest.
- Writes to both `competitor_prices` (overwrite latest) and `price_history`
  (append), then recomputes and updates `base_prices.base_price` using
  `calculate_reference_price`.
- For MVP, this script can start as a manual-entry admin form
  (`admin/pricing/page.tsx`) that a staff member fills in weekly — automate
  the actual fetching once the manual process is proven out and you've
  reviewed each competitor's Terms of Service for automated access.
- On failure (site unreachable, parsing error), log and leave the existing
  `base_price` untouched rather than writing a bad value — surface the
  staleness in the admin dashboard via `last_synced_at`.

## 8. API surface

**Public**
```
GET  /api/v1/devices?brand=apple&search=...      catalog list, "up to €X"
GET  /api/v1/devices/{slug}                       detail + question set
POST /api/v1/quotes                                {device_id, answers[]} -> quote
GET  /api/v1/quotes/{id}                           quote detail
POST /api/v1/quotes/{id}/confirm                    {fulfillment_method, store_id?,
                                                      customer_name, customer_email,
                                                      customer_phone, iban,
                                                      account_holder_name}
GET  /api/v1/stores?postal_code=1234AB&limit=5     nearest stores (haversine)
```

**Admin** (JWT-protected, under `/api/v1/admin/`)
```
POST   /admin/auth/login
GET/POST/PUT/DELETE  /admin/devices
GET/PUT              /admin/base-prices/{device_id}
GET                  /admin/competitor-prices          filterable by staleness
POST                 /admin/price-sync                 start a sync run (409 if one is going)
GET                  /admin/price-sync                 progress of the current/last run
GET/POST/PUT/DELETE  /admin/question-sets, /questions, /deduction-rules
GET                  /admin/quotes                     filter by status
PATCH                /admin/quotes/{id}/status         e.g. mark "inspected", adjust price
GET/POST/PUT/DELETE  /admin/stores
GET                  /admin/payouts                    pending queue + CSV export for bank upload
PATCH                /admin/payouts/{id}                mark paid
```

## 9. Environment variables (`.env.example`)

```
# backend
DATABASE_URL=postgresql://...          # Neon connection string
JWT_SECRET=
ENCRYPTION_KEY=                        # for IBAN field encryption
CORS_ORIGINS=http://localhost:3000

# frontend
NEXT_PUBLIC_API_URL=http://localhost:8000
```

## 10. Suggested build order

Work through these roughly in order — each phase should be independently
testable before moving to the next.

1. **Scaffolding** — repo structure above, `.env.example`, README with local dev instructions.
2. **Data layer** — all SQLModel models + Alembic migration to create every table in §5.
3. **Pricing engine** — the two pure functions in §6, with unit tests covering: single-competitor fallback, multiple deduction rules stacking, price floored at 0.
4. **Public API** — devices list/detail, quote creation, quote confirm. No auth needed yet.
5. **Customer frontend** — catalog page, device detail page, questionnaire with live price recalculation, confirmation page with fulfillment choice + IBAN form.
6. **Store locator** — stores API + Leaflet map on the confirmation page.
7. **Admin auth + catalog/pricing/question management screens.**
8. **Competitor price sync** — manual admin form first, then the scripted version + GitHub Actions workflow.
9. **Payout queue** — admin screen listing pending payouts with CSV export; mark-as-paid action.
10. **Deploy** — Neon (db) → Render (backend) → Vercel (frontend) → GitHub Actions secrets for the sync job.

## 11. Open assumptions to confirm before/while building

- The real iPhone and Samsung condition questionnaires are now defined in
  `seed-data/questions.json`, sourced directly from the business. Two gaps
  in what was provided, still open:
  - **Samsung is missing a housing/back-condition question.** iPhone has one
    (question 4); Samsung's list jumps from screen condition to battery.
    Confirm whether this is intentional (Samsung housing wear folds into the
    screen-condition question somehow) or a gap to fill before launch.
  - **S-Pen question scope**: only S-Pen-compatible Samsung models (Ultra
    and Z Fold lines) should show that question. `has_s_pen` is added to the
    `devices` table for this, but which exact models get flagged `true` is
    a catalog decision, not answered yet — seed data currently only flags
    the Galaxy S25 Ultra.
  - Exact deduction amounts in `questions.json` are still illustrative
    placeholders on top of the now-real question structure — see the seed
    file's own note.
- Default `markup_pct` per device is a business decision, not a technical
  one — leave it as admin-configurable, not a constant in code.
- UI language (Dutch vs English vs both) — confirm before building frontend copy.
