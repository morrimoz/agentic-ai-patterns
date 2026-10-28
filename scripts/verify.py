"""One offline verification command, recording test output and repeatable scenario evidence."""

from __future__ import annotations

import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time


def main():
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    from run_all import fingerprint

    env = {key: value for key, value in os.environ.items() if not key.endswith("API_KEY")}
    env.update(
        AI_PROVIDER="fake", EMBEDDING_PROVIDER="fake", LANGSMITH_TRACING="false", LANGCHAIN_TRACING_V2="false"
    )
    evidence = root / "evidence"
    evidence.mkdir(exist_ok=True)
    commands = [
        ["-m", "pytest"],
        ["run_all.py"],
        ["scripts/smoke_http.py"],
        ["-m", "patterns.application.cli", "walkthrough"],
    ]
    results = []
    for index, args in enumerate(commands):
        started = time.monotonic()
        process = subprocess.run(
            [sys.executable, *args], cwd=root, env=env, text=True, capture_output=True, timeout=120
        )
        record = {
            "command": "python " + " ".join(args),
            "returncode": process.returncode,
            "seconds": round(time.monotonic() - started, 3),
            "stdout": process.stdout,
            "stderr": process.stderr,
        }
        results.append(record)
        if index == 3 and process.returncode == 0:
            (evidence / "integrated.json").write_text(process.stdout)
        print(("PASS" if process.returncode == 0 else "FAIL") + " " + record["command"], flush=True)
        if process.returncode:
            print(process.stdout + process.stderr)
    report = {
        "python": platform.python_version(),
        "source_sha256": fingerprint(),
        "providers": "offline fixtures",
        "commands": results,
        "passed": all(row["returncode"] == 0 for row in results),
    }
    (evidence / "verification.json").write_text(json.dumps(report, indent=2) + "\n")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
