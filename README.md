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

## Cache drift cases (The Poltergeist app)

Mismatches between `cache_config.yaml` and the live Redis state:

| Ghost | Kind | Description |
|-------|------|-------------|
| `products:list` | `KEY_MISSING` | Declared in config, absent from Redis — fix: warms the key via `/cache/warm` |
| `debug:session_dump` | `KEY_EXTRA` | Present in Redis, not declared in config — fix: deletes the key via `/cache/delete` |

## Cache endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/cache/status` | GET | Returns all keys currently in Redis |
| `/cache/warm` | POST | Restores demo drift state (or warms a specific declared key via `?key=`) |
| `/cache/delete` | DELETE | Deletes a specific key from Redis (`?key=`) — called by Touchstone for `KEY_EXTRA` fixes |

## How Touchstone uses this repo

Target repo is configured in `repos.json` in the Touchstone root. No env vars needed — Touchstone fetches `models.py`, `openapi.yaml`, and `cache_config.yaml` via GitHub raw URLs automatically.

To reset drift after fixes are applied, use the **Reset Demo** button in the Touchstone UI.
