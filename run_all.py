"""Run independent demos with fixture providers and save reviewable receipts."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import platform
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FOLDERS = [
    "deterministic-workflow-with-subagents",
    "router-and-orchestrator",
    "agents-as-tools",
    "context-management",
    "rag-pipeline-with-evals",
    "mcp-server-from-rest-api",
    "human-in-the-loop-approval",
    "event-driven-job-runner",
    "evaluator-retry-loop",
]


def fingerprint():
    paths = [
        ROOT / "pyproject.toml",
        ROOT / ".python-version",
        ROOT / "uv.lock",
        ROOT / "run_all.py",
        ROOT / "conftest.py",
    ]
    for directory in ["patterns", "application", "tests", "scripts", ".github", *FOLDERS]:
        paths.extend(
            path for path in (ROOT / directory).rglob("*") if path.suffix in {".py", ".json", ".yml"}
        )
    digest = hashlib.sha256()
    for path in sorted(paths):
        if path.is_file():
            digest.update(path.relative_to(ROOT).as_posix().encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()


def main():
    environment = {
        key: value
        for key, value in os.environ.items()
        if key not in {"AI_API_KEY", "OPENAI_API_KEY", "GOOGLE_API_KEY", "ANTHROPIC_API_KEY"}
    }
    environment.update(
        AI_PROVIDER="fake", EMBEDDING_PROVIDER="fake", LANGSMITH_TRACING="false", LANGCHAIN_TRACING_V2="false"
    )
    started = time.perf_counter()
    rows = []
    for folder in FOLDERS:
        before = time.perf_counter()
        process = subprocess.run(
            [sys.executable, f"{folder}/demo.py"],
            cwd=ROOT,
            env=environment,
            text=True,
            capture_output=True,
            timeout=30,
        )
        row = {
            "pattern": folder,
            "command": f"python {folder}/demo.py",
            "returncode": process.returncode,
            "seconds": round(time.perf_counter() - before, 3),
        }
        if process.returncode == 0:
            row["output"] = json.loads(process.stdout)
        else:
            row["error"] = process.stderr[-3000:]
        rows.append(row)
        print(f"{'PASS' if process.returncode == 0 else 'FAIL'} {folder}")
    report = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "python": platform.python_version(),
        "source_sha256": fingerprint(),
        "providers": "fake",
        "credentials_removed": True,
        "versions": {
            name: importlib.metadata.version(name) for name in ("langgraph", "fastapi", "mcp", "pytest")
        },
        "seconds": round(time.perf_counter() - started, 3),
        "demos": rows,
    }
    (ROOT / "evidence").mkdir(exist_ok=True)
    (ROOT / "evidence/latest.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"Evidence: evidence/latest.json ({report['seconds']}s)")
    return int(any(row["returncode"] for row in rows))


if __name__ == "__main__":
    raise SystemExit(main())
