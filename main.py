"""
main.py — Customer Service API (Touchstone demo target).

This is the LIVE API that Contract Observer probes. It intentionally returns
fields that are NOT documented in openapi.yaml — that is the contract drift
Touchstone detects.

Drift cases (vs openapi.yaml):
  · GET /users       → returns `account_status` field — undocumented in spec
  · GET /users/{id}  → returns `account_status` field — undocumented in spec
  · GET /products    → returns `sku` field — undocumented in spec
"""

from __future__ import annotations

import os

import psycopg
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

load_dotenv()

DB_URL = os.environ.get("DATABASE_URL", "")

app = FastAPI(
    title="Customer Service API",
    description="Demo target for Touchstone contract-observer.",
    version="1.0.0",
)


def _conn():
    return psycopg.connect(DB_URL)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/users")
def list_users():
    with _conn() as conn:
        rows = conn.execute(
            "SELECT id, email, age, created_at FROM users ORDER BY id"
        ).fetchall()
    return [
        {
            "id": r[0],
            "email": r[1],
            "age": r[2],
            "created_at": r[3].isoformat() if r[3] else None,
            "account_status": "active",   # undocumented in openapi.yaml — CONTRACT DRIFT
        }
        for r in rows
    ]


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


@app.get("/orders")
def list_orders():
    with _conn() as conn:
        rows = conn.execute(
            "SELECT id, user_id, total, status FROM orders ORDER BY id"
        ).fetchall()
    return [
        {"id": r[0], "user_id": r[1], "total": float(r[2]) if r[2] else None, "status": r[3]}
        for r in rows
    ]


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
            "sku": f"SKU-{r[0]:04d}",   # undocumented in openapi.yaml — CONTRACT DRIFT
        }
        for r in rows
    ]
