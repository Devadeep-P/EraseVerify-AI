"""
evidence_loader.py — Load and temporally filter the evidence file manifest.

Plain-English explanation:
  There are 94 evidence files (SQL, JSON, log, text, PDF, PNG).
  Each has a 'captured_at' timestamp — the moment it was collected.

  For any given case, we must ONLY use evidence captured AT OR BEFORE the
  case's audit_at timestamp. Using later evidence would be "looking into
  the future" which the contest rules forbid.

  This module:
  1. Reads evidence_files.csv into memory once.
  2. For each case, returns only the evidence files that are temporally valid.
  3. Provides helpers to classify each file by type so the right extractor
     can be called.
"""

import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


# ── Internal cache ────────────────────────────────────────────────────────────
_evidence_manifest: list[dict] = []   # all 94 rows from evidence_files.csv
_evidence_by_id: dict[str, dict] = {} # file_id → row


def _parse_iso(ts: str) -> datetime:
    """Parse an ISO-8601 UTC timestamp string to a timezone-aware datetime."""
    ts = ts.strip()
    if ts.endswith("Z"):
        ts = ts[:-1] + "+00:00"
    return datetime.fromisoformat(ts)


def load_manifest(evidence_files_csv: Path) -> None:
    """
    Read evidence_files.csv into memory.
    Columns: file_id, file_path, origin, captured_at
    Call this ONCE at startup.
    """
    global _evidence_manifest, _evidence_by_id
    with open(evidence_files_csv, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))

    for row in rows:
        row["_captured_dt"] = _parse_iso(row["captured_at"])
        _evidence_by_id[row["file_id"]] = row

    _evidence_manifest = rows


def valid_evidence_for(audit_at: str, dataset_dir: Path) -> list[dict]:
    """
    Return evidence files whose captured_at <= audit_at.

    Each returned dict contains:
      file_id      str  — e.g. 'evidence_01'
      file_path    str  — relative path from dataset root
      origin       str  — source system name
      captured_at  str  — ISO timestamp string
      abs_path     Path — absolute path to the file
      file_type    str  — 'sql' | 'json' | 'log' | 'txt' | 'pdf' | 'png'
    """
    if not _evidence_manifest:
        raise RuntimeError("Call load_manifest() before valid_evidence_for().")

    cutoff = _parse_iso(audit_at)
    result = []

    for row in _evidence_manifest:
        if row["_captured_dt"] <= cutoff:
            enriched = dict(row)
            abs_path = (dataset_dir / row["file_path"]).resolve()
            enriched["abs_path"] = abs_path
            enriched["file_type"] = _classify_type(abs_path)
            result.append(enriched)

    return result


def get_by_id(file_id: str) -> Optional[dict]:
    """Look up a single evidence file by its file_id."""
    return _evidence_by_id.get(file_id)


def _classify_type(path: Path) -> str:
    """Return a short type tag based on the file extension."""
    suffix = path.suffix.lower()
    return {
        ".sql": "sql",
        ".json": "json",
        ".log": "log",
        ".txt": "txt",
        ".pdf": "pdf",
        ".png": "png",
        ".jpg": "png",   # treat JPEGs as images too
        ".jpeg": "png",
    }.get(suffix, "unknown")
