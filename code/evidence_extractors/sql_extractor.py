"""
evidence_extractors/sql_extractor.py

Plain-English explanation:
  SQL evidence files are snapshots of the database at a point in time.
  They use SQLite syntax, so we can load each one into an in-memory SQLite
  database and run queries to find records belonging to our deletion subject.

  Important: some files contain MULTIPLE tables — e.g. a primary table AND
  a failover-replica table. Replication drift = same user_id appears in the
  primary (deleted) but still in the replica (ghost data). We detect this.

  We scan ALL tables in the file and look for rows where any column value
  matches any of the subject's known identifiers (emails, phones, email
  hashes, user_id).  We also parse embedded JSON blob columns (e.g.
  record_json) so identity links stored inside JSON strings are detected.

  Returns a list of Finding dicts — one for each matching row found.
"""

import json
import re
import sqlite3
from pathlib import Path
from typing import Any


def _normalise(v: Any) -> str:
    return str(v or "").strip().lower()


def _table_topology(table_name: str) -> str:
    """
    Extract the DB topology from the table name suffix.
    e.g. customer_profiles_failover_replica → failover_replica
         customer_profiles_primary           → primary
    """
    for keyword in ("failover_replica", "read_replica", "reporting_replica",
                    "regional_", "primary", "inventory"):
        if keyword.replace("_", "") in table_name.replace("_", ""):
            return keyword.rstrip("_")
    return "unknown"


def _extract_json_values(text: str) -> list[str]:
    """
    Recursively extract all string leaf values from a JSON blob.
    Returns an empty list if text is not valid JSON.
    """
    try:
        obj = json.loads(text)
    except Exception:
        return []

    leaves = []

    def _walk(node: Any) -> None:
        if isinstance(node, dict):
            for v in node.values():
                _walk(v)
        elif isinstance(node, list):
            for v in node:
                _walk(v)
        elif node is not None:
            leaves.append(_normalise(str(node)))

    _walk(obj)
    return leaves


def _row_matches(row: sqlite3.Row, keys: list, all_ids: set) -> bool:
    """
    Return True if any raw column value OR any value inside a JSON blob
    column matches one of the subject's known identifiers.
    """
    for k in keys:
        raw = row[k]
        norm = _normalise(raw)
        # Direct column match
        if norm and norm in all_ids:
            return True
        # JSON blob match (for columns like record_json)
        if isinstance(raw, str) and raw.startswith("{"):
            if any(v in all_ids for v in _extract_json_values(raw) if v):
                return True
    return False


def _get_matching_detail(row: sqlite3.Row, keys: list, all_ids: set) -> str:
    """Build a short description of which fields matched."""
    parts = []
    for k in keys:
        raw = row[k]
        norm = _normalise(raw)
        if norm and norm in all_ids:
            parts.append(f"{k}={raw}")
        elif isinstance(raw, str) and raw.startswith("{"):
            hits = [v for v in _extract_json_values(raw) if v and v in all_ids]
            if hits:
                parts.append(f"{k}[json]={hits}")
    return ", ".join(parts)


def extract(sql_path: Path, identity: dict) -> list[dict]:
    """
    Load a .sql file into in-memory SQLite and search all tables for records
    that belong to the given identity.

    Returns a list of finding dicts:
    {
        'system_id':   str   — mapped from table name
        'resource_id': str   — the value in the first column (usually resource_id)
        'record_type': str   — data category (USER_PROFILE, SEARCH_INDEX_ENTRY, …)
        'state':       str   — 'PRESENT' (record found in snapshot)
        'topology':    str   — primary / failover_replica / read_replica / …
        'evidence_detail': str   — raw matching info for debug
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
        sql_text = sql_path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return findings

    # Load into in-memory SQLite
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    try:
        conn.executescript(sql_text)
    except Exception:
        conn.close()
        return findings

    # List all tables in this DB
    try:
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    except Exception:
        conn.close()
        return findings

    for table in tables:
        topology = _table_topology(table)

        # Determine data category from table name
        record_type = _infer_record_type(table)
        system_id   = _infer_system_id(table)

        try:
            rows = conn.execute(f'SELECT * FROM "{table}"').fetchall()
        except Exception:
            continue

        for row in rows:
            keys = row.keys()

            if _row_matches(row, keys, all_ids):
                resource_id = _pick_resource_id(row, keys)
                detail = _get_matching_detail(row, keys, all_ids)

                # Infer system_id and record_type from the record's own data
                # (for multi-collection tables like customer_data_primary)
                actual_system_id, actual_record_type = _infer_from_row(
                    row, keys, system_id, record_type)

                findings.append({
                    "system_id":       actual_system_id,
                    "resource_id":     resource_id,
                    "record_type":     actual_record_type,
                    "state":           "PRESENT",
                    "topology":        topology,
                    "table_name":      table,
                    "evidence_detail": detail,
                })

    conn.close()
    return findings


def _infer_from_row(row: sqlite3.Row, keys: list,
                    default_system_id: str, default_record_type: str) -> tuple[str, str]:
    """
    For tables that store multiple collections (e.g. customer_data_primary
    with origin_system and collection_name columns), use those fields to
    get a more precise system_id and record_type.
    """
    origin = _normalise(row["origin_system"]) if "origin_system" in keys else ""
    collection = _normalise(row["collection_name"]) if "collection_name" in keys else ""

    if origin:
        system_id = _map_origin_to_system_id(origin) or default_system_id
    else:
        system_id = default_system_id

    if collection:
        record_type = _map_collection_to_record_type(collection) or default_record_type
    else:
        record_type = default_record_type

    return system_id, record_type


def _map_origin_to_system_id(origin: str) -> str:
    mapping = {
        "account_service":   "account_service",
        "search_service":    "search_service",
        "analytics_platform": "analytics_platform",
        "support_platform":  "support_platform",
        "security_service":  "security_service",
        "export_service":    "export_service",
        "marketing_platform": "marketing_platform",
        "integration_service": "integration_service",
        "backup_service":    "backup_service",
    }
    for k, v in mapping.items():
        if k in origin:
            return v
    return ""


def _map_collection_to_record_type(collection: str) -> str:
    mapping = {
        "customer_profiles":       "USER_PROFILE",
        "customer_search_documents": "SEARCH_INDEX_ENTRY",
        "customer_analytics_reports": "ANALYTICS_PROFILE",
        "support_messages":        "SUPPORT_MESSAGE",
        "security_audit_events":   "SECURITY_AUDIT_LOG",
        "export_jobs":             "USER_EXPORT",
        "marketing_profiles":      "MARKETING_PROFILE",
        "account_tombstones":      "ACCOUNT_TOMBSTONE",
        "backup_catalog":          "BACKUP_ARCHIVE",
        "connector_configurations": "DATA_FLOW",
    }
    for k, v in mapping.items():
        if k in collection:
            return v
    return ""


def _pick_resource_id(row: sqlite3.Row, keys: list) -> str:
    """Extract the resource_id column, or fall back to the first column."""
    for candidate in ("resource_id", "id", "record_id"):
        if candidate in keys:
            return str(row[candidate])
    return str(row[keys[0]]) if keys else "unknown"


def _infer_record_type(table_name: str) -> str:
    """Map a table name to the closest deletion-rules data category."""
    t = table_name.lower()
    if "profile" in t and ("customer" in t or "account" in t):
        return "USER_PROFILE"
    if "search" in t or "index" in t:
        return "SEARCH_INDEX_ENTRY"
    if "analytic" in t:
        return "ANALYTICS_PROFILE"
    if "support" in t:
        return "SUPPORT_MESSAGE"
    if "audit" in t or "security" in t:
        return "SECURITY_AUDIT_LOG"
    if "export" in t:
        return "USER_EXPORT"
    if "marketing" in t:
        return "MARKETING_PROFILE"
    if "tombstone" in t:
        return "ACCOUNT_TOMBSTONE"
    if "backup" in t:
        return "BACKUP_ARCHIVE"
    if "connector" in t or "data_flow" in t or "integration" in t:
        return "DATA_FLOW"
    return "USER_PROFILE"  # safe default


def _infer_system_id(table_name: str) -> str:
    """Map a table name to a canonical system_id string."""
    t = table_name.lower()
    if "search" in t:
        return "search_service"
    if "analytic" in t:
        return "analytics_platform"
    if "support" in t:
        return "support_platform"
    if "audit" in t or "security" in t:
        return "security_service"
    if "export" in t:
        return "export_service"
    if "marketing" in t:
        return "marketing_platform"
    if "tombstone" in t:
        return "identity_service"
    if "backup" in t:
        return "backup_service"
    if "connector" in t or "integration" in t:
        return "integration_service"
    return "account_service"
