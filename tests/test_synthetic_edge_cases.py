"""
test_synthetic_edge_cases.py — Required Participant Synthetic Edge Cases.

These tests are custom, hand-crafted evaluation cases created to stress-test
the deletion-audit agent on distinct privacy and compliance risks:

Edge Case 1: Non-deletion Request (Portability / Export without Deletion)
  - Risk: Mistaking a data access or portability request for a deletion request.
  - Required Outcome: deletion_status="NOT_APPLICABLE", steps_json=[].

Edge Case 2: Historical Identifier Alias (Identity Drift)
  - Risk: Subject files a deletion request using an old, superseded email address.
    Primary database was wiped, but an uncleaned replica/document still references
    the historical alias.
  - Required Outcome: Identity resolved via user_audit_log, uncleaned alias flagged
    as INCOMPLETE with REPORT_REMAINING_RECORD.

Edge Case 3: Appears Deleted but Active Restore Risk Exists (Ghost Restore Risk)
  - Risk: The primary profile is verified ABSENT, but a backup archive has
    restore_allowed=True, allowing deleted data to be resurrected during disaster recovery.
  - Required Outcome: Marked INCOMPLETE with REPORT_RESTORE_RISK, remediation includes
    BLOCK_RESTORE before dependent verifications.
"""

import sys
import os
import json
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(REPO_ROOT / "code"))

import main
import config
import identity_resolver
import request_classifier
import policy_engine
import step_builder


@pytest.fixture(scope="module", autouse=True)
def init_system():
    main.initialize_pipeline()


# ---------------------------------------------------------------------------
# Synthetic Edge Case 1: Non-Deletion Request
# ---------------------------------------------------------------------------

def test_synthetic_edge_case_1_non_deletion():
    """
    Edge Case 1: The user requests a GDPR Article 20 data export / download in
    portable format and explicitly requests to keep their account active.
    Must evaluate to NOT_APPLICABLE with empty steps array.
    """
    synthetic_case = {
        "case_id": "case_synthetic_01",
        "email": "customer.portable@example.com",
        "requested_at": "2026-09-01T10:00:00Z",
        "reported_status": "NOT_STARTED",
        "reported_at": "2026-09-01T10:00:00Z",
        "audit_at": "2026-09-05T12:00:00Z",
        "request_text": (
            "I'd like to download my account information in a portable format. "
            "Please keep the account as it is, do not delete or close anything."
        ),
    }

    cid, status, steps_json = main.process_case(synthetic_case)
    assert cid == "case_synthetic_01"
    assert status == "NOT_APPLICABLE"
    assert steps_json == "[]"
    assert json.loads(steps_json) == []


# ---------------------------------------------------------------------------
# Synthetic Edge Case 2: Historical Identifier Drift
# ---------------------------------------------------------------------------

def test_synthetic_edge_case_2_historical_identifier():
    """
    Edge Case 2: Deletion requested under an old email that exists in user_audit_log.
    A record in an external search index or replica still holds that historical email.
    The system must link the historical alias to the canonical identity and flag
    the exposed record.
    """
    # Use real user_10 who changed email from nadia.ionescu@yahoo.com to n.petrescu@yahoo.com
    user_identity = identity_resolver.resolve("nadia.ionescu@yahoo.com")
    assert user_identity is not None
    assert "nadia.ionescu@yahoo.com" in user_identity["all_emails"]
    assert "n.petrescu@yahoo.com" in user_identity["all_emails"]

    # Simulate fact set where an old search index entry still has the historical email
    fact_set = {
        "records": {
            ("account_service", "account_10"): {
                "system_id": "account_service",
                "resource_id": "account_10",
                "record_type": "USER_PROFILE",
                "state": "ABSENT",
                "evidence_id": "ev_db_snapshot",
            },
            ("search_service", "search_old_alias_10"): {
                "system_id": "search_service",
                "resource_id": "search_old_alias_10",
                "record_type": "SEARCH_INDEX_ENTRY",
                "state": "PRESENT",
                "evidence_id": "ev_search_dump",
            },
        }
    }

    decisions = policy_engine.decide(fact_set)
    status = policy_engine.overall_status(decisions)
    assert status == "INCOMPLETE"

    steps = step_builder.build_steps_for_case(status, decisions)
    assert len(steps) > 0

    # Must contain a FINDING for the remaining search index entry citing ev_search_dump
    finding = [s for s in steps if s["phase"] == "FINDING" and s["system_id"] == "search_service"][0]
    assert finding["operation"] == "REPORT_REMAINING_RECORD"
    assert finding["evidence_id"] == "ev_search_dump"

    # Remediation must propose DELETE_RECORD with empty evidence_id
    remediation = [s for s in steps if s["phase"] == "REMEDIATION" and s["system_id"] == "search_service"][0]
    assert remediation["operation"] == "DELETE_RECORD"
    assert remediation["evidence_id"] == ""


# ---------------------------------------------------------------------------
# Synthetic Edge Case 3: Appears Deleted but Active Restore Risk Exists
# ---------------------------------------------------------------------------

def test_synthetic_edge_case_3_restore_risk():
    """
    Edge Case 3: Primary profile is verified ABSENT in database replicas,
    but a backup archive exists with restore_allowed=True.
    A simple inspection might claim COMPLETE, but policy requires blocking restore access.
    The agent must identify this as INCOMPLETE, report REPORT_RESTORE_RISK, and propose BLOCK_RESTORE.
    """
    fact_set = {
        "records": {
            ("account_service", "account_33"): {
                "system_id": "account_service",
                "resource_id": "account_33",
                "record_type": "USER_PROFILE",
                "state": "ABSENT",
                "evidence_id": "ev_db_snapshot_clean",
            },
            ("backup_service", "backup_archive_33"): {
                "system_id": "backup_service",
                "resource_id": "backup_archive_33",
                "record_type": "BACKUP_ARCHIVE",
                "state": "ACTIVE",
                "evidence_id": "ev_backup_console",
            },
        }
    }

    decisions = policy_engine.decide(fact_set)
    status = policy_engine.overall_status(decisions)
    assert status == "INCOMPLETE"

    steps = step_builder.build_steps_for_case(status, decisions)

    # 1. Finding must be REPORT_RESTORE_RISK citing ev_backup_console
    finding = [s for s in steps if s["phase"] == "FINDING"][0]
    assert finding["operation"] == "REPORT_RESTORE_RISK"
    assert finding["state"] == "ACTIVE"
    assert finding["evidence_id"] == "ev_backup_console"

    # 2. Remediation must be BLOCK_RESTORE
    remediation = [s for s in steps if s["phase"] == "REMEDIATION"][0]
    assert remediation["operation"] == "BLOCK_RESTORE"
    assert remediation["state"] == "BLOCKED"
    assert remediation["evidence_id"] == ""

    # 3. Verification must include VERIFY_RESTORE_BLOCKED
    verification = [s for s in steps if s["phase"] == "VERIFICATION" and s["system_id"] == "backup_service"][0]
    assert verification["operation"] == "VERIFY_RESTORE_BLOCKED"
    assert verification["state"] == "BLOCKED"
    assert verification["evidence_id"] == ""
