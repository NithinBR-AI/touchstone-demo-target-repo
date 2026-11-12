"""
main.py — Customer Service API (Touchstone demo target).

This is the LIVE API that Contract Observer probes. It intentionally returns
fields that are NOT documented in openapi.yaml — that is the contract drift
Touchstone detects.

It also uses Redis caching with intentional drift vs cache_config.yaml:
  · eviction_policy declared as allkeys-lru but Upstash default is noeviction
  · orders:list cached with TTL=999 instead of declared 180  (TTL_MISMATCH)
  · products:list never cached                               (KEY_MISSING)
  · users:list cached correctly with TTL=300                 (no drift)

Drift cases (vs openapi.yaml):
  · GET /users       → returns `account_status` field — undocumented in spec
  · GET /users/{id}  → returns `account_status` field — undocumented in spec
  · GET /products    → returns `sku` field — undocumented in spec
"""

from __future__ import annotations

import json
import os

import psycopg
import redis as redis_lib
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

load_dotenv()

DB_URL    = os.environ.get("DATABASE_URL", "")
REDIS_URL = os.environ.get("REDIS_URL", "")

app = FastAPI(
    title="Customer Service API",
    description="Demo target for Touchstone contract-observer and poltergeist.",
    version="1.0.0",
)

# Redis client — None if not configured
_redis: redis_lib.Redis | None = None
if REDIS_URL:
    _redis = redis_lib.from_url(REDIS_URL, decode_responses=True)


def _conn():
    return psycopg.connect(DB_URL)


def _r() -> redis_lib.Redis:
    if _redis is None:
        raise HTTPException(503, detail="REDIS_URL not configured")
    return _redis


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    redis_ok = False
    if _redis:
        try:
            redis_ok = _redis.ping()
        except Exception:
            pass
    return {"status": "ok", "redis": redis_ok}


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

@app.get("/users")
def list_users():
    with _conn() as conn:
        rows = conn.execute(
            "SELECT id, email, age, created_at FROM users ORDER BY id"
        ).fetchall()
    result = [
        {
            "id": r[0],
            "email": r[1],
            "age": r[2],
            "created_at": r[3].isoformat() if r[3] else None,
            "account_status": "active",   # undocumented in openapi.yaml — CONTRACT DRIFT
        }
        for r in rows
    ]
    # Cache correctly — TTL matches declared 300s (no drift here)
    if _redis:
        _redis.setex("users:list", 300, json.dumps(result, default=str))
    return result


@app.get("/users/{id}")
def get_user(id: int):
    with _conn() as conn:
        row = conn.execute(
            "SELECT id, email, age, created_at FROM users WHERE id = %s", (id,)
        ).fetchone()
    if row is None:
        raise HTTPException(404, detail="User not found")
    return {
        "id": row[0],
        "email": row[1],
        "age": row[2],
        "created_at": row[3].isoformat() if row[3] else None,
        "account_status": "active",   # undocumented in openapi.yaml — CONTRACT DRIFT
    }


# ---------------------------------------------------------------------------
# Orders
# ---------------------------------------------------------------------------

@app.get("/orders")
def list_orders():
    with _conn() as conn:
        rows = conn.execute(
            "SELECT id, user_id, total, status FROM orders ORDER BY id"
        ).fetchall()
    result = [
        {"id": r[0], "user_id": r[1], "total": float(r[2]) if r[2] else None, "status": r[3]}
        for r in rows
    ]
    # INTENTIONAL DRIFT: declared TTL=180, actually caching with TTL=999
    if _redis:
        _redis.setex("orders:list", 999, json.dumps(result, default=str))
    return result


@app.get("/orders/{id}")
def get_order(id: int):
    with _conn() as conn:
        row = conn.execute(
            "SELECT id, user_id, total, status FROM orders WHERE id = %s", (id,)
        ).fetchone()
    if row is None:
        raise HTTPException(404, detail="Order not found")
    return {
        "id": row[0],
        "user_id": row[1],
        "total": float(row[2]) if row[2] else None,
        "status": row[3],
    }


# ---------------------------------------------------------------------------
# Products
# ---------------------------------------------------------------------------

@app.get("/products")
def list_products():
    with _conn() as conn:
        rows = conn.execute(
            "SELECT id, name, price, stock FROM products ORDER BY id"
        ).fetchall()
    result = [
        {
            "id": r[0],
            "name": r[1],
            "price": float(r[2]) if r[2] else None,
            "stock": r[3],
            "sku": f"SKU-{r[0]:04d}",   # undocumented in openapi.yaml — CONTRACT DRIFT
        }
        for r in rows
    ]
    # INTENTIONAL DRIFT: declared TTL=600, never cached (KEY_MISSING drift)
    # products:list is intentionally NOT written to Redis
    return result


# ---------------------------------------------------------------------------
# Cache warm — sets keys with intentional drift for Poltergeist demo
# ---------------------------------------------------------------------------

@app.post("/cache/warm")
def cache_warm():
    """
    Re-populate Redis with intentional drift so Poltergeist always has ghosts.
    Call this before running a demo scan.

    Drift state after warm:
      · users:list   TTL=300  (matches declared — no drift)
      · orders:list  TTL=999  (declared=180 — TTL_MISMATCH ghost)
      · products:list missing (declared=600 — KEY_MISSING ghost)
    """
    r = _r()
    r.setex("users:list",  300, '["warmed"]')
    r.setex("orders:list", 999, '["warmed"]')   # intentional TTL mismatch
    # products:list intentionally NOT set                                    # KEY_MISSING
    return {
        "status": "warmed",
        "keys": {
            "users:list":    {"ttl": 300,  "drift": False},
            "orders:list":   {"ttl": 999,  "drift": "TTL_MISMATCH (declared 180)"},
            "products:list": {"ttl": None, "drift": "KEY_MISSING (declared 600)"},
        },
    }


# ---------------------------------------------------------------------------
# Cache status — read-only view of current Redis state
# ---------------------------------------------------------------------------

@app.get("/cache/status")
def cache_status():
    """Current Redis state — used by Poltergeist actual adapter."""
    r = _r()
    keys = ["users:list", "orders:list", "products:list"]
    status = {}
    for key in keys:
        ttl = r.ttl(key)   # -2 = missing, -1 = no expiry, >=0 = seconds remaining
        status[key] = {"ttl": ttl, "exists": ttl != -2}
    try:
        eviction_policy = r.config_get("maxmemory-policy").get("maxmemory-policy", "unknown")
        maxmemory       = r.config_get("maxmemory").get("maxmemory", "unknown")
    except Exception:
        eviction_policy = "unknown"
        maxmemory       = "unknown"
    return {
        "keys": status,
        "eviction_policy": eviction_policy,
        "maxmemory": maxmemory,
    }