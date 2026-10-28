"""Inspect and operate the same durable application used by FastAPI and acceptance checks."""

from __future__ import annotations

import argparse
from pathlib import Path
import tempfile
import time

from patterns.providers import emit
from .service import Service


def walkthrough(path):
    service = Service(path)
    service.seed()
    case = service.submit(
        "north", "INV-1042", "Investigate the suspected duplicate payment", request_id="walkthrough"
    )
    service.work("investigator")
    pending = service.case("north", case["case_id"])
    if pending["status"] == "awaiting_approval" and pending["approval"]["status"] == "pending":
        service.resolve(
            "north",
            case["case_id"],
            action="edit",
            actor="demo-reviewer",
            expected_version=pending["approval"]["version"],
            amount_cents=10000,
        )
        service.work("executor", fault="after_effect")
        effects_before_retry = service.erp.credits("north", "INV-1042")
        Service(path).work("recovery-worker", now=service.clock() + 10)
    else:
        effects_before_retry = service.erp.credits("north", "INV-1042")
    final = service.case("north", case["case_id"])
    if final["status"] != "completed" or not final["report"]["verified"]:
        raise RuntimeError("Walkthrough did not complete")
    return {
        "scenario": "Invoice investigation, reviewed edit and response-loss recovery",
        "invoice_id": "INV-1042",
        "proposed_amount_cents": pending["proposal"]["arguments"]["amount_cents"],
        "approved_amount_cents": 10000,
        "effects_after_response_loss": len(effects_before_retry),
        "effects_after_recovery": len(service.erp.credits("north", "INV-1042")),
        "final": final,
        "work_document": service.docs.get("north", case["case_id"]),
        "events": service.events("north", case["case_id"]),
    }


def main():
    parser = argparse.ArgumentParser(description="Local invoice investigation workbench")
    parser.add_argument("--data", default=".local-data", help="Durable local data directory")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("seed", help="Create synthetic invoices and policy documents")
    submit = sub.add_parser("submit", help="Submit a scoped invoice investigation")
    submit.add_argument("--workspace", default="north")
    submit.add_argument("--invoice", required=True)
    submit.add_argument("--request", required=True)
    submit.add_argument("--request-id", required=True)
    worker = sub.add_parser("worker", help="Poll durable state and run due jobs")
    worker.add_argument("--owner", default="cli-worker")
    worker.add_argument("--ticks", type=int, default=1)
    worker.add_argument("--interval", type=float, default=1)
    worker.add_argument("--fault", choices=["after_effect"])
    show = sub.add_parser("show", help="Read a scoped case or its event trail")
    show.add_argument("case_id")
    show.add_argument("--workspace", default="north")
    show.add_argument("--events", action="store_true")
    decide = sub.add_parser("decide", help="Approve, edit or reject a pending action")
    decide.add_argument("case_id")
    decide.add_argument("--workspace", default="north")
    decide.add_argument("--actor", required=True)
    decide.add_argument("--action", choices=["approve", "edit", "reject"], required=True)
    decide.add_argument("--version", type=int, required=True)
    decide.add_argument("--amount-cents", type=int)
    sub.add_parser("walkthrough", help="Execute a fresh offline scenario including crash recovery")
    args = parser.parse_args()
    if args.command == "walkthrough":
        with tempfile.TemporaryDirectory() as path:
            emit(walkthrough(path))
        return
    service = Service(Path(args.data))
    if args.command == "seed":
        service.seed()
        emit({"status": "seeded"})
    elif args.command == "submit":
        emit(service.submit(args.workspace, args.invoice, args.request, args.request_id))
    elif args.command == "show":
        emit(
            service.events(args.workspace, args.case_id)
            if args.events
            else service.case(args.workspace, args.case_id)
        )
    elif args.command == "decide":
        emit(
            service.resolve(
                args.workspace, args.case_id, args.action, args.actor, args.version, args.amount_cents
            )
        )
    elif args.command == "worker":
        if args.ticks < 1 or args.interval <= 0:
            parser.error("Positive ticks and interval required")
        for tick in range(args.ticks):
            emit(service.work(args.owner, fault=args.fault) or {"status": "idle"})
            if tick + 1 < args.ticks:
                time.sleep(args.interval)


if __name__ == "__main__":
    main()
