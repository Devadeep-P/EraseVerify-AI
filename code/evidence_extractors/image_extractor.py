"""
evidence_extractors/image_extractor.py

Plain-English explanation:
  PNG images are screenshots of admin consoles (account admin, search index
  inspector, backup restore console, connector management, etc.).

  They contain valuable state information — e.g. a screenshot showing an
  account marked "DELETED" proves deletion; a backup console showing
  "Restore Allowed: YES" proves a restore risk.

  We use a multimodal LLM (Claude) to read and interpret each image.
  If no API key is available, we fall back to pytesseract OCR.

  The LLM receives:
  1. The image as base64.
  2. A structured prompt asking it to list any records it sees belonging
     to identifiers we provide.

  Returns a list of finding dicts.
"""

import base64
import os
import re
from pathlib import Path
from typing import Any


def _normalise(v: Any) -> str:
    return str(v or "").strip().lower()


# ── LLM-based extraction ──────────────────────────────────────────────────────

_IMAGE_PROMPT = """You are a privacy compliance analyst reading a screenshot of an admin console.

The deletion subject has these identifiers:
  User ID: {user_id}
  Emails: {emails}
  Phones: {phones}

Examine the screenshot carefully. List ONLY rows/entries that belong to this subject.
For each entry found, output one line in this exact format:
  RECORD | system_id | resource_id | record_type | state

Where:
- system_id is one of: account_service, search_service, analytics_platform, support_platform, integration_service, backup_service, security_service, export_service, marketing_platform, identity_service
- resource_id is the identifier shown (e.g. account_123, search_456)
- record_type is one of: USER_PROFILE, SEARCH_INDEX_ENTRY, ANALYTICS_PROFILE, SUPPORT_MESSAGE, SECURITY_AUDIT_LOG, USER_EXPORT, MARKETING_PROFILE, BACKUP_ARCHIVE, ACCOUNT_TOMBSTONE, DATA_FLOW
- state is one of: PRESENT, ABSENT, ACTIVE, DISABLED, BLOCKED, REDACTED, ANONYMIZED, IDENTIFIABLE

If no records for this subject appear in the screenshot, output: NONE

Output only the RECORD lines or NONE. No explanations."""


def extract(img_path: Path, identity: dict) -> list[dict]:
    """
    Analyse a PNG screenshot for records belonging to the identity.
    Returns a list of finding dicts.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()

    if api_key:
        return _extract_with_llm(img_path, identity, api_key)
    else:
        return _extract_with_ocr(img_path, identity)


def _extract_with_llm(img_path: Path, identity: dict, api_key: str) -> list[dict]:
    """Use Claude's vision API to read the screenshot."""
    try:
        import anthropic

        img_bytes = img_path.read_bytes()
        img_b64   = base64.b64encode(img_bytes).decode("utf-8")

        prompt = _IMAGE_PROMPT.format(
            user_id=identity["user_id"],
            emails=", ".join(sorted(identity["all_emails"])),
            phones=", ".join(sorted(identity["all_phones"])),
        )

        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=500,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type":       "base64",
                            "media_type": "image/png",
                            "data":       img_b64,
                        },
                    },
                    {"type": "text", "text": prompt},
                ],
            }],
        )

        response_text = message.content[0].text.strip()
        return _parse_llm_response(response_text, img_path.name)

    except Exception:
        return []


def _parse_llm_response(text: str, source: str) -> list[dict]:
    """Parse the structured LLM response into finding dicts."""
    findings = []
    if "NONE" in text.upper() and len(text) < 20:
        return findings

    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("RECORD"):
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 5:
            continue
        _, system_id, resource_id, record_type, state = parts[:5]
        findings.append({
            "system_id":       system_id,
            "resource_id":     resource_id,
            "record_type":     record_type.upper(),
            "state":           state.upper(),
            "evidence_detail": f"image:{source}",
        })
    return findings


def _extract_with_ocr(img_path: Path, identity: dict) -> list[dict]:
    """
    Fallback: use pytesseract OCR to extract text from the image,
    then search for known identifiers.
    """
    all_ids = (
        identity["all_emails"]
        | identity["all_phones"]
        | identity["all_email_hashes"]
        | {_normalise(identity["user_id"])}
    )

    findings = []
    try:
        from PIL import Image
        import pytesseract

        img  = Image.open(img_path)
        text = pytesseract.image_to_string(img)
    except (ImportError, Exception):
        return findings

    lines = text.splitlines()
    for line in lines:
        norm = _normalise(line)
        if any(id_val in norm for id_val in all_ids if id_val):
            resource_id = _extract_resource_id_from_text(line)
            findings.append({
                "system_id":       "account_service",
                "resource_id":     resource_id,
                "record_type":     "USER_PROFILE",
                "state":           "PRESENT",
                "evidence_detail": f"ocr:{img_path.name}:{line.strip()[:100]}",
            })

    return findings


def _extract_resource_id_from_text(text: str) -> str:
    pattern = re.compile(
        r'\b(account_\w+|audit_record_\w+|support_\w+|analytics_\w+|'
        r'backup_\w+|search_\w+|export_\w+|tombstone_\w+|data_flow_\w+)\b',
        re.IGNORECASE,
    )
    match = pattern.search(text)
    return match.group(0) if match else "unknown"
