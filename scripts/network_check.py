"""Observe only this project's Python/Ollama processes; never alters network settings."""
import json
import time
from pathlib import Path

import psutil

root = Path(__file__).resolve().parents[1]
records = []
for process in psutil.process_iter(["pid", "name", "cmdline", "cwd", "exe"]):
    try:
        info = process.info
        ours = (info["exe"] and str(root / ".runtime/ollama").lower() in info["exe"].lower()) or (
            info["cwd"] and Path(info["cwd"]) == root and any("backend.app" in c for c in info["cmdline"] or []))
        if not ours:
            continue
        for connection in process.net_connections(kind="inet"):
            if connection.raddr:
                records.append({"pid": process.pid, "name": info["name"], "remote": list(connection.raddr),
                                "external": connection.raddr.ip not in {"127.0.0.1", "::1"}})
    except (psutil.AccessDenied, psutil.NoSuchProcess):
        continue
report = {"time": time.time(), "connections": records, "external": [r for r in records if r["external"]]}
target = root / "docs/verification/network.json"
target.parent.mkdir(parents=True, exist_ok=True)
target.write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report, indent=2))
