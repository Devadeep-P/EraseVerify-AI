"""
policy_engine.py — Apply deletion rules to each discovered record.

Plain-English explanation:
  Once all evidence facts are aggregated for a user, the policy engine asks:
  "What does our deletion policy (deletion_rules.csv) require for this record?"

  The policy defines:
  - DELETE: Entire record must be absent.
  - REDACT: Record may remain, but PII (name, email, phone, email hash) must be stripped.
  - ANONYMIZE: Attributable user links must be severed.
  - RETAIN: Record must be kept (e.g. security audit logs, active legal holds).
  - DISABLE: Data flows/connectors that can recreate data must be stopped.
  - BLOCK: Backup restore access must be blocked.

  Decisions are completely dynamic and explainable based on the evidence facts
  and applicable rules.
"""

import csv
from pathlib import Path
from typing import Optional

# Action constants
ACTION_DELETE    = "DELETE"
ACTION_REDACT    = "REDACT"
ACTION_ANONYMIZE = "ANONYMIZE"
ACTION_RETAIN    = "RETAIN"
ACTION_DISABLE   = "DISABLE"
ACTION_BLOCK     = "BLOCK"

_rules_cache: dict[str, dict] = {}


def load_rules(rules_csv: Path) -> None:
    """Load deletion_rules.csv into memory."""
    global _rules_cache
    _rules_cache = {}
    with open(rules_csv, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            cat = row["data_category"].strip().upper()
            _rules_cache[cat] = row


def get_required_action(record_type: str) -> str:
    """Return the policy-required action for a given record type / data category."""
    rt = record_type.strip().upper()
    if rt == "DATA_FLOW":
        return ACTION_DISABLE
    if rt == "BACKUP_ARCHIVE":
        return ACTION_BLOCK
    if rt in _rules_cache:
        return _rules_cache[rt]["required_action"].strip().upper()

    # Defaults matching standard policy rules
    fallback_map = {
        "USER_PROFILE":         ACTION_DELETE,
        "SECONDARY_IDENTIFIER": ACTION_DELETE,
        "SEARCH_INDEX_ENTRY":   ACTION_DELETE,
        "CACHE_ENTRY":          ACTION_DELETE,
        "SUPPORT_MESSAGE":      ACTION_REDACT,
        "SUPPORT_ATTACHMENT":   ACTION_DELETE,
        "ANALYTICS_PROFILE":    ACTION_ANONYMIZE,
        "PRODUCT_TELEMETRY":    ACTION_ANONYMIZE,
        "USER_EXPORT":          ACTION_DELETE,
        "MARKETING_PROFILE":    ACTION_DELETE,
        "EMAIL_DELIVERY_LOG":   ACTION_REDACT,
        "SECURITY_AUDIT_LOG":   ACTION_RETAIN,
        "LEGAL_HOLD_RECORD":    ACTION_RETAIN,
        "BACKUP_ARCHIVE":       ACTION_BLOCK,
        "ACCOUNT_TOMBSTONE":    ACTION_REDACT,
    }
    return fallback_map.get(rt, ACTION_DELETE)


def decide(fact_set: dict) -> list[dict]:
    """
    Apply deletion policy to every record in fact_set['records'].

    Returns a list of decision dicts:
    {
        'system_id':       str
        'resource_id':     str
        'record_type':     str
        'current_state':   str   — observed evidence state
        'required_action': str   — DELETE | REDACT | ANONYMIZE | RETAIN | DISABLE | BLOCK
        'is_compliant':    bool  — True if observed state satisfies required action
        'evidence_id':     str   — file_id establishing current state
        'explanation':     str   — plain-English rationale
    }
    """
    decisions = []

    for (system_id, resource_id), record in fact_set.get("records", {}).items():
        record_type   = record.get("record_type", "USER_PROFILE")
        current_state = record.get("state", "PRESENT")
        evidence_id   = record.get("evidence_id", "")
        required_act  = get_required_action(record_type)

        is_compliant, explanation = _evaluate_compliance(record_type, current_state, required_act)

        decisions.append({
            "system_id":       system_id,
            "resource_id":     resource_id,
            "record_type":     record_type,
            "current_state":   current_state,
            "required_action": required_act,
            "is_compliant":    is_compliant,
            "evidence_id":     evidence_id,
            "explanation":     explanation,
        })

    return decisions


def _evaluate_compliance(record_type: str, current_state: str, required_action: str) -> tuple[bool, str]:
    """Check compliance and generate a plain-English explanation."""
    state = current_state.upper()

    if required_action == ACTION_DELETE:
        if state == "ABSENT":
            return True, f"{record_type} was successfully deleted."
        return False, f"{record_type} is still {state}; policy requires full deletion."

    elif required_action == ACTION_REDACT:
        if state == "REDACTED":
            return True, f"{record_type} has personal identifiers properly redacted."
        return False, f"{record_type} is {state}; personal data remains exposed."

    elif required_action == ACTION_ANONYMIZE:
        if state in ("ANONYMIZED", "ABSENT"):
            return True, f"{record_type} is anonymized and no longer attributable."
        return False, f"{record_type} is {state}; identifiable links still exist."

    elif required_action == ACTION_RETAIN:
        if state == "PRESENT":
            return True, f"{record_type} is retained as legally/operationally required."
        return False, f"{record_type} is {state}; required retention record is missing."

    elif required_action == ACTION_DISABLE:
        if state in ("DISABLED", "ABSENT"):
            return True, "Data flow connector is disabled."
        return False, f"Data flow connector is {state}; can sync or recreate data."

    elif required_action == ACTION_BLOCK:
        if state == "BLOCKED":
            return True, "Backup archive restore access is blocked."
        return False, f"Backup archive restore is {state}; risk of restoring deleted data."

    return False, f"Unknown compliance state for {record_type} with action {required_action}."


def overall_status(decisions: list[dict]) -> str:
    """Return COMPLETE if every decision is compliant, otherwise INCOMPLETE."""
    if not decisions:
        return "INCOMPLETE"

    for d in decisions:
        if not d["is_compliant"]:
            return "INCOMPLETE"

    return "COMPLETE"
