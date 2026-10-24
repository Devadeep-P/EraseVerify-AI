"""
config.py — Central path configuration for Ghost Data Still Exists.

Everything is resolved relative to the REPO ROOT (the folder that contains
AGENTS.md). This means the code works on any machine regardless of username
or drive letter.

Plain-English explanation:
  - We find the repo root by going two levels up from this file
    (this file lives in code/, which is inside the repo root).
  - All dataset and evidence paths are built from that root.
  - The output file is always at the repo root level.
"""

from pathlib import Path

# ── Repo root ─────────────────────────────────────────────────────────────────
# This file is at <repo_root>/code/config.py
# Path(__file__).parent  →  <repo_root>/code/
# .parent again          →  <repo_root>/
REPO_ROOT = Path(__file__).parent.parent.resolve()

# ── Dataset directory ─────────────────────────────────────────────────────────
DATASET_DIR = REPO_ROOT / "dataset"
EVIDENCE_DIR = DATASET_DIR / "evidence"

# ── Input CSV files ───────────────────────────────────────────────────────────
DELETION_REQUESTS_CSV    = DATASET_DIR / "deletion_requests.csv"
SAMPLE_DELETION_REQUESTS = DATASET_DIR / "sample_deletion_requests.csv"
SAMPLE_OUTPUT_CSV        = DATASET_DIR / "sample_output.csv"

USER_IDENTITIES_CSV      = DATASET_DIR / "user_identities.csv"
USER_AUDIT_LOG_CSV       = DATASET_DIR / "user_audit_log.csv"
SYSTEM_ACTIVITY_CSV      = DATASET_DIR / "system_activity.csv"
DELETION_RULES_CSV       = DATASET_DIR / "deletion_rules.csv"
EVIDENCE_FILES_CSV       = DATASET_DIR / "evidence_files.csv"

# ── Output file ───────────────────────────────────────────────────────────────
OUTPUT_CSV = REPO_ROOT / "output.csv"

# ── Log file (AGENTS.md §2) ───────────────────────────────────────────────────
LOG_FILE = REPO_ROOT / "log.txt"

# ── Evidence sub-directories ──────────────────────────────────────────────────
EVIDENCE_DATABASES = EVIDENCE_DIR / "databases"
EVIDENCE_LOGS      = EVIDENCE_DIR / "logs"
EVIDENCE_RECORDS   = EVIDENCE_DIR / "records"
EVIDENCE_DOCUMENTS = EVIDENCE_DIR / "documents"
EVIDENCE_IMAGES    = EVIDENCE_DIR / "images"

# ── Deletion status constants ─────────────────────────────────────────────────
STATUS_COMPLETE       = "COMPLETE"
STATUS_INCOMPLETE     = "INCOMPLETE"
STATUS_NOT_APPLICABLE = "NOT_APPLICABLE"

# ── Phase constants ───────────────────────────────────────────────────────────
PHASE_FINDING      = "FINDING"
PHASE_REMEDIATION  = "REMEDIATION"
PHASE_VERIFICATION = "VERIFICATION"

# ── Operation constants (in the canonical ordering for step sorting) ──────────
FINDING_OPERATIONS = [
    "REPORT_REMAINING_RECORD",
    "REPORT_EXPOSED_PII",
    "REPORT_ACTIVE_DATA_FLOW",
    "REPORT_RESTORE_RISK",
]

REMEDIATION_OPERATIONS = [
    "DISABLE_DATA_FLOW",
    "BLOCK_RESTORE",
    "DELETE_RECORD",
    "REDACT_RECORD",
    "ANONYMIZE_RECORD",
]

VERIFICATION_OPERATIONS = [
    "VERIFY_RECORD_ABSENT",
    "VERIFY_RECORD_PRESENT",
    "VERIFY_RECORD_REDACTED",
    "VERIFY_RECORD_ANONYMIZED",
    "VERIFY_DATA_FLOW_DISABLED",
    "VERIFY_RESTORE_BLOCKED",
]

OPERATION_ORDER = (
    FINDING_OPERATIONS + REMEDIATION_OPERATIONS + VERIFICATION_OPERATIONS
)

def operation_rank(op: str) -> int:
    """Return the canonical sort rank of an operation name."""
    try:
        return OPERATION_ORDER.index(op)
    except ValueError:
        return 999


# ── State constants ───────────────────────────────────────────────────────────
STATE_PRESENT    = "PRESENT"
STATE_ABSENT     = "ABSENT"
STATE_ACTIVE     = "ACTIVE"
STATE_DISABLED   = "DISABLED"
STATE_BLOCKED    = "BLOCKED"
STATE_REDACTED   = "REDACTED"
STATE_ANONYMIZED = "ANONYMIZED"

# ── Operation → State mapping ─────────────────────────────────────────────────
OP_TO_STATE = {
    "REPORT_REMAINING_RECORD":   STATE_PRESENT,
    "REPORT_EXPOSED_PII":        STATE_PRESENT,
    "REPORT_ACTIVE_DATA_FLOW":   STATE_ACTIVE,
    "REPORT_RESTORE_RISK":       STATE_ACTIVE,
    "DISABLE_DATA_FLOW":         STATE_DISABLED,
    "BLOCK_RESTORE":             STATE_BLOCKED,
    "DELETE_RECORD":             STATE_ABSENT,
    "REDACT_RECORD":             STATE_REDACTED,
    "ANONYMIZE_RECORD":          STATE_ANONYMIZED,
    "VERIFY_RECORD_ABSENT":      STATE_ABSENT,
    "VERIFY_RECORD_PRESENT":     STATE_PRESENT,
    "VERIFY_RECORD_REDACTED":    STATE_REDACTED,
    "VERIFY_RECORD_ANONYMIZED":  STATE_ANONYMIZED,
    "VERIFY_DATA_FLOW_DISABLED": STATE_DISABLED,
    "VERIFY_RESTORE_BLOCKED":    STATE_BLOCKED,
}

# ── Deletion rules: data_category → required action ──────────────────────────
# Mirrors deletion_rules.csv exactly.
CATEGORY_ACTION = {
    "USER_PROFILE":         "DELETE",
    "SECONDARY_IDENTIFIER": "DELETE",
    "SEARCH_INDEX_ENTRY":   "DELETE",
    "CACHE_ENTRY":          "DELETE",
    "SUPPORT_MESSAGE":      "REDACT",
    "SUPPORT_ATTACHMENT":   "DELETE",
    "ANALYTICS_PROFILE":    "ANONYMIZE",
    "PRODUCT_TELEMETRY":    "ANONYMIZE",
    "USER_EXPORT":          "DELETE",
    "MARKETING_PROFILE":    "DELETE",
    "EMAIL_DELIVERY_LOG":   "REDACT",
    "SECURITY_AUDIT_LOG":   "RETAIN",
    "LEGAL_HOLD_RECORD":    "RETAIN",
    "BACKUP_ARCHIVE":       "RETAIN",    # keep archive, BLOCK restore access
    "ACCOUNT_TOMBSTONE":    "REDACT",    # keep user_id, strip name/email/phone/hash
}
