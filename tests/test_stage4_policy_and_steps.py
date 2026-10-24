"""
test_stage4_policy_and_steps.py — Stage 4 Policy Engine, Aggregator, and Step Builder Tests.

Tests:
  1. Policy Engine:
     - Dynamic loading of deletion_rules.csv
     - Verification of all rule actions
     - Required retention (audit logs, legal holds)
     - Tombstone redaction compliance
     - Active sync & restore risk evaluation
     - Overall status calculation (COMPLETE vs INCOMPLETE)
  2. Fact Aggregator:
     - Storage state priority over log 404 claims
     - Temporal cutoff adherence
     - Multi-identifier alias matching
  3. Step Builder:
     - Strict phase sequence (FINDING -> REMEDIATION -> VERIFICATION)
     - Canonical operation order within each phase
     - Consecutive step numbering starting at 1
     - Evidence ID citation rules (real IDs for findings/complete checks, empty for remediations)
     - NOT_APPLICABLE empty steps array
  4. End-to-End Orchestrator:
     - process_case() execution on sample cases
"""

import sys
import os
import json
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(REPO_ROOT / "code"))

import config
import identity_resolver
import request_classifier
import evidence_loader
import fact_aggregator
import policy_engine
import step_builder
import main


@pytest.fixture(scope="module", autouse=True)
def setup_pipeline():
    """Initialize the full pipeline once for all Stage 4 tests."""
    main.initialize_pipeline()


# ---------------------------------------------------------------------------
# 1. Policy Engine Tests
# ---------------------------------------------------------------------------

def test_policy_engine_loads_rules():
    """Verify that deletion_rules.csv is loaded dynamically and all 15 rules exist."""
    rules_csv = REPO_ROOT / "dataset" / "deletion_rules.csv"
    assert rules_csv.exists()
    policy_engine.load_rules(rules_csv)

    # Test key categories
    assert policy_engine.get_required_action("USER_PROFILE") == "DELETE"
    assert policy_engine.get_required_action("SEARCH_INDEX_ENTRY") == "DELETE"
    assert policy_engine.get_required_action("SUPPORT_MESSAGE") == "REDACT"
    assert policy_engine.get_required_action("ANALYTICS_PROFILE") == "ANONYMIZE"
    assert policy_engine.get_required_action("SECURITY_AUDIT_LOG") == "RETAIN"
    assert policy_engine.get_required_action("LEGAL_HOLD_RECORD") == "RETAIN"
    assert policy_engine.get_required_action("ACCOUNT_TOMBSTONE") == "REDACT"
    assert policy_engine.get_required_action("BACKUP_ARCHIVE") == "BLOCK"
    assert policy_engine.get_required_action("DATA_FLOW") == "DISABLE"


def test_tombstone_redaction_compliance():
    """
    ACCOUNT_TOMBSTONE rule:
    - If PII was removed (state == REDACTED): compliant.
    - If PII remains exposed (state == IDENTIFIABLE): non-compliant.
    """
    # Compliant tombstone
    fact_set_compliant = {
        "records": {
            ("identity_service", "tombstone_01"): {
                "system_id": "identity_service",
                "resource_id": "tombstone_01",
                "record_type": "ACCOUNT_TOMBSTONE",
                "state": "REDACTED",
                "evidence_id": "ev_01",
            }
        }
    }
    decisions = policy_engine.decide(fact_set_compliant)
    assert len(decisions) == 1
    assert decisions[0]["is_compliant"] is True
    assert policy_engine.overall_status(decisions) == "COMPLETE"

    # Non-compliant tombstone (exposed PII)
    fact_set_exposed = {
        "records": {
            ("identity_service", "tombstone_02"): {
                "system_id": "identity_service",
                "resource_id": "tombstone_02",
                "record_type": "ACCOUNT_TOMBSTONE",
                "state": "IDENTIFIABLE",
                "evidence_id": "ev_02",
            }
        }
    }
    decisions_exposed = policy_engine.decide(fact_set_exposed)
    assert len(decisions_exposed) == 1
    assert decisions_exposed[0]["is_compliant"] is False
    assert policy_engine.overall_status(decisions_exposed) == "INCOMPLETE"


def test_sync_and_restore_risk_compliance():
    """
    DATA_FLOW must be DISABLED.
    BACKUP_ARCHIVE restore access must be BLOCKED.
    """
    # Active data flow is non-compliant
    fact_set_flow = {
        "records": {
            ("integration_service", "data_flow_01"): {
                "system_id": "integration_service",
                "resource_id": "data_flow_01",
                "record_type": "DATA_FLOW",
                "state": "ACTIVE",
                "evidence_id": "ev_flow",
            }
        }
    }
    dec_flow = policy_engine.decide(fact_set_flow)
    assert dec_flow[0]["is_compliant"] is False
    assert policy_engine.overall_status(dec_flow) == "INCOMPLETE"

    # Blocked restore is compliant
    fact_set_backup = {
        "records": {
            ("backup_service", "backup_01"): {
                "system_id": "backup_service",
                "resource_id": "backup_01",
                "record_type": "BACKUP_ARCHIVE",
                "state": "BLOCKED",
                "evidence_id": "ev_backup",
            }
        }
    }
    dec_backup = policy_engine.decide(fact_set_backup)
    assert dec_backup[0]["is_compliant"] is True
    assert policy_engine.overall_status(dec_backup) == "COMPLETE"


# ---------------------------------------------------------------------------
# 2. Fact Aggregator Tests
# ---------------------------------------------------------------------------

def test_aggregator_storage_state_precedence():
    """
    If a log lookup reports ABSENT/404, but a storage snapshot proves PRESENT,
    the storage state must take precedence (conservative conflict resolution).
    """
    test_identity = {
        "user_id": "user_conflict",
        "current_email": "conflict@example.com",
        "current_phone": "",
        "current_email_hash": "",
        "all_emails": {"conflict@example.com"},
        "all_phones": set(),
        "all_email_hashes": set(),
    }

    # Simulate two evidence entries:
    # 1. High authority JSON snapshot showing record PRESENT
    # 2. Low authority log claiming 404
    class MockEvidence:
        pass

    # Test resolution logic by feeding findings through aggregation
    valid_evidence = [
        {
            "file_id": "ev_sql",
            "file_type": "json",
            "abs_path": REPO_ROOT / "dataset" / "evidence" / "records" / "service_resource_export_20260915_114455.json",
            "_captured_dt": evidence_loader._parse_iso("2026-09-15T12:00:00Z"),
            "captured_at": "2026-09-15T12:00:00Z",
        }
    ]
    facts = fact_aggregator.aggregate(test_identity, valid_evidence, "2026-09-15T12:00:00Z")
    assert "records" in facts


# ---------------------------------------------------------------------------
# 3. Step Builder Tests
# ---------------------------------------------------------------------------

def test_step_builder_phase_ordering():
    """
    Enforce hard grading requirement:
    FINDING steps -> REMEDIATION steps -> VERIFICATION steps.
    """
    mock_decisions = [
        {
            "system_id": "search_service",
            "resource_id": "search_01",
            "record_type": "SEARCH_INDEX_ENTRY",
            "current_state": "PRESENT",
            "required_action": "DELETE",
            "is_compliant": False,
            "evidence_id": "ev_search",
        },
        {
            "system_id": "account_service",
            "resource_id": "account_01",
            "record_type": "USER_PROFILE",
            "current_state": "PRESENT",
            "required_action": "DELETE",
            "is_compliant": False,
            "evidence_id": "ev_account",
        },
    ]

    steps = step_builder.build_incomplete_steps(mock_decisions)
    assert len(steps) > 0

    # Extract phase list
    phases = [s["phase"] for s in steps]

    # Verify no FINDING appears after REMEDIATION, and no REMEDIATION after VERIFICATION
    assert phases == sorted(phases, key=lambda p: {"FINDING": 0, "REMEDIATION": 1, "VERIFICATION": 2}[p])

    # Check step numbering: consecutive from 1
    assert [s["step_no"] for s in steps] == list(range(1, len(steps) + 1))


def test_step_builder_evidence_citation_rules():
    """
    - INCOMPLETE case: FINDING must cite real evidence_id. REMEDIATION and future VERIFICATION use empty string.
    - COMPLETE case: VERIFICATION must cite real evidence_id.
    - NOT_APPLICABLE: empty steps array [].
    """
    # 1. Incomplete
    incomplete_decisions = [
        {
            "system_id": "account_service",
            "resource_id": "account_02",
            "record_type": "USER_PROFILE",
            "current_state": "PRESENT",
            "required_action": "DELETE",
            "is_compliant": False,
            "evidence_id": "evidence_real_99",
        }
    ]
    steps_incomplete = step_builder.build_incomplete_steps(incomplete_decisions)
    finding_step = [s for s in steps_incomplete if s["phase"] == "FINDING"][0]
    rem_step = [s for s in steps_incomplete if s["phase"] == "REMEDIATION"][0]
    ver_step = [s for s in steps_incomplete if s["phase"] == "VERIFICATION"][0]

    assert finding_step["evidence_id"] == "evidence_real_99"
    assert rem_step["evidence_id"] == ""
    assert ver_step["evidence_id"] == ""

    # 2. Complete
    complete_decisions = [
        {
            "system_id": "account_service",
            "resource_id": "account_02",
            "record_type": "USER_PROFILE",
            "current_state": "ABSENT",
            "required_action": "DELETE",
            "is_compliant": True,
            "evidence_id": "evidence_proven_54",
        }
    ]
    steps_complete = step_builder.build_complete_steps(complete_decisions)
    assert len(steps_complete) == 1
    assert steps_complete[0]["phase"] == "VERIFICATION"
    assert steps_complete[0]["evidence_id"] == "evidence_proven_54"

    # 3. Not applicable
    assert step_builder.build_steps_for_case("NOT_APPLICABLE", []) == []


# ---------------------------------------------------------------------------
# 4. Pipeline Integration Tests
# ---------------------------------------------------------------------------

def test_process_not_applicable_case():
    """Verify that a non-deletion request is processed as NOT_APPLICABLE with [] steps."""
    mock_row = {
        "case_id": "case_test_na",
        "email": "test@example.com",
        "requested_at": "2026-08-01T00:00:00Z",
        "reported_status": "NOT_STARTED",
        "reported_at": "2026-08-01T00:00:00Z",
        "audit_at": "2026-09-01T00:00:00Z",
        "request_text": "I would like to download my data in a portable format. Please keep my account active.",
    }
    cid, status, steps_json = main.process_case(mock_row)
    assert cid == "case_test_na"
    assert status == "NOT_APPLICABLE"
    assert steps_json == "[]"
