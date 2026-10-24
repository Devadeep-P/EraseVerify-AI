"""
test_stage2.py — Stage 2 Foundation Tests for Ghost Data Still Exists.

Tests:
  1. Identity Resolution (identity_resolver.py)
     - Load tables from actual project dataset
     - Resolve current emails
     - Resolve historical emails from audit log
     - Confirm all sample deletion requests resolve to a user
     - Validate identity matching logic
     - Test edge cases (unknown user, case insensitivity, whitespace)

  2. Request Classification (request_classifier.py)
     - Validate genuine deletion requests across languages (English, Spanish, French, Japanese, Korean, etc.)
     - Validate that all public sample requests authorize deletion
     - Validate non-deletion intents (access, export, rectification, opt-out, explicit retention) are NOT_APPLICABLE
     - Test empty/whitespace inputs
"""

import sys
import os
import csv
from pathlib import Path
import pytest

# Add code/ to python search path
REPO_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(REPO_ROOT / "code"))

import identity_resolver
import request_classifier


@pytest.fixture(scope="module", autouse=True)
def setup_tables():
    """Load dataset tables once for all tests in this module."""
    identities_csv = REPO_ROOT / "dataset" / "user_identities.csv"
    audit_log_csv = REPO_ROOT / "dataset" / "user_audit_log.csv"
    assert identities_csv.exists(), f"Missing dataset file: {identities_csv}"
    assert audit_log_csv.exists(), f"Missing dataset file: {audit_log_csv}"
    identity_resolver.load_tables(identities_csv, audit_log_csv)


# ---------------------------------------------------------------------------
# 1. Identity Resolver Tests
# ---------------------------------------------------------------------------

def test_identity_resolution_sample_requests():
    """
    Every deletion request in sample_deletion_requests.csv must resolve to a valid user_id.
    Ensures zero unresolved users among the public sample set.
    """
    sample_csv = REPO_ROOT / "dataset" / "sample_deletion_requests.csv"
    assert sample_csv.exists()

    with open(sample_csv, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            email = row["email"]
            resolved = identity_resolver.resolve(email)
            assert resolved is not None, f"Failed to resolve email: {email} (Case {row['case_id']})"
            assert "user_id" in resolved and resolved["user_id"].startswith("user_")
            assert "all_emails" in resolved and len(resolved["all_emails"]) >= 1
            assert "all_phones" in resolved
            assert "all_email_hashes" in resolved
            assert "audit_ids" in resolved


def test_historical_identity_resolution():
    """
    Test that an email recorded only in user_audit_log.csv (as old_value)
    correctly resolves to the same user and includes both old and current emails.
    """
    audit_log_csv = REPO_ROOT / "dataset" / "user_audit_log.csv"
    with open(audit_log_csv, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        historical_row = None
        for r in reader:
            if r["field_name"] == "email" and r["old_value"]:
                historical_row = r
                break

    assert historical_row is not None, "Expected at least one historical email change in audit log"
    old_email = historical_row["old_value"]
    expected_uid = historical_row["user_id"]

    resolved = identity_resolver.resolve(old_email)
    assert resolved is not None
    assert resolved["user_id"] == expected_uid
    assert old_email.lower() in resolved["all_emails"]
    assert resolved["current_email"].lower() in resolved["all_emails"]


def test_unknown_identity_returns_none():
    """Resolving an email that has never existed in the system must return None."""
    assert identity_resolver.resolve("definitely_nonexistent_user_99999@example.com") is None
    assert identity_resolver.resolve("") is None
    assert identity_resolver.resolve("   ") is None


def test_identity_matches_helper():
    """Test identity_matches checks across user_id, current, and historical identifiers."""
    sample_csv = REPO_ROOT / "dataset" / "sample_deletion_requests.csv"
    with open(sample_csv, encoding="utf-8") as f:
        first_row = next(csv.DictReader(f))

    identity = identity_resolver.resolve(first_row["email"])
    assert identity is not None

    # Matches user_id
    assert identity_resolver.identity_matches(identity["user_id"], identity)
    # Matches current email
    assert identity_resolver.identity_matches(identity["current_email"], identity)
    # Case-insensitive matching
    assert identity_resolver.identity_matches(identity["current_email"].upper(), identity)
    # Matches phone if present
    if identity["current_phone"]:
        assert identity_resolver.identity_matches(identity["current_phone"], identity)
    # Non-matching identifier returns False
    assert not identity_resolver.identity_matches("completely_random_unrelated_id", identity)
    assert not identity_resolver.identity_matches(None, identity)


# ---------------------------------------------------------------------------
# 2. Request Classifier Tests
# ---------------------------------------------------------------------------

def test_all_sample_requests_classify_as_deletion():
    """
    All 32 public sample cases in sample_deletion_requests.csv are genuine deletion requests.
    They should all be classified as DELETION.
    """
    sample_csv = REPO_ROOT / "dataset" / "sample_deletion_requests.csv"
    with open(sample_csv, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            classification = request_classifier.classify(row["request_text"])
            assert classification == "DELETION", (
                f"Sample case {row['case_id']} was unexpectedly classified as {classification}. "
                f"Text: {row['request_text']}"
            )


def test_non_deletion_categories_classify_as_not_applicable():
    """
    Test standard GDPR / privacy requests that do NOT authorize deletion
    (access, export, portability, marketing opt-out, correction, explicit retention).
    These MUST classify as NOT_APPLICABLE.
    """
    non_deletion_examples = [
        "I'd like to download my account information in a portable format. Please keep the account as it is.",
        "I need a copy of last year's invoices for my records. Please leave my profile and purchase history in place.",
        "Please remove me from marketing lists only. I still want receipts and service messages for this account.",
        "Please stop the promotional emails. I still need the account and my order history, so I am not asking for deletion.",
        "Can you tell me what personal information you hold about me? This is an information request, not a request to erase it.",
        "My surname is misspelled on the account. Can you correct it without removing any of my records?",
        "The mobile number on my profile is out of date. Please replace it with the new one and leave the account active.",
        "I can't access my profile and need help resetting the login. Do not close the account.",
        "Could you send me a copy of the information held on my account? I still use it, so please don't delete or change anything.",
        "Please change the email address used for this account. I want to continue using the service.",
    ]

    for text in non_deletion_examples:
        res = request_classifier.classify(text)
        assert res == "NOT_APPLICABLE", f"Expected NOT_APPLICABLE but got {res} for text: {text}"


def test_multilingual_deletion_classification():
    """Test that deletion requests in multiple languages correctly classify as DELETION."""
    multilingual_deletion_examples = [
        "I want to permanently delete my account and erase all my personal data.",
        "Intenté eliminar mi cuenta ayer. Por favor completen la eliminación.",
        "Je demande la suppression définitive de mon compte et de mes données.",
        "Solicito a exclusão permanente da conta associada a este e-mail.",
        "Bitte mein Konto und alle personenbezogenen Daten löschen.",
        "このメールアドレスに関連するアカウントの完全な削除を依頼します。",
        "이 이메일 주소에 연결된 계정의 영구 삭제를 요청합니다.",
    ]

    for text in multilingual_deletion_examples:
        res = request_classifier.classify(text)
        assert res == "DELETION", f"Expected DELETION but got {res} for text: {text}"


def test_classifier_empty_input():
    """Empty or whitespace text should be safely classified as NOT_APPLICABLE."""
    assert request_classifier.classify("") == "NOT_APPLICABLE"
    assert request_classifier.classify("   ") == "NOT_APPLICABLE"
    assert request_classifier.classify(None) == "NOT_APPLICABLE"
