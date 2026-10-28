"""A real local HTTP application backed by its own accounting database.

This mock service enforces provider-side idempotency and current balance bounds.
Those guarantees are intentionally outside the agent's checkpoint transaction.
"""

from __future__ import annotations

import json
from pathlib import Path
import sqlite3
from uuid import uuid4

from fastapi import FastAPI, Header, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel, ConfigDict, Field

from patterns.database import digest, encoded


ERP_SCHEMA = """
CREATE TABLE IF NOT EXISTS invoices(tenant TEXT,id TEXT,amount_cents INTEGER,currency TEXT,revision INTEGER,PRIMARY KEY(tenant,id));
CREATE TABLE IF NOT EXISTS payments(tenant TEXT,id TEXT,invoice_id TEXT,amount_cents INTEGER,PRIMARY KEY(tenant,id));
CREATE TABLE IF NOT EXISTS credits(tenant TEXT,id TEXT,invoice_id TEXT,amount_cents INTEGER,reason TEXT,operation_id TEXT,PRIMARY KEY(tenant,id),UNIQUE(tenant,operation_id));
CREATE TABLE IF NOT EXISTS operations(tenant TEXT,id TEXT,payload_hash TEXT,response TEXT,PRIMARY KEY(tenant,id));
"""


def seed_erp(path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as db:
        db.executescript(ERP_SCHEMA)
        db.executemany(
            "INSERT OR IGNORE INTO invoices VALUES (?,?,?,?,?)",
            [
                ("north", "INV-1042", 12000, "USD", 0),
                ("north", "INV-1043", 8000, "USD", 0),
                ("south", "INV-2042", 5000, "USD", 0),
            ],
        )
        db.executemany(
            "INSERT OR IGNORE INTO payments VALUES (?,?,?,?)",
            [
                ("north", "PAY-1", "INV-1042", 12000),
                ("north", "PAY-2", "INV-1042", 12000),
                ("north", "PAY-3", "INV-1043", 8000),
                ("south", "PAY-4", "INV-2042", 5000),
            ],
        )


class CreditBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    invoice_id: str = Field(pattern=r"^INV-[0-9]+$")
    amount_cents: int = Field(gt=0, strict=True)
    reason: str = Field(min_length=3, max_length=200)


def create_erp_app(path):
    app = FastAPI(title="Local accounting sandbox", version="1.0.0")

    def connection():
        db = sqlite3.connect(path, timeout=20, isolation_level=None)
        db.row_factory = sqlite3.Row
        return db

    def require_invoice(db, tenant, identity):
        row = db.execute("SELECT * FROM invoices WHERE tenant=? AND id=?", (tenant, identity)).fetchone()
        if row is None:
            raise HTTPException(404, "Invoice not found in this workspace")
        return dict(row)

    @app.get(
        "/invoices/{invoice_id}", operation_id="get_invoice", summary="Read an invoice in the bound workspace"
    )
    def invoice(invoice_id: str, x_workspace: str = Header()):
        db = connection()
        try:
            return require_invoice(db, x_workspace, invoice_id)
        finally:
            db.close()

    @app.get(
        "/invoices/{invoice_id}/payments",
        operation_id="list_payments",
        summary="Read payments for an invoice",
    )
    def payments(invoice_id: str, x_workspace: str = Header()):
        db = connection()
        try:
            require_invoice(db, x_workspace, invoice_id)
            return [
                dict(row)
                for row in db.execute(
                    "SELECT id,amount_cents FROM payments WHERE tenant=? AND invoice_id=? ORDER BY id",
                    (x_workspace, invoice_id),
                )
            ]
        finally:
            db.close()

    @app.get(
        "/invoices/{invoice_id}/credits",
        operation_id="list_credits",
        summary="Read credit receipts for an invoice",
    )
    def credits(invoice_id: str, x_workspace: str = Header()):
        db = connection()
        try:
            require_invoice(db, x_workspace, invoice_id)
            return [
                dict(row)
                for row in db.execute(
                    "SELECT id,invoice_id,amount_cents,reason,operation_id FROM credits WHERE tenant=? AND invoice_id=? ORDER BY id",
                    (x_workspace, invoice_id),
                )
            ]
        finally:
            db.close()

    @app.post(
        "/credits",
        operation_id="create_credit",
        summary="Create a bounded credit with provider idempotency",
        openapi_extra={"x-effect": "write"},
    )
    def credit(body: CreditBody, x_workspace: str = Header(), idempotency_key: str = Header()):
        db = connection()
        try:
            db.execute("BEGIN IMMEDIATE")
            payload_hash = digest(body.model_dump())
            previous = db.execute(
                "SELECT * FROM operations WHERE tenant=? AND id=?", (x_workspace, idempotency_key)
            ).fetchone()
            if previous:
                if previous["payload_hash"] != payload_hash:
                    raise HTTPException(409, "Idempotency identity reused with changed payload")
                db.rollback()
                return json.loads(previous["response"])
            invoice = require_invoice(db, x_workspace, body.invoice_id)
            paid = db.execute(
                "SELECT COALESCE(SUM(amount_cents),0) FROM payments WHERE tenant=? AND invoice_id=?",
                (x_workspace, body.invoice_id),
            ).fetchone()[0]
            credited = db.execute(
                "SELECT COALESCE(SUM(amount_cents),0) FROM credits WHERE tenant=? AND invoice_id=?",
                (x_workspace, body.invoice_id),
            ).fetchone()[0]
            if body.amount_cents > paid - invoice["amount_cents"] - credited:
                raise HTTPException(409, "Credit exceeds current overpayment")
            result = {
                "id": "CR-" + uuid4().hex[:16],
                "invoice_id": body.invoice_id,
                "amount_cents": body.amount_cents,
                "reason": body.reason,
                "operation_id": idempotency_key,
            }
            db.execute(
                "INSERT INTO credits VALUES (?,?,?,?,?,?)",
                (x_workspace, result["id"], body.invoice_id, body.amount_cents, body.reason, idempotency_key),
            )
            db.execute(
                "INSERT INTO operations VALUES (?,?,?,?)",
                (x_workspace, idempotency_key, payload_hash, encoded(result)),
            )
            db.execute(
                "UPDATE invoices SET revision=revision+1 WHERE tenant=? AND id=?",
                (x_workspace, body.invoice_id),
            )
            db.commit()
            return result
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    return app


class ERPClient:
    def __init__(self, path):
        self.path = str(path)

    def request(self, tenant, method, path, **kwargs):
        with TestClient(create_erp_app(self.path)) as client:
            headers = {"X-Workspace": tenant, **kwargs.pop("headers", {})}
            response = client.request(method, path, headers=headers, **kwargs)
            if response.status_code == 404:
                raise KeyError("Invoice not found")
            if response.status_code >= 400:
                raise ValueError(response.json()["detail"])
            return response.json()

    def invoice(self, tenant, identity):
        return self.request(tenant, "GET", f"/invoices/{identity}")

    def payments(self, tenant, identity):
        return self.request(tenant, "GET", f"/invoices/{identity}/payments")

    def credits(self, tenant, identity):
        return self.request(tenant, "GET", f"/invoices/{identity}/credits")

    def credit(self, tenant, args, operation):
        return self.request(tenant, "POST", "/credits", json=args, headers={"Idempotency-Key": operation})

    def facts(self, tenant, identity):
        invoice = self.invoice(tenant, identity)
        paid = sum(row["amount_cents"] for row in self.payments(tenant, identity))
        credited = sum(row["amount_cents"] for row in self.credits(tenant, identity))
        return {
            "invoice_id": identity,
            "invoice_cents": invoice["amount_cents"],
            "paid_cents": paid,
            "credited_cents": credited,
            "overpayment_cents": max(0, paid - invoice["amount_cents"] - credited),
            "revision": invoice["revision"],
            "currency": invoice["currency"],
        }
