"""
identity_resolver.py — Resolve a case's email to a full identity set.

Plain-English explanation:
  The person filing a deletion request may have changed their email before
  submitting it. So we need to look up BOTH the current email table AND the
  historical change log to find who they really are.

  Steps:
  1. Try to find the email directly in user_identities.csv (current email).
  2. If that fails, search user_audit_log.csv for that email in old/new values.
  3. Once we know the user_id, fetch the FULL current identity.
  4. Return a dict with user_id, ALL current identifiers, AND all historical
     emails/phones/hashes so we can search for ghost data under any alias.
"""

import csv
from pathlib import Path
from typing import Optional

# ── Internal cache (loaded once, reused for all 518 cases) ───────────────────
_identities: dict   = {}   # email (lower) → row dict
_by_user_id: dict   = {}   # user_id → row dict
_audit_rows: list   = []   # raw rows from user_audit_log.csv


def _normalise(value: Optional[str]) -> str:
    """Lowercase + strip a string for case-insensitive matching."""
    return (value or "").strip().lower()


def load_tables(identities_csv: Path, audit_log_csv: Path) -> None:
    """
    Load user_identities.csv and user_audit_log.csv into memory.
    Call this ONCE before processing any cases.
    """
    global _identities, _by_user_id, _audit_rows

    # ── user_identities.csv ──────────────────────────────────────────────────
    # Columns: user_id, name, email, phone, email_hash, updated_at
    with open(identities_csv, encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            key = _normalise(row["email"])
            _identities[key] = row
            _by_user_id[row["user_id"]] = row

    # ── user_audit_log.csv ───────────────────────────────────────────────────
    # Columns: audit_id, user_id, event_time, field_name, old_value, new_value
    with open(audit_log_csv, encoding="utf-8", newline="") as f:
        _audit_rows = list(csv.DictReader(f))


def resolve(request_email: str) -> Optional[dict]:
    """
    Given the email from a deletion request, return a complete identity dict or
    None if the email cannot be matched to any known user.

    Returned dict keys:
        user_id           str   — canonical internal ID
        current_email     str   — current email (from user_identities.csv)
        current_phone     str
        current_email_hash str
        current_name      str
        all_emails        set   — current + all historical emails (lowercase)
        all_phones        set   — current + all historical phone numbers
        all_email_hashes  set   — current + all historical email hashes
        audit_ids         list  — audit_id values for this user (cite in steps)
    """
    if not _identities:
        raise RuntimeError("Call load_tables() before resolve().")

    needle = _normalise(request_email)
    if not needle:
        return None

    # ── Step 1: direct lookup by current email ────────────────────────────────
    identity_row = _identities.get(needle)

    # ── Step 2: search audit log for historical match ─────────────────────────
    if identity_row is None:
        for row in _audit_rows:
            if (_normalise(row.get("old_value", "")) == needle or
                    _normalise(row.get("new_value", "")) == needle):
                uid = row["user_id"]
                identity_row = _by_user_id.get(uid)
                break  # first match is sufficient

    if identity_row is None:
        return None   # unknown user

    uid = identity_row["user_id"]

    # ── Step 3: collect ALL historical identifiers for this user ──────────────
    all_emails        = {_normalise(identity_row["email"])}
    all_phones        = {_normalise(identity_row["phone"])}
    all_email_hashes  = {_normalise(identity_row["email_hash"])}
    audit_ids         = []

    for row in _audit_rows:
        if row["user_id"] != uid:
            continue
        audit_ids.append(row["audit_id"])
        field = row["field_name"]
        if field == "email":
            all_emails.add(_normalise(row["old_value"]))
            all_emails.add(_normalise(row["new_value"]))
        elif field == "phone":
            all_phones.add(_normalise(row["old_value"]))
            all_phones.add(_normalise(row["new_value"]))
        elif field == "email_hash":
            all_email_hashes.add(_normalise(row["old_value"]))
            all_email_hashes.add(_normalise(row["new_value"]))

    # Remove empty strings that crept in
    all_emails       -= {""}
    all_phones       -= {""}
    all_email_hashes -= {""}

    return {
        "user_id":            uid,
        "current_email":      identity_row["email"],
        "current_phone":      identity_row["phone"],
        "current_email_hash": identity_row["email_hash"],
        "current_name":       identity_row["name"],
        "all_emails":         all_emails,
        "all_phones":         all_phones,
        "all_email_hashes":   all_email_hashes,
        "audit_ids":          audit_ids,
    }


def identity_matches(record_value: Optional[str], identity: dict) -> bool:
    """
    Return True if record_value matches any identifier in the identity set.
    Works for emails, phones, email hashes, or user_id strings.
    Comparison is case-insensitive.
    """
    if record_value is None:
        return False
    norm = _normalise(record_value)
    if not norm:
        return False
    return (
        norm in identity["all_emails"]
        or norm in identity["all_phones"]
        or norm in identity["all_email_hashes"]
        or norm == _normalise(identity["user_id"])
    )
