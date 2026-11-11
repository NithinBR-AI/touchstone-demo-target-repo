"""
models.py — Declared (intended) schema for the customer-service microservice.

This is the SOURCE OF TRUTH that Touchstone reads to know what the schema
*should* look like. The live Neon DB has intentional drift from these
declarations — that is what Touchstone detects.

Drift cases present (vs seeded Neon DB):
  · users.email  VARCHAR(50) in DB  vs VARCHAR(255) declared here  → TYPE_CHANGED (widening, auto-fix)
  · users.age    BIGINT in DB       vs INTEGER declared here        → TYPE_CHANGED (narrowing, review-only)
  · ix_orders_user_id  MISSING in DB, declared here                 → INDEX_MISSING (auto-fix)
"""

from sqlalchemy import Column, ForeignKey, Index, Integer, Numeric, String, TIMESTAMP
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    email = Column(String(255), nullable=False, unique=True)   # intended wider than DB's 50
    age = Column(Integer, nullable=True)                        # intended INTEGER; DB has BIGINT
    created_at = Column(TIMESTAMP, server_default=func.now())


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    total = Column(Numeric(10, 2), nullable=True)
    status = Column(String(20), nullable=True)


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    price = Column(Numeric(10, 2), nullable=True)
    stock = Column(Integer, nullable=True)


# Declared index — intentionally missing from live DB (the ghost Touchstone will find)
ix_orders_user_id = Index("ix_orders_user_id", Order.user_id)
