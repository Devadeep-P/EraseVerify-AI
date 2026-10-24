"""
evidence_extractors/json_extractor.py — Parse JSON evidence files for personal data.

Plain-English explanation:
  JSON evidence files in the dataset come in several distinct structures:
  1. service_resource_export_*.json:
     Contains top-level 'service_exports' with sections for each service:
     - account_service (profile_lookups with status_code 200/404)
     - analytics_platform (profiles: attributable PII vs. anonymized)
     - backup_service (restore_entries with restore_allowed flag)
     - export_service (exports with owner_email)
     - integration_service (connectors with enabled flag)
     - search_service (index_queries with hits)
     - security_service (audit_records with subject_reference)
     - support_platform (tickets with requester_email/phone)
  2. customer_data_snapshot_bundle_*.json:
     Contains 'snapshots' per data_store and collection (e.g. customer_profiles,
     deleted_customer_references/tombstones, security_audit_events).
  3. connector_configurations_*.json:
     Contains connector configuration records with enabled flag.
  4. security_audit_ledger_*.json:
     Contains audit trail ledger records.
  5. customer_export_jobs_*.json & customer_export_manifest_*.json:
     Contains export jobs with download_available flag.
  6. customer_analytics_report_*.json:
     Contains analytics profiles.

  This extractor checks records against all known identifiers (user_id, current
  and historical emails, phones, email hashes) and extracts finding dicts.
"""

import json
from pathlib import Path
from typing import Any, Optional


def _normalise(v: Any) -> str:
    """Lowercase + strip string for case-insensitive matching."""
    return str(v or "").strip().lower()


def _identity_in_record(record: dict, all_ids: set) -> bool:
    """Recursively check if any value in a record matches known identifiers."""
    for v in record.values():
        if isinstance(v, str) and _normalise(v) in all_ids:
            return True
        if isinstance(v, dict):
            if _identity_in_record(v, all_ids):
                return True
        if isinstance(v, list):
            for item in v:
                if isinstance(item, str) and _normalise(item) in all_ids:
                    return True
                if isinstance(item, dict) and _identity_in_record(item, all_ids):
                    return True
    return False


def _state_from_result(result_str: str) -> str:
    """Normalize string results to allowed state constants."""
    result = _normalise(result_str)
    if result in ("found", "present", "active", "hit"):
        return "PRESENT"
    if result in ("not_found", "absent", "deleted", "miss"):
        return "ABSENT"
    if result in ("anonymized", "anonymised"):
        return "ANONYMIZED"
    if result in ("redacted",):
        return "REDACTED"
    if result in ("identifiable",):
        return "IDENTIFIABLE"
    if result in ("disabled", "stopped"):
        return "DISABLED"
    if result in ("blocked",):
        return "BLOCKED"
    return "PRESENT"


def extract(json_path: Path, identity: dict) -> list[dict]:
    """
    Parse any JSON evidence file and return findings for the given identity.

    Each finding dict:
    {
        'system_id':       str   — canonical system (e.g. account_service)
        'resource_id':     str   — resource identifier (e.g. account_001)
        'record_type':     str   — data category (e.g. USER_PROFILE)
        'state':           str   — PRESENT | ABSENT | ACTIVE | DISABLED | BLOCKED | REDACTED | ANONYMIZED
        'evidence_detail': str   — provenance/audit detail
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
        data = json.loads(json_path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return findings

    # ── Format 1: service_resource_export_*.json ──────────────────────────────
    if "service_exports" in data and isinstance(data["service_exports"], dict):
        se = data["service_exports"]

        # 1. account_service
        for item in se.get("account_service", {}).get("profile_lookups", []):
            profile = item.get("profile") or {}
            if _identity_in_record(profile, all_ids) or _normalise(item.get("resource_id")) in all_ids:
                status_code = item.get("status_code")
                state = "ABSENT" if status_code == 404 else "PRESENT"
                findings.append({
                    "system_id": "account_service",
                    "resource_id": item.get("resource_id", "unknown"),
                    "record_type": "USER_PROFILE",
                    "state": state,
                    "evidence_detail": f"profile_lookup:http_{status_code}",
                })

        # 2. analytics_platform
        for item in se.get("analytics_platform", {}).get("profiles", []):
            # Check if this profile belongs to user
            is_match = (
                _normalise(item.get("customer_reference")) in all_ids
                or _normalise(item.get("email")) in all_ids
                or _normalise(item.get("phone")) in all_ids
                or _normalise(item.get("email_hash")) in all_ids
            )
            # Or if resource_id matches known user resources
            if is_match or _normalise(item.get("resource_id")) in all_ids:
                # Check whether identifiable PII is still exposed
                has_pii = bool(
                    item.get("email")
                    or item.get("phone")
                    or item.get("email_hash")
                    or (item.get("customer_reference") and _normalise(item.get("customer_reference")) != _normalise(identity["user_id"]))
                )
                state = "IDENTIFIABLE" if has_pii else "ANONYMIZED"
                findings.append({
                    "system_id": "analytics_platform",
                    "resource_id": item.get("resource_id", "unknown"),
                    "record_type": "ANALYTICS_PROFILE",
                    "state": state,
                    "evidence_detail": f"analytics_profile:pii={has_pii}",
                })

        # 3. backup_service
        for item in se.get("backup_service", {}).get("restore_entries", []):
            if _identity_in_record(item, all_ids) or _normalise(item.get("resource_id")) in all_ids:
                allowed = item.get("restore_allowed")
                state = "ACTIVE" if allowed is True else "BLOCKED"
                findings.append({
                    "system_id": "backup_service",
                    "resource_id": item.get("resource_id", "unknown"),
                    "record_type": "BACKUP_ARCHIVE",
                    "state": state,
                    "evidence_detail": f"restore_allowed={allowed}",
                })

        # 4. export_service
        for item in se.get("export_service", {}).get("exports", []):
            if _identity_in_record(item, all_ids) or _normalise(item.get("resource_id")) in all_ids:
                findings.append({
                    "system_id": "export_service",
                    "resource_id": item.get("resource_id", "unknown"),
                    "record_type": "USER_EXPORT",
                    "state": "PRESENT",
                    "evidence_detail": f"export_object={item.get('object_key')}",
                })

        # 5. integration_service
        for item in se.get("integration_service", {}).get("connectors", []):
            if _identity_in_record(item, all_ids) or _normalise(item.get("resource_id")) in all_ids:
                enabled = item.get("enabled")
                state = "ACTIVE" if enabled is True else "DISABLED"
                findings.append({
                    "system_id": "integration_service",
                    "resource_id": item.get("resource_id", "unknown"),
                    "record_type": "DATA_FLOW",
                    "state": state,
                    "evidence_detail": f"connector_enabled={enabled}",
                })

        # 6. search_service
        for item in se.get("search_service", {}).get("index_queries", []):
            query_match = _normalise(item.get("query")) in all_ids
            hits = item.get("hits", {})
            docs = hits.get("documents", [])
            doc_match = any(_identity_in_record(doc, all_ids) for doc in docs)
            if query_match or doc_match or _normalise(item.get("resource_id")) in all_ids:
                total_hits = hits.get("total", len(docs))
                state = "PRESENT" if total_hits > 0 else "ABSENT"
                findings.append({
                    "system_id": "search_service",
                    "resource_id": item.get("resource_id", "unknown"),
                    "record_type": "SEARCH_INDEX_ENTRY",
                    "state": state,
                    "evidence_detail": f"search_hits={total_hits}",
                })

        # 7. security_service
        for item in se.get("security_service", {}).get("audit_records", []):
            if _identity_in_record(item, all_ids) or _normalise(item.get("resource_id")) in all_ids:
                findings.append({
                    "system_id": "security_service",
                    "resource_id": item.get("resource_id", "unknown"),
                    "record_type": "SECURITY_AUDIT_LOG",
                    "state": "PRESENT",
                    "evidence_detail": f"security_audit_until={item.get('retention_until')}",
                })

        # 8. support_platform
        for item in se.get("support_platform", {}).get("tickets", []):
            if _identity_in_record(item, all_ids) or _normalise(item.get("resource_id")) in all_ids:
                has_pii = bool(item.get("requester_email") or item.get("requester_phone") or item.get("requester_name"))
                state = "IDENTIFIABLE" if has_pii else "REDACTED"
                findings.append({
                    "system_id": "support_platform",
                    "resource_id": item.get("resource_id", "unknown"),
                    "record_type": "SUPPORT_MESSAGE",
                    "state": state,
                    "evidence_detail": f"support_ticket:pii={has_pii}",
                })

    # ── Format 2: customer_data_snapshot_bundle_*.json ────────────────────────
    if "snapshots" in data:
        for snapshot in data.get("snapshots", []):
            data_store = snapshot.get("data_store", "")
            collection = snapshot.get("collection", "")

            for record in snapshot.get("records", []):
                if _identity_in_record(record, all_ids):
                    resource_id = record.get("resource_id", "unknown")

                    if collection == "deleted_customer_references" or "tombstone" in resource_id:
                        # Account tombstone check: PII must be stripped
                        has_pii = bool(record.get("name") or record.get("email") or record.get("phone") or record.get("email_hash"))
                        state = "IDENTIFIABLE" if has_pii else "REDACTED"
                        findings.append({
                            "system_id": "identity_service",
                            "resource_id": resource_id,
                            "record_type": "ACCOUNT_TOMBSTONE",
                            "state": state,
                            "evidence_detail": f"tombstone:pii={has_pii}",
                        })
                    elif collection == "security_audit_events":
                        findings.append({
                            "system_id": "security_service",
                            "resource_id": resource_id,
                            "record_type": "SECURITY_AUDIT_LOG",
                            "state": "PRESENT",
                            "evidence_detail": f"security_event:{record.get('event_name')}",
                        })
                    else:
                        result_str = record.get("result") or record.get("status") or "found"
                        state = _state_from_result(result_str)
                        findings.append({
                            "system_id": data_store or "account_service",
                            "resource_id": resource_id,
                            "record_type": "USER_PROFILE",
                            "state": state,
                            "evidence_detail": f"snapshot:{collection}:{resource_id}",
                        })

    # ── Format 3: Flat 'records' list (connector configs, ledgers, export manifests)
    if "records" in data and "snapshots" not in data and "service_exports" not in data:
        origin = data.get("origin") or data.get("source") or ""
        collection = data.get("collection", "")

        for record in data.get("records", []):
            if _identity_in_record(record, all_ids):
                resource_id = record.get("resource_id", "unknown")
                system_id = record.get("system") or origin or "account_service"
                record_type = record.get("record_type") or "USER_PROFILE"

                # Check if connector with enabled flag
                if "enabled" in record:
                    state = "ACTIVE" if str(record["enabled"]).lower() == "true" else "DISABLED"
                    record_type = "DATA_FLOW"
                    system_id = "integration_service"
                elif "download_available" in record:
                    state = "PRESENT" if record.get("download_available") else "ABSENT"
                    record_type = "USER_EXPORT"
                    system_id = "export_service"
                elif "result" in record:
                    state = _state_from_result(record["result"])
                else:
                    # Generic record present in snapshot
                    has_pii = bool(record.get("email") or record.get("phone") or record.get("name"))
                    state = "IDENTIFIABLE" if has_pii else "ANONYMIZED"

                findings.append({
                    "system_id": system_id,
                    "resource_id": resource_id,
                    "record_type": record_type,
                    "state": state,
                    "evidence_detail": f"record:{resource_id}",
                })

    return findings
