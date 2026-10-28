"""Real localhost HTTP acceptance with durable storage, approvals and verified provider effects."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

import httpx


def main():
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    from run_all import fingerprint

    env = {key: value for key, value in os.environ.items() if not key.endswith("API_KEY")}
    env.update(
        AI_PROVIDER="fake", EMBEDDING_PROVIDER="fake", LANGSMITH_TRACING="false", LANGCHAIN_TRACING_V2="false"
    )
    receipts = []
    with tempfile.TemporaryDirectory() as path:
        env["DEMO_DATA_DIR"] = path
        command = [
            sys.executable,
            "-m",
            "uvicorn",
            "patterns.api:app_factory",
            "--factory",
            "--host",
            "127.0.0.1",
            "--port",
            "8765",
            "--log-level",
            "error",
        ]
        process = subprocess.Popen(command, cwd=root, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            for _ in range(100):
                try:
                    if httpx.get("http://127.0.0.1:8765/health", timeout=1).status_code == 200:
                        break
                except httpx.ConnectError:
                    time.sleep(0.05)
            else:
                raise RuntimeError("Local server did not start")
            with httpx.Client(base_url="http://127.0.0.1:8765", timeout=30) as client:

                def request(method, url, status=200, **kwargs):
                    response = client.request(method, url, **kwargs)
                    assert response.status_code == status, (url, response.text)
                    value = response.json()
                    receipts.append(
                        {
                            "method": method,
                            "path": url,
                            "expected_status": status,
                            "actual_status": response.status_code,
                            "response": value,
                        }
                    )
                    return value

                request(
                    "POST",
                    "/cases",
                    status=401,
                    json={"invoice_id": "INV-1042", "request": "Investigate", "request_id": "unauthorized"},
                )
                headers = {"X-Workspace": "north", "X-Actor": "http-reviewer"}
                case = request(
                    "POST",
                    "/cases",
                    headers=headers,
                    json={
                        "invoice_id": "INV-1042",
                        "request": "Investigate duplicate payment",
                        "request_id": "http-smoke",
                    },
                )
                request("POST", "/worker/tick")
                pending = request("GET", "/cases/" + case["case_id"], headers=headers)
                assert (
                    pending["status"] == "awaiting_approval"
                    and pending["proposal"]["arguments"]["amount_cents"] == 12000
                )
                request("GET", "/cases/" + case["case_id"], headers={"X-Workspace": "south"}, status=404)
                request(
                    "POST",
                    "/cases/" + case["case_id"] + "/decision",
                    headers=headers,
                    json={
                        "action": "edit",
                        "amount_cents": 10000,
                        "expected_version": pending["approval"]["version"],
                    },
                )
                request("POST", "/worker/tick")
                final = request("GET", "/cases/" + case["case_id"], headers=headers)
                assert (
                    final["status"] == "completed"
                    and final["report"]["amount_cents"] == 10000
                    and final["report"]["verified"]
                )
                events = request("GET", "/cases/" + case["case_id"] + "/events", headers=headers)
                assert {"model.called", "tool.executed", "approval.decided", "effect.verified"} <= {
                    event["kind"] for event in events
                }
                idle = request("POST", "/worker/tick")
                assert idle["status"] == "idle"
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
    report = {
        "environment": "actual localhost HTTP, SQLite application and separate accounting store, MCP subprocess, fixture model",
        "source_sha256": fingerprint(),
        "command": "python scripts/smoke_http.py",
        "cases": receipts,
        "pass": True,
    }
    (root / "evidence").mkdir(exist_ok=True)
    (root / "evidence/http.json").write_text(json.dumps(report, indent=2) + "\n")
    print(
        "PASS: actual HTTP submit, investigate, cross-scope refusal, reviewed edit, execution, verification and idle replay"
    )


if __name__ == "__main__":
    main()
