"""
step_builder.py — Construct ordered, compliant steps_json arrays.

Plain-English explanation:
  The problem statement specifies exact schemas, operations, and ordering rules:
  1. Phases must appear in this order:
     FINDING → REMEDIATION → VERIFICATION
  2. Within each phase, steps are sorted by:
     - Operation canonical rank (the order in problem_statement.md table)
     - system_id ascending
     - resource_id ascending
  3. Every step object contains:
     {
       "step_no": int,
       "phase": "FINDING" | "REMEDIATION" | "VERIFICATION",
       "system_id": str,
       "resource_id": str,
       "operation": str,
       "state": str,
       "evidence_id": str
     }
  4. Evidence citations:
     - COMPLETE cases: only VERIFICATION steps, each citing a real evidence ID.
     - INCOMPLETE cases: FINDING steps cite real evidence IDs; REMEDIATION and
       future VERIFICATION steps use evidence_id="".
     - NOT_APPLICABLE cases: steps_json=[].
"""

from typing import Optional
from config import (
    PHASE_FINDING,
    PHASE_REMEDIATION,
    PHASE_VERIFICATION,
    OP_TO_STATE,
    operation_rank,
)

# Canonical operation mapping per required action
_ACTION_TO_FINDING_OP = {
    "DELETE":    "REPORT_REMAINING_RECORD",
    "REDACT":    "REPORT_EXPOSED_PII",
    "ANONYMIZE": "REPORT_EXPOSED_PII",
    "DISABLE":   "REPORT_ACTIVE_DATA_FLOW",
    "BLOCK":     "REPORT_RESTORE_RISK",
}

_ACTION_TO_REMEDIATION_OP = {
    "DISABLE":   "DISABLE_DATA_FLOW",
    "BLOCK":     "BLOCK_RESTORE",
    "DELETE":    "DELETE_RECORD",
    "REDACT":    "REDACT_RECORD",
    "ANONYMIZE": "ANONYMIZE_RECORD",
}

_ACTION_TO_VERIFICATION_OP = {
    "DELETE":    "VERIFY_RECORD_ABSENT",
    "RETAIN":    "VERIFY_RECORD_PRESENT",
    "REDACT":    "VERIFY_RECORD_REDACTED",
    "ANONYMIZE": "VERIFY_RECORD_ANONYMIZED",
    "DISABLE":   "VERIFY_DATA_FLOW_DISABLED",
    "BLOCK":     "VERIFY_RESTORE_BLOCKED",
}


def _make_step(step_no: int, phase: str, system_id: str, resource_id: str,
               operation: str, evidence_id: str) -> dict:
    """Construct a single compliant step dictionary."""
    state = OP_TO_STATE.get(operation, "PRESENT")
    return {
        "step_no":     step_no,
        "phase":       phase,
        "system_id":   system_id,
        "resource_id": resource_id,
        "operation":   operation,
        "state":       state,
        "evidence_id": evidence_id or "",
    }


def _step_sort_key(step: dict) -> tuple:
    """
    Sort key enforcing canonical order:
    1. Phase: FINDING (0) -> REMEDIATION (1) -> VERIFICATION (2)
    2. Operation canonical rank (per specification table)
    3. system_id ascending
    4. resource_id ascending
    """
    phase_order = {
        PHASE_FINDING:      0,
        PHASE_REMEDIATION:  1,
        PHASE_VERIFICATION: 2,
    }.get(step["phase"], 9)

    op_rank = operation_rank(step["operation"])
    return (phase_order, op_rank, step["system_id"], step["resource_id"])


def build_complete_steps(decisions: list[dict]) -> list[dict]:
    """
    Build steps for a COMPLETE deletion case.
    Includes only evidence-backed VERIFICATION steps proving the compliant state.
    """
    raw_steps = []

    for d in decisions:
        action = d["required_action"]
        ver_op = _ACTION_TO_VERIFICATION_OP.get(action)
        if not ver_op:
            continue

        raw_steps.append({
            "phase":       PHASE_VERIFICATION,
            "system_id":   d["system_id"],
            "resource_id": d["resource_id"],
            "operation":   ver_op,
            "evidence_id": d.get("evidence_id", ""),
        })

    raw_steps.sort(key=_step_sort_key)

    return [
        _make_step(
            step_no=i + 1,
            phase=s["phase"],
            system_id=s["system_id"],
            resource_id=s["resource_id"],
            operation=s["operation"],
            evidence_id=s["evidence_id"],
        )
        for i, s in enumerate(raw_steps)
    ]


def build_incomplete_steps(decisions: list[dict]) -> list[dict]:
    """
    Build steps for an INCOMPLETE deletion case.
    Includes FINDING steps, REMEDIATION steps, and future VERIFICATION checks.
    """
    finding_steps = []
    remediation_steps = []
    verification_steps = []

    for d in decisions:
        action       = d["required_action"]
        is_compliant = d["is_compliant"]
        system_id    = d["system_id"]
        resource_id  = d["resource_id"]
        evidence_id  = d.get("evidence_id", "")

        find_op = _ACTION_TO_FINDING_OP.get(action)
        rem_op  = _ACTION_TO_REMEDIATION_OP.get(action)
        ver_op  = _ACTION_TO_VERIFICATION_OP.get(action)

        # 1. Findings: only for non-compliant resources (citing evidence)
        if not is_compliant and find_op:
            finding_steps.append({
                "phase":       PHASE_FINDING,
                "system_id":   system_id,
                "resource_id": resource_id,
                "operation":   find_op,
                "evidence_id": evidence_id,
            })

        # 2. Remediation: future action for non-compliant resources (empty evidence_id)
        if not is_compliant and rem_op:
            remediation_steps.append({
                "phase":       PHASE_REMEDIATION,
                "system_id":   system_id,
                "resource_id": resource_id,
                "operation":   rem_op,
                "evidence_id": "",
            })

        # 3. Verification: future post-remediation check (empty evidence_id)
        if ver_op:
            verification_steps.append({
                "phase":       PHASE_VERIFICATION,
                "system_id":   system_id,
                "resource_id": resource_id,
                "operation":   ver_op,
                "evidence_id": "",
            })

    finding_steps.sort(key=_step_sort_key)
    remediation_steps.sort(key=_step_sort_key)
    verification_steps.sort(key=_step_sort_key)

    all_raw = finding_steps + remediation_steps + verification_steps

    return [
        _make_step(
            step_no=i + 1,
            phase=s["phase"],
            system_id=s["system_id"],
            resource_id=s["resource_id"],
            operation=s["operation"],
            evidence_id=s["evidence_id"],
        )
        for i, s in enumerate(all_raw)
    ]


def build_steps_for_case(deletion_status: str, decisions: list[dict]) -> list[dict]:
    """Main entry point to build steps based on status."""
    if deletion_status == "NOT_APPLICABLE":
        return []
    elif deletion_status == "COMPLETE":
        return build_complete_steps(decisions)
    else:
        return build_incomplete_steps(decisions)
