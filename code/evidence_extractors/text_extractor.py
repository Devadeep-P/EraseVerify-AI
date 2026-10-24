"""
evidence_extractors/text_extractor.py

Plain-English explanation:
  The handover text file uses a pipe-delimited format:
    YYYY-MM-DDThh:mm:ssZ | system_id | resource_id | record_type | status | subject_ref

  We parse each line and check if subject_ref matches any known identifier.
  The 'status' column tells us the current state of the record.
"""

from pathlib import Path
from typing import Any


def _normalise(v: Any) -> str:
    return str(v or "").strip().lower()


_STATUS_TO_STATE = {
    "not_found":   "ABSENT",
    "found":       "PRESENT",
    "active":      "ACTIVE",
    "disabled":    "DISABLED",
    "blocked":     "BLOCKED",
    "anonymized":  "ANONYMIZED",
    "anonymised":  "ANONYMIZED",
    "redacted":    "REDACTED",
    "identifiable":"IDENTIFIABLE",
}

_RECORD_TYPE_MAP = {
    "USER_PROFILE":         "USER_PROFILE",
    "SEARCH_INDEX_ENTRY":   "SEARCH_INDEX_ENTRY",
    "ANALYTICS_PROFILE":    "ANALYTICS_PROFILE",
    "SUPPORT_MESSAGE":      "SUPPORT_MESSAGE",
    "SECURITY_AUDIT_LOG":   "SECURITY_AUDIT_LOG",
    "USER_EXPORT":          "USER_EXPORT",
    "MARKETING_PROFILE":    "MARKETING_PROFILE",
    "BACKUP_ARCHIVE":       "BACKUP_ARCHIVE",
    "ACCOUNT_TOMBSTONE":    "ACCOUNT_TOMBSTONE",
    "DATA_FLOW":            "DATA_FLOW",
}


def extract(txt_path: Path, identity: dict) -> list[dict]:
    """
    Parse a pipe-delimited handover .txt file.

    Returns a list of finding dicts:
    {
        'system_id':    str
        'resource_id':  str
        'record_type':  str
        'state':        str
        'evidence_detail': str
    }
    """
    all_ids = (
        identity["all_emails"]
        | identity["all_phones"]
        | identity["all_email_hashes"]
        | {_normalise(identity["user_id"])}
    )

    findings = []

    try:
        lines = txt_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        return findings

    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "|" not in line:
            continue

        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 6:
            continue

        # Format: timestamp | system_id | resource_id | record_type | status | subject_ref
        _timestamp   = parts[0]
        system_id    = parts[1]
        resource_id  = parts[2]
        record_type  = parts[3].upper()
        status       = parts[4].upper()
        subject_ref  = parts[5]

        # Check if subject_ref matches the identity
        if _normalise(subject_ref) not in all_ids:
            continue

        state = _STATUS_TO_STATE.get(status.lower(), "PRESENT")
        mapped_record_type = _RECORD_TYPE_MAP.get(record_type, record_type)

        findings.append({
            "system_id":       system_id,
            "resource_id":     resource_id,
            "record_type":     mapped_record_type,
            "state":           state,
            "evidence_detail": line[:200],
        })

    return findings
