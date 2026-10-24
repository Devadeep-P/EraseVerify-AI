"""
evidence_extractors/pdf_extractor.py

Plain-English explanation:
  PDF files contain business documents like:
  - Legal retention registers (tells us which records are on legal hold)
  - Security retention extracts (tells us audit log retention periods)
  - Delivery correction attachments (support ticket attachments)
  - Account history reports

  We use pdfplumber to extract all text, then search for identifiers.
  PDFs don't give us structured records, so we extract key facts as text
  and let the fact_aggregator interpret them.

  Returns a list of raw text findings with notes about what was found.
"""

from pathlib import Path
from typing import Any


def _normalise(v: Any) -> str:
    return str(v or "").strip().lower()


def extract(pdf_path: Path, identity: dict) -> list[dict]:
    """
    Extract text from a PDF and search for identity mentions.

    Returns findings with state='PRESENT' and a text excerpt as evidence_detail.
    The record_type is inferred from surrounding context in the text.
    """
    all_ids = (
        identity["all_emails"]
        | identity["all_phones"]
        | identity["all_email_hashes"]
        | {_normalise(identity["user_id"])}
    )

    findings = []

    # Try pdfplumber first
    try:
        import pdfplumber
        with pdfplumber.open(pdf_path) as pdf:
            full_text = "\n".join(
                page.extract_text() or "" for page in pdf.pages
            )
    except ImportError:
        # Fall back to PyPDF2 if available
        try:
            import PyPDF2
            with open(pdf_path, "rb") as f:
                reader = PyPDF2.PdfReader(f)
                full_text = "\n".join(
                    page.extract_text() or "" for page in reader.pages
                )
        except ImportError:
            return []  # No PDF library available
    except Exception:
        return []

    if not full_text:
        return []

    # Split into lines and search for identity matches
    lines = full_text.splitlines()
    for i, line in enumerate(lines):
        norm_line = _normalise(line)
        if any(id_val in norm_line for id_val in all_ids if id_val):
            # Found a mention — extract context (expanded window to catch document headers)
            context_start = max(0, i - 8)
            context_end   = min(len(lines), i + 8)
            context = " | ".join(lines[context_start:context_end]).strip()

            # Infer record type from surrounding text
            record_type = _infer_type_from_text(full_text, line)
            system_id   = _infer_system_from_text(full_text, line)
            resource_id = _extract_resource_id(line, context, full_text)
            if not resource_id or resource_id == "unknown":
                continue
            state       = _infer_state_from_text(line, context)

            findings.append({
                "system_id":       system_id,
                "resource_id":     resource_id,
                "record_type":     record_type,
                "state":           state,
                "evidence_detail": context[:300],
            })

    return findings


def _infer_type_from_text(full_text: str, line: str) -> str:
    """Guess data category from surrounding text."""
    t = (full_text + line).lower()
    if "delivery address correction" in t or "attachment" in t:
        return "SUPPORT_ATTACHMENT"
    if "legal hold" in t or "legal retention" in t or "disputed order" in t or "retain until" in t or "tax record" in t:
        return "LEGAL_HOLD_RECORD"
    if "security audit" in t or "audit log" in t or "retention period" in t:
        return "SECURITY_AUDIT_LOG"
    if "support" in t:
        return "SUPPORT_MESSAGE"
    if "account history" in t or "account profile" in t:
        return "USER_PROFILE"
    if "analytics" in t:
        return "ANALYTICS_PROFILE"
    return "USER_PROFILE"


def _infer_system_from_text(full_text: str, line: str) -> str:
    """Guess system from surrounding text."""
    t = (full_text + line).lower()
    if "delivery address correction" in t or "support" in t:
        return "support_platform"
    if "security" in t or "audit" in t or "legal" in t:
        return "security_service"
    if "analytics" in t:
        return "analytics_platform"
    return "account_service"


def _extract_resource_id(line: str, context: str, full_text: str = "") -> str:
    """Try to pull a resource_id-like token from context."""
    import re
    pattern = re.compile(
        r'\b(account_\w+|audit_record_\w+|support_\w+|analytics_\w+|'
        r'backup_\w+|search_\w+|export_\w+|tombstone_\w+|data_flow_\w+)\b',
        re.IGNORECASE
    )
    match = pattern.search(context)
    if match:
        return match.group(0).lower()
    return "unknown"


def _infer_state_from_text(line: str, context: str) -> str:
    """Guess state from surrounding text keywords."""
    t = (line + context).lower()
    if "not found" in t or "deleted" in t or "absent" in t:
        return "ABSENT"
    if "anonymized" in t or "anonymised" in t:
        return "ANONYMIZED"
    if "redacted" in t:
        return "REDACTED"
    if "blocked" in t:
        return "BLOCKED"
    if "disabled" in t:
        return "DISABLED"
    return "PRESENT"
