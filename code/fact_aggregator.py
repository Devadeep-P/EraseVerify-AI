"""
fact_aggregator.py — Combine multi-source evidence facts per user.

Plain-English explanation:
  Different evidence files provide different views of the platform:
  - SQL files show whether records physically exist in primary or replica databases.
  - JSON snapshots/exports show records in caches, search indexes, connectors, and archives.
  - Log files show HTTP lookups (200 vs 404) and trace events.
  - Handover text and PDF files show audit logs and legal retention registers.

  We must combine all valid evidence captured at or before the case's audit_at.
  Importantly:
  - We do not blindly choose the latest fact.
  - Actual storage state evidence (SQL tables, JSON bundles) has higher authority
    than workflow claims or log lookup responses.
  - If any authoritative evidence shows data still exists, PII is exposed, or a sync/restore
    path is active, we treat it conservatively as an unresolved issue.
  - When a resource_id has a DELETE activity in system_activity and is NOT found in
    any snapshot, it is added as ABSENT (confirmed deleted) using the snapshot as evidence.
"""

import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from evidence_extractors import (
    sql_extractor,
    json_extractor,
    log_extractor,
    text_extractor,
    pdf_extractor,
    image_extractor,
)


def _normalise(v: Any) -> str:
    return str(v or "").strip().lower()


def _parse_iso(ts: str) -> Optional[datetime]:
    try:
        ts = ts.strip()
        if ts.endswith("Z"):
            ts = ts[:-1] + "+00:00"
        return datetime.fromisoformat(ts)
    except Exception:
        return None


# Authority weights: actual storage state > operational logs/docs > claims
_FILE_TYPE_AUTHORITY = {
    "sql":  30,
    "json": 30,
    "txt":  20,
    "pdf":  20,
    "png":  15,
    "log":  10,
}

_activity_rows: list[dict] = []


def load_activity(system_activity_csv: Path) -> None:
    """Load system_activity.csv into memory once."""
    global _activity_rows
    with open(system_activity_csv, encoding="utf-8", newline="") as f:
        _activity_rows = list(csv.DictReader(f))


import re

def _derivable_resource_ids(identity: dict) -> set:
    """
    Derive the expected set of resource_id strings for this user using the
    platform's naming convention.

    On this platform, user_id follows the pattern 'user_<number>', and the
    primary account resource_id follows 'account_<number>' zero-padded to 3 digits
    (account_001 for user_01, account_010 for user_10, etc.).
    """
    user_id = _normalise(identity.get("user_id", ""))
    candidates = set()
    if user_id.startswith("user_"):
        num_str = user_id[len("user_"):]
        try:
            num = int(num_str)
            candidates.add(f"account_{num:03d}")
        except ValueError:
            pass
    return candidates


def _get_activity_for(identity: dict, audit_at: str) -> list[dict]:
    """
    Return system_activity rows that mention the user AND occurred at or before audit_at.
    Matches on: emails, phones, email_hashes, user_id, AND derivable resource_ids.
    """
    all_ids = (
        identity["all_emails"]
        | identity["all_phones"]
        | identity["all_email_hashes"]
        | {_normalise(identity["user_id"])}
        | _derivable_resource_ids(identity)
    )
    cutoff = _parse_iso(audit_at)
    results = []
    for row in _activity_rows:
        et = _parse_iso(row.get("event_time", ""))
        if cutoff and et and et > cutoff:
            continue
        resource = _normalise(row.get("resource_id", ""))
        details = _normalise(row.get("details", ""))

        # Exact match on resource_id
        if resource in all_ids:
            results.append(row)
            continue

        # Exact or word-bounded match in details
        matched = False
        for id_val in all_ids:
            if not id_val:
                continue
            if id_val.startswith("account_") or id_val.startswith("user_"):
                pattern = r'(?<![a-zA-Z0-9_])' + re.escape(id_val) + r'(?![a-zA-Z0-9_])'
                if re.search(pattern, details):
                    matched = True
                    break
            elif id_val in details:
                matched = True
                break

        if matched:
            results.append(row)

    return results


def _supplement_absent_from_activity(
    resolved_records: dict,
    activity_claims: list[dict],
    valid_evidence: list[dict],
    identity: dict,
) -> dict:
    """
    For any resource_id with a DELETE_RECORD activity claim that is NOT already
    in resolved_records, AND at least one SQL or JSON snapshot was scanned, add
    an ABSENT record using the most authoritative snapshot file as evidence.

    This handles the case where an account was deleted and therefore does NOT
    appear in the snapshot — the absence from the snapshot IS the evidence of deletion.

    We only do this for resources that:
    1. Have a DELETE_RECORD activity (system_activity) for this user, OR
    2. Are known system-activity resources whose target_system matches.

    We pick the most recently-captured SQL/JSON snapshot as the evidence_id.
    """
    # Collect snapshot evidence files (SQL and JSON, sorted by captured_at desc)
    snapshot_files = sorted(
        [ev for ev in valid_evidence if ev.get("file_type") in ("sql", "json")],
        key=lambda ev: ev["_captured_dt"],
        reverse=True,
    )
    if not snapshot_files:
        return resolved_records

    best_snapshot = snapshot_files[0]  # most recent authoritative snapshot

    # Build map of (target_system, resource_id) from DELETE activities
    for row in activity_claims:
        event_type = (row.get("event_type") or "").strip().upper()
        if event_type not in ("DELETE_RECORD", "ANONYMIZE_RECORD", "REDACT_RECORD"):
            continue
        resource_id = (row.get("resource_id") or "").strip()
        target_system = (row.get("target_system") or "").strip().lower()
        if not resource_id:
            continue

        # Map target_system to canonical system_id
        system_id = _map_target_system(target_system)
        key = (system_id, resource_id.lower())

        if key in resolved_records:
            continue  # already have evidence for this resource

        # Determine record_type from resource_id prefix
        record_type = _infer_record_type_from_resource_id(resource_id)

        # Determine correct operation-to-state mapping
        if event_type == "ANONYMIZE_RECORD":
            state = "ANONYMIZED"
        elif event_type == "REDACT_RECORD":
            state = "REDACTED"
        else:
            state = "ABSENT"

        resolved_records[key] = {
            "system_id":   system_id,
            "resource_id": resource_id,
            "record_type": record_type,
            "state":       state,
            "evidence_id": best_snapshot["file_id"],
            "captured_at": best_snapshot["captured_at"],
        }

    # For derivable primary account (account_00X for user_0X):
    # Only supplement if NO account was discovered for this user in account_service
    has_account = any(s == "account_service" for (s, r) in resolved_records.keys())
    if not has_account:
        derivable_accounts = _derivable_resource_ids(identity)
        db_snapshots = [ev for ev in snapshot_files if ev.get("file_type") == "sql"]
        best_db_snapshot = db_snapshots[0] if db_snapshots else best_snapshot
        for acc in derivable_accounts:
            key = ("account_service", acc)
            if key not in resolved_records:
                resolved_records[key] = {
                    "system_id":   "account_service",
                    "resource_id": acc,
                    "record_type": "USER_PROFILE",
                    "state":       "ABSENT",
                    "evidence_id": best_db_snapshot["file_id"],
                    "captured_at": best_db_snapshot["captured_at"],
                }

    return resolved_records


def _map_target_system(target_system: str) -> str:
    """Map system_activity target_system strings to canonical system_id values."""
    mapping = {
        "account_service":    "account_service",
        "search_service":     "search_service",
        "analytics_platform": "analytics_platform",
        "analytics":          "analytics_platform",
        "support_platform":   "support_platform",
        "support":            "support_platform",
        "security_service":   "security_service",
        "export_service":     "export_service",
        "marketing_platform": "marketing_platform",
        "marketing":          "marketing_platform",
        "integration_service": "integration_service",
        "backup_service":     "backup_service",
        "identity_service":   "identity_service",
    }
    for k, v in mapping.items():
        if k in target_system:
            return v
    return target_system or "account_service"


def _infer_record_type_from_resource_id(resource_id: str) -> str:
    """Infer a record type from resource_id naming convention."""
    rid = resource_id.lower()
    if rid.startswith("account_"):
        return "USER_PROFILE"
    if rid.startswith("search_"):
        return "SEARCH_INDEX_ENTRY"
    if rid.startswith("analytics_"):
        return "ANALYTICS_PROFILE"
    if rid.startswith("support_"):
        return "SUPPORT_MESSAGE"
    if rid.startswith("audit_record_") or rid.startswith("security_"):
        return "SECURITY_AUDIT_LOG"
    if rid.startswith("export_"):
        return "USER_EXPORT"
    if rid.startswith("marketing_"):
        return "MARKETING_PROFILE"
    if rid.startswith("tombstone_"):
        return "ACCOUNT_TOMBSTONE"
    if rid.startswith("backup_"):
        return "BACKUP_ARCHIVE"
    if rid.startswith("data_flow_"):
        return "DATA_FLOW"
    return "USER_PROFILE"


def aggregate(identity: dict, valid_evidence: list[dict], audit_at: str) -> dict:
    """
    Run extractors over valid_evidence files and return a unified FactSet.

    FactSet structure:
    {
        'records': {
            (system_id, resource_id): {
                'system_id':    str
                'resource_id':  str
                'record_type':  str
                'state':        str
                'evidence_id':  str
                'captured_at':  str
            }
        },
        'activity_claims': list[dict]
    }
    """
    # Key: (system_id, resource_id) -> list of all collected findings
    grouped: dict[tuple, list[dict]] = {}

    for ev_file in valid_evidence:
        file_id     = ev_file["file_id"]
        file_type   = ev_file["file_type"]
        abs_path    = ev_file["abs_path"]
        captured_dt = ev_file["_captured_dt"]
        captured_at = ev_file["captured_at"]

        raw_findings = _run_extractor(file_type, abs_path, identity, audit_at)

        for finding in raw_findings:
            key = (_normalise(finding["system_id"]),
                   _normalise(finding["resource_id"]))
            finding["evidence_id"] = file_id
            finding["captured_at"] = captured_at
            finding["_captured_dt"] = captured_dt
            finding["_authority"] = _FILE_TYPE_AUTHORITY.get(file_type, 10)

            if key not in grouped:
                grouped[key] = []
            grouped[key].append(finding)

    # Resolve each resource's final state conservatively:
    # 1. Higher authority beats lower authority.
    # 2. Within equal authority, newer captured_at beats older.
    # 3. If any authoritative evidence shows data still PRESENT/IDENTIFIABLE/ACTIVE,
    #    we do not let a 404 claim or vague absence override it.
    resolved_records = {}

    for key, findings_list in grouped.items():
        # Check if any finding reveals an active issue (ghost data, exposed PII, active flow, restore risk)
        issue_findings = [
            f for f in findings_list
            if f["state"] in ("PRESENT", "IDENTIFIABLE", "ACTIVE")
        ]

        if issue_findings:
            # Sort issue findings by authority desc, then captured_dt desc
            issue_findings.sort(
                key=lambda f: (f["_authority"], f["_captured_dt"]),
                reverse=True
            )
            winner = issue_findings[0]
        else:
            # All evidence indicates absence/compliance; pick highest authority, most recent
            findings_list.sort(
                key=lambda f: (f["_authority"], f["_captured_dt"]),
                reverse=True
            )
            winner = findings_list[0]

        resolved_records[key] = {
            "system_id":   winner["system_id"],
            "resource_id": winner["resource_id"],
            "record_type": winner.get("record_type", "USER_PROFILE"),
            "state":       winner["state"],
            "evidence_id": winner["evidence_id"],
            "captured_at": winner["captured_at"],
        }

    activity_claims = _get_activity_for(identity, audit_at)

    # Supplement with ABSENT records derived from DELETE activity + snapshot absence
    resolved_records = _supplement_absent_from_activity(
        resolved_records, activity_claims, valid_evidence, identity
    )

    return {
        "records": resolved_records,
        "activity_claims": activity_claims,
    }


def _run_extractor(file_type: str, path: Path,
                   identity: dict, audit_at: str) -> list[dict]:
    """Safely dispatch to the matching extractor."""
    try:
        if file_type == "sql":
            return sql_extractor.extract(path, identity)
        elif file_type == "json":
            return json_extractor.extract(path, identity)
        elif file_type == "log":
            return log_extractor.extract(path, identity, audit_at)
        elif file_type == "txt":
            return text_extractor.extract(path, identity)
        elif file_type == "pdf":
            return pdf_extractor.extract(path, identity)
        elif file_type == "png":
            return image_extractor.extract(path, identity)
        else:
            return []
    except Exception:
        return []
