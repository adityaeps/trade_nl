# CLAUDE.md

This is the Phone Trade-In Platform (Netherlands). **Read
[ARCHITECTURE.md](./ARCHITECTURE.md) in full before writing any code** — it
is the source of truth for scope, business rules, data model, and API
surface. [TASKS.md](./TASKS.md) tracks sprint progress; update it at the end
of each working session.

## Working conventions

- Where ARCHITECTURE.md doesn't specify something, pick the simplest option
  consistent with existing patterns and leave a `# TODO(assumption): ...`
  comment rather than deciding silently.
- Items marked `[owner: business]` in TASKS.md are not yours to resolve —
  surface them, don't guess.
- `services/pricing_engine.py` must stay pure (no DB/HTTP calls) — see
  ARCHITECTURE.md §6.
- Competitor prices are never fetched live during a customer request (§7) —
  customer-facing reads only ever hit our own DB.
- No payment gateway, no customer accounts, no Redis, no automated courier
  labels, no multi-currency, no i18n scaffolding — all explicitly out of
  scope for MVP (§3). Don't build them speculatively.
- Quotes are frozen at creation time — never recompute a stored quote's price
  from live `base_prices` (§2).
