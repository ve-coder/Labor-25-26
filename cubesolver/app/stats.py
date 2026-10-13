"""Statistik der Durchläufe (data/stats.json)."""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path


class Stats:
    def __init__(self, path: Path):
        self.path = path
        self.lock = threading.Lock()
        self.runs = []
        if path.exists():
            try:
                self.runs = json.loads(path.read_text())
            except Exception:
                self.runs = []

    def add(self, run: dict):
        run = dict(run)
        run.setdefault("time", time.time())
        with self.lock:
            self.runs.append(run)
            self.runs = self.runs[-1000:]
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self.runs, indent=1))

    def clear(self):
        with self.lock:
            self.runs = []
            if self.path.exists():
                self.path.unlink()

    def summary(self):
        runs = self.runs
        ok = [r for r in runs if r.get("ok")]

        def avg(key, rs):
            vals = [r[key] for r in rs if r.get(key) is not None]
            return round(sum(vals) / len(vals), 2) if vals else None

        def best(key, rs):
            vals = [r[key] for r in rs if r.get(key) is not None]
            return round(min(vals), 2) if vals else None

        errors = {}
        for r in runs:
            if not r.get("ok") and r.get("error"):
                key = r["error"].split(":")[0][:60]
                errors[key] = errors.get(key, 0) + 1
        return {
            "total": len(runs),
            "ok": len(ok),
            "success_rate": round(100 * len(ok) / len(runs)) if runs else None,
            "avg_total_s": avg("total_s", ok),
            "best_total_s": best("total_s", ok),
            "avg_scan_s": avg("scan_s", ok),
            "avg_solve_s": avg("solve_s", ok),
            "avg_moves": avg("moves", ok),
            "best_moves": best("moves", ok),
            "errors": errors,
            "last": list(reversed(runs[-25:])),
        }
