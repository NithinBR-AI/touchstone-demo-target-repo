# touchstone-demo-target

This repo is the **target** that [Touchstone](https://github.com/NithinBR-AI/touchstone) scans.

It represents a fictional **customer-service microservice** with intentional drift between its
declared schema (`models.py`) and the live Neon Postgres database — the ghosts Touchstone hunts.

## Files

| File | Purpose |
|------|---------|
| `models.py` | SQLAlchemy model declarations — what the schema *should* look like |
| `openapi.yaml` | OpenAPI spec — what the API *should* look like (for contract-observer) |
| `requirements.txt` | Python dependencies for the SQLAlchemy models |

## Drift cases present

These mismatches exist between `models.py` and the seeded Neon DB:

| Ghost | Kind | Policy | Description |
|-------|------|--------|-------------|
| `users.email` | `TYPE_CHANGED` | AUTO-FIX | Declared `VARCHAR(255)`, live DB has `VARCHAR(50)` |
| `users.age` | `TYPE_CHANGED` | REVIEW REQUIRED | Declared `INTEGER`, live DB has `BIGINT` (narrowing) |
| `ix_orders_user_id` | `INDEX_MISSING` | AUTO-FIX | Declared in models, missing from live DB |

## How Touchstone uses this repo

Touchstone's schema-drift app reads `models.py` via the `MODELS_PATH` environment variable:

```bash
MODELS_PATH=/path/to/touchstone-demo-target/models.py
```

The live DB state is set up by running the seed script in the Touchstone repo:

```bash
python demo/seed.py $DATABASE_URL
```

To reset drift after a judge applies fixes, use the **Reset Demo** button in the Touchstone UI
(calls `POST /demo/reset` on the schema-drift app).
