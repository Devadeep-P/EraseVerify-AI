"""
test_stage3_extractors.py — Unit and integration tests for all 6 evidence extractors.

Tests:
  1. sql_extractor: SQLite in-memory execution, topology detection, replication drift.
  2. json_extractor: parsing snapshot bundles, service resource exports, connector configs.
  3. log_extractor: structured key=value parsing, temporal cutoff (audit_at), status codes.
  4. text_extractor: pipe-delimited format parsing, status mapping.
  5. pdf_extractor: pdfplumber text extraction on actual PDF evidence files.
  6. image_extractor: graceful execution and OCR interface validation on PNG files.
"""

import sys
import os
import sqlite3
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(REPO_ROOT / "code"))

import identity_resolver
from evidence_extractors import (
    sql_extractor,
    json_extractor,
    log_extractor,
    text_extractor,
    pdf_extractor,
    image_extractor
)


@pytest.fixture(scope="module", autouse=True)
def setup_tables():
    """Load user identity tables once for extractor testing."""
    identities_csv = REPO_ROOT / "dataset" / "user_identities.csv"
    audit_log_csv = REPO_ROOT / "dataset" / "user_audit_log.csv"
    identity_resolver.load_tables(identities_csv, audit_log_csv)


# ---------------------------------------------------------------------------
# 1. SQL Extractor Tests
# ---------------------------------------------------------------------------

def test_sql_extractor_on_real_evidence():
    """Test SQL extractor on actual evidence SQL files in dataset/evidence/databases/."""
    sql_files = list((REPO_ROOT / "dataset" / "evidence" / "databases").glob("*.sql"))
    assert len(sql_files) > 0, "Expected at least one SQL evidence file"

    # Test with a mock identity that we inject into a temporary in-memory snapshot
    test_identity = {
        "user_id": "user_test_99",
        "current_email": "test.user@example.com",
        "current_phone": "+1 555 0199",
        "current_email_hash": "hash99",
        "all_emails": {"test.user@example.com", "old.test@example.com"},
        "all_phones": {"+1 555 0199"},
        "all_email_hashes": {"hash99"},
    }

    # Test real file execution
    real_sql = sql_files[0]
    res = sql_extractor.extract(real_sql, test_identity)
    assert isinstance(res, list)


def test_sql_extractor_replication_drift():
    """
    Simulate replication drift: primary table does not have the record (deleted),
    but failover replica STILL contains the record.
    The extractor must identify the record in the replica table as PRESENT.
    """
    test_identity = {
        "user_id": "user_drift_01",
        "current_email": "drift.user@example.com",
        "current_phone": "+1 555 1234",
        "current_email_hash": "hash_drift",
        "all_emails": {"drift.user@example.com"},
        "all_phones": {"+1 555 1234"},
        "all_email_hashes": {"hash_drift"},
    }

    # Create synthetic SQL representing primary (empty) and failover_replica (has ghost data)
    synthetic_sql = """
    CREATE TABLE customer_profiles_primary (
        resource_id TEXT PRIMARY KEY, user_id TEXT, email TEXT
    );
    CREATE TABLE customer_profiles_failover_replica (
        resource_id TEXT PRIMARY KEY, user_id TEXT, email TEXT
    );
    INSERT INTO customer_profiles_failover_replica VALUES ('account_drift_99', 'user_drift_01', 'drift.user@example.com');
    """
    tmp_path = REPO_ROOT / "tests" / "temp_drift_test.sql"
    tmp_path.write_text(synthetic_sql, encoding="utf-8")

    try:
        findings = sql_extractor.extract(tmp_path, test_identity)
        assert len(findings) == 1
        finding = findings[0]
        assert finding["resource_id"] == "account_drift_99"
        assert finding["state"] == "PRESENT"
        assert finding["topology"] == "failover_replica"
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


# ---------------------------------------------------------------------------
# 2. JSON Extractor Tests
# ---------------------------------------------------------------------------

def test_json_extractor_service_exports():
    """Test JSON extractor parsing service_resource_export_*.json."""
    export_files = list((REPO_ROOT / "dataset" / "evidence" / "records").glob("service_resource_export_*.json"))
    assert len(export_files) > 0

    # User 24 in sample_output.csv has exposed account_5334 in evidence_92
    identity_24 = identity_resolver.resolve("keiko.nakamura@gmail.com")
    assert identity_24 is not None

    evidence_92_path = REPO_ROOT / "dataset" / "evidence" / "records" / "service_resource_export_20260915_114455.json"
    if evidence_92_path.exists():
        findings = json_extractor.extract(evidence_92_path, identity_24)
        assert any(f["resource_id"] == "account_5334" and f["state"] == "PRESENT" for f in findings)


def test_json_extractor_tombstone_redaction():
    """
    Test JSON extractor on customer_data_snapshot_bundle_20260915.json.
    Verifies that tombstone_440 (all PII null) is REDACTED,
    while tombstone_9178 (name/phone present) is IDENTIFIABLE (exposed PII).
    """
    bundle_path = REPO_ROOT / "dataset" / "evidence" / "records" / "customer_data_snapshot_bundle_20260915.json"
    assert bundle_path.exists()

    # User 541 (case_31)
    user_541 = identity_resolver.resolve("a.eze08@gmail.com")
    assert user_541 is not None
    findings_541 = json_extractor.extract(bundle_path, user_541)
    tombstone_541 = [f for f in findings_541 if f["record_type"] == "ACCOUNT_TOMBSTONE"]
    assert len(tombstone_541) == 1
    assert tombstone_541[0]["state"] == "REDACTED"

    # User 542 (case_32)
    user_542 = identity_resolver.resolve("addo.kofi@gmail.com")
    findings_542 = json_extractor.extract(bundle_path, user_542)
    tombstone_542 = [f for f in findings_542 if f["record_type"] == "ACCOUNT_TOMBSTONE"]
    assert len(tombstone_542) == 1
    assert tombstone_542[0]["state"] == "IDENTIFIABLE"


# ---------------------------------------------------------------------------
# 3. Log Extractor Tests
# ---------------------------------------------------------------------------

def test_log_extractor_temporal_filter():
    """
    Verify that log events occurring AFTER audit_at are strictly ignored,
    while events at or before audit_at are processed.
    """
    test_identity = {
        "user_id": "user_log_test",
        "all_emails": {"log.user@example.com"},
        "all_phones": set(),
        "all_email_hashes": set(),
    }

    synthetic_log = """
    2026-08-01T10:00:00Z level=INFO service=account_service event=profile_lookup_completed resource_id=account_early email=log.user@example.com rows=1 http_status=200
    2026-08-10T10:00:00Z level=INFO service=account_service event=profile_lookup_completed resource_id=account_late email=log.user@example.com rows=0 http_status=404
    """
    tmp_path = REPO_ROOT / "tests" / "temp_temporal_test.log"
    tmp_path.write_text(synthetic_log, encoding="utf-8")

    try:
        # Cutoff at 2026-08-05: should only include account_early
        findings = log_extractor.extract(tmp_path, test_identity, audit_at="2026-08-05T00:00:00Z")
        assert len(findings) == 1
        assert findings[0]["resource_id"] == "account_early"
        assert findings[0]["state"] == "PRESENT"

        # Cutoff at 2026-08-15: should include both
        findings_all = log_extractor.extract(tmp_path, test_identity, audit_at="2026-08-15T00:00:00Z")
        assert len(findings_all) == 2
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


def test_log_extractor_data_flow_and_restore_events():
    """Test log extractor identifying active/disabled data flows and restore risks."""
    test_identity = {
        "user_id": "user_flow_test",
        "all_emails": {"flow.user@example.com"},
        "all_phones": set(),
        "all_email_hashes": set(),
    }

    synthetic_log = """
    2026-08-01T10:00:00Z service=integration_service event=connector_config_read_completed resource_id=data_flow_01 email=flow.user@example.com enabled=true last_delivery_status=delivered
    2026-08-01T10:05:00Z service=backup_service event=restore_policy_read_completed resource_id=backup_01 email=flow.user@example.com restore_allowed=true
    """
    tmp_path = REPO_ROOT / "tests" / "temp_flow_test.log"
    tmp_path.write_text(synthetic_log, encoding="utf-8")

    try:
        findings = log_extractor.extract(tmp_path, test_identity, audit_at="2026-08-05T00:00:00Z")
        assert len(findings) == 2
        f_map = {f["resource_id"]: f for f in findings}
        assert f_map["data_flow_01"]["state"] == "ACTIVE"
        assert f_map["backup_01"]["state"] == "ACTIVE"
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


# ---------------------------------------------------------------------------
# 4. Text Extractor Tests
# ---------------------------------------------------------------------------

def test_text_extractor_pipe_delimited_parsing():
    """Test parsing pipe-delimited handover files in dataset/evidence/records/."""
    txt_files = list((REPO_ROOT / "dataset" / "evidence" / "records").glob("*.txt"))
    assert len(txt_files) > 0

    test_identity = {
        "user_id": "user_txt_test",
        "all_emails": {"txt.user@example.com"},
        "all_phones": set(),
        "all_email_hashes": set(),
    }

    synthetic_txt = """
    # Handover report
    2026-10-01T12:00:00Z | account_service | account_777 | USER_PROFILE | found | txt.user@example.com
    2026-10-01T12:00:00Z | backup_service | backup_888 | BACKUP_ARCHIVE | blocked | txt.user@example.com
    """
    tmp_path = REPO_ROOT / "tests" / "temp_handover_test.txt"
    tmp_path.write_text(synthetic_txt, encoding="utf-8")

    try:
        findings = text_extractor.extract(tmp_path, test_identity)
        assert len(findings) == 2
        f_map = {f["resource_id"]: f for f in findings}
        assert f_map["account_777"]["state"] == "PRESENT"
        assert f_map["backup_888"]["state"] == "BLOCKED"
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


# ---------------------------------------------------------------------------
# 5. PDF Extractor Tests
# ---------------------------------------------------------------------------

def test_pdf_extractor_real_pdf_files():
    """Test PDF text extraction with pdfplumber on actual PDF files in dataset/evidence/documents/."""
    pdf_files = list((REPO_ROOT / "dataset" / "evidence" / "documents").glob("*.pdf"))
    assert len(pdf_files) > 0

    test_identity = {
        "user_id": "user_pdf_nonexistent",
        "all_emails": {"nonexistent_pdf_user@example.com"},
        "all_phones": set(),
        "all_email_hashes": set(),
    }

    # Running on actual PDF file should execute without exception
    res = pdf_extractor.extract(pdf_files[0], test_identity)
    assert isinstance(res, list)


# ---------------------------------------------------------------------------
# 6. Image Extractor Tests
# ---------------------------------------------------------------------------

def test_image_extractor_interface_and_graceful_handling():
    """Test image extractor runs without crashing on actual PNG screenshot evidence."""
    img_files = list((REPO_ROOT / "dataset" / "evidence" / "images").glob("*.png"))
    assert len(img_files) > 0

    test_identity = {
        "user_id": "user_img_test",
        "all_emails": {"img.test@example.com"},
        "all_phones": set(),
        "all_email_hashes": set(),
    }

    # Running on actual PNG file returns a list (graceful fallback when OCR binary not installed)
    res = image_extractor.extract(img_files[0], test_identity)
    assert isinstance(res, list)
