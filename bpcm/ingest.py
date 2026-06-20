"""Ingestion: download source files robustly and land them in data/raw.

Robustness:
- retries with exponential backoff (tenacity) on network errors;
- atomic write (temp file -> rename) so a crash never leaves a partial CSV;
- sha256 + byte-count validation, recorded in the provenance manifest;
- idempotent: an unchanged period (same sha256) is skipped unless force=True;
- a 404 (period not published yet) is logged and skipped, not fatal.
"""
from __future__ import annotations

import hashlib

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from . import config, manifest
from .sources import REGISTRY, DatasetSpec

log = config.get_logger("ingest")

_TRANSIENT = (httpx.TransportError, httpx.HTTPStatusError)


class NotPublished(Exception):
    """The requested period returned 404 — not an error, just not available yet."""


@retry(
    retry=retry_if_exception_type(_TRANSIENT),
    wait=wait_exponential(multiplier=1, min=1, max=20),
    stop=stop_after_attempt(4),
    reraise=True,
)
def _download(url: str) -> bytes:
    with httpx.Client(timeout=120, follow_redirects=True) as client:
        resp = client.get(url)
        if resp.status_code == 404:
            raise NotPublished(url)
        resp.raise_for_status()
        return resp.content


def _raw_path(spec: DatasetSpec, period_key: str):
    d = config.RAW / spec.name
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{period_key}.csv"


def ingest_one(spec: DatasetSpec, year: int, month: int | None, force: bool = False) -> str:
    """Download a single period. Returns one of: 'ok', 'skipped', 'absent'."""
    period_key = spec.period_key(year, month)
    url = spec.url(year, month)
    dest = _raw_path(spec, period_key)

    try:
        content = _download(url)
    except NotPublished:
        log.info("absent  %s %s (not published)", spec.name, period_key)
        return "absent"

    sha = hashlib.sha256(content).hexdigest()
    prev = manifest.latest(spec.name, period_key)
    if not force and dest.exists() and prev and prev.get("sha256") == sha:
        log.info("skip    %s %s (unchanged)", spec.name, period_key)
        return "skipped"

    # atomic write
    tmp = dest.with_suffix(".csv.part")
    tmp.write_bytes(content)
    tmp.replace(dest)

    rows = content.count(b"\n")  # cheap line estimate (header + data)
    manifest.record(spec.name, period_key, url, sha, len(content), rows)
    log.info("ok      %s %s (%.1f MB, ~%d rows)", spec.name, period_key,
             len(content) / 1e6, rows)
    return "ok"


def ingest(source: str, periods: list[tuple[int, int | None]], force: bool = False) -> dict:
    """Ingest many periods of one source. Returns a status tally."""
    if source not in REGISTRY:
        raise KeyError(f"unknown source '{source}'. Known: {', '.join(REGISTRY)}")
    spec = REGISTRY[source]
    tally = {"ok": 0, "skipped": 0, "absent": 0}
    for (y, m) in periods:
        tally[ingest_one(spec, y, m, force=force)] += 1
    log.info("done    %s -> %s", source, tally)
    return tally
