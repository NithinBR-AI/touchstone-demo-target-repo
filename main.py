"""
Customer Service API — Touchstone demo target.

Intentional drift baked in for demo purposes:

  Cache drift (detected by Poltergeist):
    · products:list        never cached → KEY_MISSING
    · debug:session_dump   in Redis, not declared → UNDECLARED_KEY

  Contract drift (detected by Contract Observer):
    · GET /users    returns `account_status` — not in openapi.yaml
    · GET /products returns `sku` — not in openapi.yaml
"""

from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from typing import Any

import psycopg
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException

load_dotenv()

DATABASE_URL             = os.environ["DATABASE_URL"]
UPSTASH_REDIS_REST_URL   = os.environ.get("UPSTASH_REDIS_REST_URL", "")
UPSTASH_REDIS_REST_TOKEN = os.environ.get("UPSTASH_REDIS_REST_TOKEN", "")

app = FastAPI(
    title="Customer Service API",
    description="Demo target for Touchstone drift detection.",
    version="1.0.0",
)


# ---------------------------------------------------------------------------
# DB
# ---------------------------------------------------------------------------

def _conn():
    return psycopg.connect(DATABASE_URL)


# ---------------------------------------------------------------------------
# Redis (Upstash REST API)
# ---------------------------------------------------------------------------

def _redis(path: str, method: str = "GET", data: bytes | None = None) -> Any:
    if not UPSTASH_REDIS_REST_URL or not UPSTASH_REDIS_REST_TOKEN:
        raise HTTPException(503, detail="Redis not configured")
    req = urllib.request.Request(
        f"{UPSTASH_REDIS_REST_URL}/{path}",
        headers={"Authorization": f"Bearer {UPSTASH_REDIS_REST_TOKEN}"},
        data=data,
        method=method,
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())


def _redis_set(key: str, value: str) -> None:
    _redis(f"set/{key}/{urllib.parse.quote(value, safe='')}")


def _redis_del(key: str) -> None:
    _redis(f"del/{key}")


def _redis_keys(pattern: str = "*") -> list[str]:
    result = _redis(f"keys/{urllib.parse.quote(pattern, safe='*')}")
    return result.get("result") or []


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    redis_ok = False
    try:
        redis_ok = _redis("ping").get("result") == "PONG"
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
            "id": r[0], "email": r[1], "age": r[2],
            "created_at": r[3].isoformat() if r[3] else None,
            "account_status": "active",  # undocumented — contract drift
        }
        for r in rows
    ]
    try:
        _redis_set("users:list", json.dumps(result, default=str))
    except Exception:
        pass
    return result


@app.get("/users/{user_id}")
def get_user(user_id: int):
    with _conn() as conn:
        row = conn.execute(
            "SELECT id, email, age, created_at FROM users WHERE id = %s", (user_id,)
        ).fetchone()
    if row is None:
        raise HTTPException(404, detail="User not found")
    return {
        "id": row[0], "email": row[1], "age": row[2],
        "created_at": row[3].isoformat() if row[3] else None,
        "account_status": "active",  # undocumented — contract drift
        "loyalty_tier": None,  # TODO: implement
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
    try:
        _redis_set("orders:list", json.dumps(result, default=str))
    except Exception:
        pass
    return result


@app.get("/orders/{order_id}")
def get_order(order_id: int):
    with _conn() as conn:
        row = conn.execute(
            "SELECT id, user_id, total, status FROM orders WHERE id = %s", (order_id,)
        ).fetchone()
    if row is None:
        raise HTTPException(404, detail="Order not found")
    return {
        "id": row[0], "user_id": row[1],
        "total": float(row[2]) if row[2] else None, "status": row[3],
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
            "id": r[0], "name": r[1],
            "price": float(r[2]) if r[2] else None, "stock": r[3],
            "sku": f"SKU-{r[0]:04d}",  # undocumented — contract drift
        }
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

@app.get("/cache/status")
def cache_status():
    """Return all keys currently in Redis."""
    return {"keys": sorted(_redis_keys())}


@app.post("/cache/warm")
def cache_warm(key: str | None = None):
    """Warm a specific declared cache key from the DB.

    POST /cache/warm?key=products:list  — populates that key in Redis.
    POST /cache/warm                    — full reset, restores demo drift state.

    Demo drift state:
      users:list         ✓ cached
      orders:list        ✓ cached
      products:list      ✗ missing  → KEY_MISSING ghost
      debug:session_dump ✓ present, undeclared → UNDECLARED_KEY ghost
    """
    with _conn() as conn:
        users  = conn.execute("SELECT id, email, age, created_at FROM users ORDER BY id").fetchall()
        orders = conn.execute("SELECT id, user_id, total, status FROM orders ORDER BY id").fetchall()
        products = conn.execute("SELECT id, name, price, stock FROM products ORDER BY id").fetchall()

    _users_data = [
        {"id": r[0], "email": r[1], "age": r[2],
         "created_at": r[3].isoformat() if r[3] else None, "account_status": "active"}
        for r in users
    ]
    _orders_data = [
        {"id": r[0], "user_id": r[1], "total": float(r[2]) if r[2] else None, "status": r[3]}
        for r in orders
    ]
    _products_data = [
        {"id": r[0], "name": r[1], "price": float(r[2]) if r[2] else None, "stock": r[3]}
        for r in products
    ]

    if key == "products:list":
        _redis_set("products:list", json.dumps(_products_data, default=str))
        return {"status": "warmed", "key": key}

    if key == "users:list":
        _redis_set("users:list", json.dumps(_users_data, default=str))
        return {"status": "warmed", "key": key}

    if key == "orders:list":
        _redis_set("orders:list", json.dumps(_orders_data, default=str))
        return {"status": "warmed", "key": key}

    # Full reset — restore demo drift state
    _redis_set("users:list",   json.dumps(_users_data,   default=str))
    _redis_set("orders:list",  json.dumps(_orders_data,  default=str))
    _redis_del("products:list")
    _redis_set("debug:session_dump", '{"users": "all"}')

    return {"status": "warmed", "message": "Cache drift restored. Click Hunt Ghosts to scan again."}