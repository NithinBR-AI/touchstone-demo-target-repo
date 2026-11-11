# touchstone-demo-target

This repo is the **live target** that [Touchstone](https://github.com/NithinBR-AI/touchstone) scans.

It represents a fictional **customer-service microservice** with intentional drift between:
- its declared schema (`models.py`) and the live Neon Postgres database — hunted by **Schema Drift**
- its OpenAPI spec (`openapi.yaml`) and what the live API actually returns — hunted by **Contract Observer**

## Deployment

Live API: **https://touchstone-demo-target-repo.onrender.com**  
(Render free tier — first request after 15 min idle may take ~30s to cold-start)

## Files

| File | Purpose |
|------|---------|
| `models.py` | SQLAlchemy model declarations — what the DB schema *should* look like |
| `openapi.yaml` | OpenAPI spec — what the API *should* return |
| `main.py` | FastAPI live app — the actual running service |
| `requirements.txt` | Python dependencies |
| `render.yaml` | Render deployment config |

## Schema drift cases (Schema Drift app)

Mismatches between `models.py` and the seeded Neon DB:

| Ghost | Kind | Policy | Description |
|-------|------|--------|-------------|
| `users.email` | `TYPE_CHANGED` | AUTO-FIX | Declared `VARCHAR(255)`, live DB has `VARCHAR(50)` |
| `users.age` | `TYPE_CHANGED` | REVIEW REQUIRED | Declared `INTEGER`, live DB has `BIGINT` (narrowing) |
| `ix_orders_user_id` | `INDEX_MISSING` | AUTO-FIX | Declared in models, missing from live DB |

## Contract drift cases (Contract Observer app)

Mismatches between `openapi.yaml` and what `main.py` actually returns:

| Ghost | Kind | Description |
|-------|------|-------------|
| `account_status` on `/users` | `FIELD_EXTRA` | API returns it, not in spec — fix: PR adds it to `openapi.yaml` |
| `sku` on `/products` | `FIELD_EXTRA` | API returns it, not in spec — fix: PR adds it to `openapi.yaml` |
| `loyalty_tier` on `/users` | `FIELD_MISSING` | Spec declares it, API doesn't return it — fix: PR adds it to `main.py` |

## How Touchstone uses this repo

Target repo is configured in `repos.json` in the Touchstone root. No env vars needed — Touchstone fetches `models.py` and `openapi.yaml` via GitHub raw URLs automatically.

To reset drift after fixes are applied, use the **Reset Demo** button in the Touchstone UI
(calls `POST /demo/reset` on the schema-drift app, re-seeds the Neon DB).
