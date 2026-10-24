"""
evidence_extractors/log_extractor.py

Plain-English explanation:
  Log files contain structured service events like:
    2026-09-26T08:57:37Z level=INFO service=account_service ... resource_id=account_7566 rows=0 http_status=404

  Each line represents one service event. We:
  1. Parse each line into key=value pairs (and the leading timestamp).
  2. Filter to lines at or before the audit_at cutoff.
  3. Correlate lines by trace_id so queries spanning multiple lines
     (e.g., query_started with lookup_key -> candidate_evaluated / heartbeat)
     correctly attribute their results to the user.
  4. Map each event type and result to a finding (PRESENT, ABSENT, ACTIVE, DISABLED, BLOCKED, etc.).
"""

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


_KV_RE = re.compile(r'(\w+)=("(?:[^"\\]|\\.)*"|\S+)')
_TS_RE = re.compile(r'^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)')


def _parse_line(line: str) -> dict:
    """Parse a structured log line into a dict."""
    result = {}
    line = line.strip()
    ts_match = _TS_RE.match(line)
    if ts_match:
        result["_timestamp"] = ts_match.group(1)
    for key, val in _KV_RE.findall(line):
        result[key] = val.strip('"')
    return result


def _parse_iso(ts: str) -> Optional[datetime]:
    try:
        ts = ts.strip()
        if ts.endswith("Z"):
            ts = ts[:-1] + "+00:00"
        return datetime.fromisoformat(ts)
    except Exception:
        return None


def _normalise(v: Any) -> str:
    return str(v or "").strip().lower()


_PRESENCE_EVENTS = {
    "profile_lookup_completed",
    "index_query_completed",
    "support_ticket_read_completed",
    "analytics_profile_read_completed",
    "audit_record_read_completed",
    "export_read_completed",
    "marketing_profile_read_completed",
    "contact_lookup_completed",
    "contact_query_completed",
    "record_lookup",
    "deletion_marker_check",
    "export_download_check_completed",
    "export_metadata_read_completed",
}

_FLOW_EVENTS = {
    "connector_config_read_completed",
    "connector_heartbeat",
}

_RESTORE_EVENTS = {
    "restore_policy_read_completed",
    "restore_candidate_evaluated",
}

_PII_EVENTS = {
    "message_pii_scan",
    "attachment_pii_scan",
    "analytics_identity_scan",
}


def _is_absent(parsed: dict) -> bool:
    """Return True if the log line reports a resource as absent/deleted."""
    if parsed.get("marker_found", "").lower() == "true":
        return True
    if parsed.get("available", "").lower() == "false":
        return True
    return (
        parsed.get("http_status") == "404"
        or parsed.get("rows") == "0"
        or parsed.get("result") in ("miss", "not_found", "absent", "deleted")
    )


def _is_present(parsed: dict) -> bool:
    """Return True if the log line reports a resource as still present."""
    if parsed.get("marker_found", "").lower() == "false":
        return True
    if parsed.get("available", "").lower() == "true":
        return True
    return (
        parsed.get("http_status") == "200"
        or (parsed.get("rows") not in (None, "0") and parsed.get("rows") is not None)
        or parsed.get("result") in ("hit", "found", "present")
    )


def _identity_in_line(parsed: dict, all_ids: set) -> bool:
    """Return True if any field value in the parsed line matches a known identifier."""
    # Check priority identifier fields
    for k in ("lookup_key", "subject_key", "subject_reference", "subject_ref",
              "customer_email", "email", "phone", "email_hash", "correlation_key",
              "customer_reference", "owner_email", "requester_email", "match_key", "scan_key"):
        if k in parsed and _normalise(parsed[k]) in all_ids:
            return True

    for v in parsed.values():
        if _normalise(v) in all_ids:
            return True
    return False


def _infer_system(parsed: dict) -> str:
    svc = parsed.get("service", "")
    mapping = {
        "account_service":     "account_service",
        "search_service":      "search_service",
        "search_index_service": "search_service",
        "analytics_platform":  "analytics_platform",
        "support_platform":    "support_platform",
        "support_replica":     "support_platform",
        "integration_service": "integration_service",
        "backup_service":      "backup_service",
        "security_service":    "security_service",
        "export_service":      "export_service",
        "marketing_platform":  "marketing_platform",
    }
    return mapping.get(svc, svc or "account_service")


def _infer_record_type(parsed: dict) -> str:
    event = parsed.get("event", "")
    svc   = parsed.get("service", "")
    rid   = parsed.get("resource_id", "").lower()

    if rid.startswith("account_"):
        return "USER_PROFILE"
    if rid.startswith("search_"):
        return "SEARCH_INDEX_ENTRY"
    if rid.startswith("analytics_"):
        return "ANALYTICS_PROFILE"
    if rid.startswith("audit_record_"):
        return "SECURITY_AUDIT_LOG"
    if rid.startswith("export_"):
        return "USER_EXPORT"
    if rid.startswith("marketing_"):
        return "MARKETING_PROFILE"
    if rid.startswith("data_flow_"):
        return "DATA_FLOW"
    if rid.startswith("backup_"):
        return "BACKUP_ARCHIVE"
    if rid.startswith("tombstone_"):
        return "ACCOUNT_TOMBSTONE"
    if rid.startswith("support_"):
        if event == "deletion_marker_check" or "attachment" in event or "replica" in svc:
            return "SUPPORT_ATTACHMENT"
        return "SUPPORT_MESSAGE"

    if "profile_lookup" in event:
        return "USER_PROFILE"
    if "index_query" in event or "search" in svc:
        return "SEARCH_INDEX_ENTRY"
    if "analytics" in event or "analytics" in svc:
        return "ANALYTICS_PROFILE"
    if "support" in event or "support" in svc:
        return "SUPPORT_MESSAGE"
    if "audit_record" in event or "security" in svc:
        return "SECURITY_AUDIT_LOG"
    if "export" in event:
        return "USER_EXPORT"
    if "marketing" in event or "marketing" in svc:
        return "MARKETING_PROFILE"
    if "connector" in event or "integration" in svc:
        return "DATA_FLOW"
    if "restore" in event or "backup" in svc:
        return "BACKUP_ARCHIVE"
    return "USER_PROFILE"


def extract(log_path: Path, identity: dict, audit_at: str) -> list[dict]:
    """
    Parse a .log file and return findings for records belonging to identity.
    Only lines with timestamp <= audit_at are considered.
    """
    all_ids = (
        identity["all_emails"]
        | identity["all_phones"]
        | identity["all_email_hashes"]
        | {_normalise(identity["user_id"])}
    )

    cutoff = _parse_iso(audit_at)
    findings = []

    try:
        lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        return findings

    parsed_lines = []
    matching_traces = set()

    for line in lines:
        if not line.strip():
            continue
        parsed = _parse_line(line)
        ts_str = parsed.get("_timestamp")
        if ts_str and cutoff:
            ts = _parse_iso(ts_str)
            if ts and ts > cutoff:
                continue
        parsed_lines.append(parsed)
        if _identity_in_line(parsed, all_ids):
            tid = parsed.get("trace_id")
            if tid:
                matching_traces.add(tid)

    for parsed in parsed_lines:
        tid = parsed.get("trace_id")
        is_direct = _identity_in_line(parsed, all_ids)
        is_trace = bool(tid and tid in matching_traces)

        if not (is_direct or is_trace):
            continue

        event       = parsed.get("event", "")
        resource_id = parsed.get("resource_id", "unknown")
        if resource_id == "unknown":
            continue

        system_id   = _infer_system(parsed)
        record_type = _infer_record_type(parsed)

        # ── Presence / absence events ─────────────────────────────────────────
        if event in _PRESENCE_EVENTS:
            if _is_absent(parsed):
                state = "ABSENT"
            elif _is_present(parsed):
                # Check if analytics or support has exposed PII
                if record_type == "ANALYTICS_PROFILE":
                    email_val = parsed.get("email") or parsed.get("customer_email")
                    ref_val   = parsed.get("customer_reference")
                    hash_val  = parsed.get("correlation_key") or parsed.get("email_hash")
                    if email_val and _normalise(email_val) != "null":
                        state = "PRESENT"
                    elif ref_val and _normalise(ref_val) != "null":
                        state = "PRESENT"
                    elif hash_val and _normalise(hash_val) != "null":
                        state = "PRESENT"
                    else:
                        state = "ANONYMIZED"
                elif record_type == "SUPPORT_MESSAGE":
                    email_val = parsed.get("requester_email") or parsed.get("customer_email")
                    phone_val = parsed.get("requester_phone")
                    name_val  = parsed.get("requester_name")
                    if any(v and _normalise(v) != "null" for v in (email_val, phone_val, name_val)):
                        state = "PRESENT"
                    else:
                        state = "REDACTED"
                else:
                    state = "PRESENT"
            else:
                continue

            findings.append({
                "system_id":       system_id,
                "resource_id":     resource_id,
                "record_type":     record_type,
                "state":           state,
                "raw_event":       event,
                "evidence_detail": f"log_presence:{event}:{state}",
            })

        # ── Data flow events ──────────────────────────────────────────────────
        elif event in _FLOW_EVENTS:
            enabled = parsed.get("enabled", "").lower()
            if enabled == "true":
                state = "ACTIVE"
            elif enabled == "false":
                state = "DISABLED"
            else:
                continue

            findings.append({
                "system_id":       "integration_service",
                "resource_id":     resource_id,
                "record_type":     "DATA_FLOW",
                "state":           state,
                "raw_event":       event,
                "evidence_detail": f"connector:{event}:{state}",
            })

        # ── Restore risk events ───────────────────────────────────────────────
        elif event in _RESTORE_EVENTS:
            if event == "restore_candidate_evaluated":
                eligible = parsed.get("eligible", "").lower() == "true"
                deletion_block = parsed.get("deletion_block", "").lower() == "true"
                state = "ACTIVE" if (eligible and not deletion_block) else "BLOCKED"
            else:
                restore_allowed = parsed.get("restore_allowed", "").lower()
                if restore_allowed == "true":
                    state = "ACTIVE"
                elif restore_allowed == "false":
                    state = "BLOCKED"
                else:
                    continue

            findings.append({
                "system_id":       "backup_service",
                "resource_id":     resource_id,
                "record_type":     "BACKUP_ARCHIVE",
                "state":           state,
                "raw_event":       event,
                "evidence_detail": f"restore:{event}:{state}",
            })

        # ── PII scan events ───────────────────────────────────────────────────
        elif event in _PII_EVENTS:
            findings.append({
                "system_id":       system_id,
                "resource_id":     resource_id,
                "record_type":     record_type,
                "state":           "PRESENT",
                "raw_event":       event,
                "evidence_detail": f"pii_scan:{event}",
            })

    return findings
