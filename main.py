"""
main.py — Customer Service API (Touchstone demo target).

This is the LIVE API that Contract Observer probes. It intentionally returns
fields that are NOT documented in openapi.yaml — that is the contract drift
Touchstone detects.

Cache drift (vs cache_config.yaml) for Poltergeist app:
  · products:list never cached → KEY_MISSING ghost
  · debug:session_dump exists in Redis (set manually) → UNDECLARED_KEY ghost

Contract drift (vs openapi.yaml):
  · GET /users    → returns `account_status` — undocumented in spec
  · GET /products → returns `sku` — undocumented in spec
"""

from __future__ import annotations

import json
import os
import urllib.request

import psycopg
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException

load_dotenv()

DB_URL                   = os.environ.get("DATABASE_URL", "")
UPSTASH_REDIS_REST_URL   = os.environ.get("UPSTASH_REDIS_REST_URL", "")
UPSTASH_REDIS_REST_TOKEN = os.environ.get("UPSTASH_REDIS_REST_TOKEN", "")

app = FastAPI(
    title="Customer Service API",
    description="Demo target for Touchstone contract-observer and poltergeist.",
    version="1.0.0",
)


def _conn():
    return psycopg.connect(DB_URL)


def _redis_get(path: str) -> dict:
    """Call Upstash REST API."""
    if not UPSTASH_REDIS_REST_URL or not UPSTASH_REDIS_REST_TOKEN:
        raise HTTPException(503, detail="Upstash REST not configured")
    req = urllib.request.Request(
        f"{UPSTASH_REDIS_REST_URL}/{path}",
        headers={"Authorization": f"Bearer {UPSTASH_REDIS_REST_TOKEN}"},
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())


def _redis_set(key: str, value: str) -> None:
    """SET a key via Upstash REST API."""
    if not UPSTASH_REDIS_REST_URL or not UPSTASH_REDIS_REST_TOKEN:
        return
    req = urllib.request.Request(
        f"{UPSTASH_REDIS_REST_URL}/set/{key}/{urllib.parse.quote(value)}",
        headers={"Authorization": f"Bearer {UPSTASH_REDIS_REST_TOKEN}"},
    )
    with urllib.request.urlopen(req, timeout=10):
        pass


def _redis_del(key: str) -> None:
    """DEL a key via Upstash REST API."""
    if not UPSTASH_REDIS_REST_URL or not UPSTASH_REDIS_REST_TOKEN:
        return
    req = urllib.request.Request(
        f"{UPSTASH_REDIS_REST_URL}/del/{key}",
        headers={"Authorization": f"Bearer {UPSTASH_REDIS_REST_TOKEN}"},
    )
    with urllib.request.urlopen(req, timeout=10):
        pass


import urllib.parse


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    redis_ok = False
    if UPSTASH_REDIS_REST_URL:
        try:
            result = _redis_get("ping")
            redis_ok = result.get("result") == "PONG"
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
            "account_status": "active",   # undocumented — CONTRACT DRIFT
        }
        for r in rows
    ]
    if UPSTASH_REDIS_REST_URL:
        try:
            _redis_set("users:list", json.dumps(result, default=str))
        except Exception:
            pass
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
        "account_status": "active",   # undocumented — CONTRACT DRIFT
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
    if UPSTASH_REDIS_REST_URL:
        try:
            _redis_set("orders:list", json.dumps(result, default=str))
        except Exception:
            pass
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
# Products — intentionally NOT cached (KEY_MISSING drift)
# ---------------------------------------------------------------------------

@app.get("/products")
def list_products():
    with _conn() as conn:
        rows = conn.execute(
            "SELECT id, name, price, stock FROM products ORDER BY id"
        ).fetchall()
    return [
        {
            "id": r[0],
            "name": r[1],
            "price": float(r[2]) if r[2] else None,
            "stock": r[3],
            "sku": f"SKU-{r[0]:04d}",   # undocumented — CONTRACT DRIFT
        }
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Cache status — returns all keys currently in Redis
# ---------------------------------------------------------------------------

@app.get("/cache/status")
def cache_status():
    """Returns all keys currently in Redis for Poltergeist drift detection."""
    result = _redis_get("keys/*")
    return {"keys": sorted(result.get("result", []))}


# ---------------------------------------------------------------------------
# Cache warm — restores drift state after a judge applies a fix
# ---------------------------------------------------------------------------

@app.post("/cache/warm")
def cache_warm():
    """Restore drift state for demo replay after a judge applies fixes.

    After warm, Redis state is:
      users:list         ✓ present (declared, healthy)
      orders:list        ✓ present (declared, healthy)
      products:list      ✗ absent  → KEY_MISSING ghost
      debug:session_dump ✓ present (undeclared) → UNDECLARED_KEY ghost
    """
    with _conn() as conn:
        users = conn.execute(
            "SELECT id, email, age, created_at FROM users ORDER BY id"
        ).fetchall()
        orders = conn.execute(
            "SELECT id, user_id, total, status FROM orders ORDER BY id"
        ).fetchall()

    users_data = [
        {"id": r[0], "email": r[1], "age": r[2],
         "created_at": r[3].isoformat() if r[3] else None, "account_status": "active"}
        for r in users
    ]
    orders_data = [
        {"id": r[0], "user_id": r[1], "total": float(r[2]) if r[2] else None, "status": r[3]}
        for r in orders
    ]

    _redis_set("users:list", json.dumps(users_data, default=str))
    _redis_set("orders:list", json.dumps(orders_data, default=str))
    _redis_del("products:list")
    _redis_set("debug:session_dump", '{"users": "all"}')

    return {"status": "warmed", "message": "Cache drift restored. Click Hunt Ghosts to scan again."}