"""Append-only provenance manifest (JSONL).

Every successful download appends one record so every byte in the warehouse is
auditable and ingestion can be made idempotent (skip unchanged periods).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from . import config


def _read_all() -> list[dict]:
    if not config.MANIFEST.exists():
        return []
    rows = []
    for line in config.MANIFEST.read_text().splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def latest(source: str, period_key: str) -> dict | None:
    """Most recent manifest record for a (source, period), or None."""
    found = None
    for r in _read_all():
        if r.get("source") == source and r.get("period") == period_key:
            found = r  # later lines win (append-only history)
    return found


def record(source: str, period_key: str, url: str, sha256: str,
           num_bytes: int, rows: int, status: str = "ok") -> None:
    rec = {
        "source": source,
        "period": period_key,
        "url": url,
        "sha256": sha256,
        "bytes": num_bytes,
        "rows": rows,
        "status": status,
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    with config.MANIFEST.open("a") as fh:
        fh.write(json.dumps(rec) + "\n")


def summary() -> list[dict]:
    """Latest record per (source, period) for reporting."""
    by_key: dict[tuple[str, str], dict] = {}
    for r in _read_all():
        by_key[(r["source"], r["period"])] = r
    return sorted(by_key.values(), key=lambda r: (r["source"], r["period"]))
