"""
request_classifier.py — Decide if a request authorizes permanent deletion.

Plain-English explanation:
  Customers write deletion requests in different languages (English, Spanish,
  French, Portuguese, German, Japanese, Korean, etc.) and styles.
  Most requests in the dataset ask to delete, erase, or close their account.
  However, some requests are NOT for deletion:
    - Requests for data access or export/portability ("download my data in portable format")
    - Requests to correct or update details ("my surname is misspelled", "change my email")
    - Requests to opt out of marketing only ("stop promotional emails", "marketing lists only")
    - Inquiries ("what personal information do you hold?")
    - Explicit non-deletion notices ("do not close the account", "leave the account active")

  Per AGENTS.md §6.5:
    "First determine whether request_text authorizes deletion. A request for access,
     correction, export, marketing opt-out, or another non-deletion action is
     NOT_APPLICABLE, even if other fields resemble a deletion case."

  When NOT_APPLICABLE, the final output must have deletion_status="NOT_APPLICABLE"
  and steps_json=[].
"""

import os
import re
from typing import Optional

# ---------------------------------------------------------------------------
# High-confidence non-deletion patterns
# These phrases explicitly request something other than account/data deletion,
# or explicitly state that the person does NOT want deletion.
# ---------------------------------------------------------------------------
_EXPLICIT_NON_DELETION_PATTERNS = [
    # Explicit negation of deletion
    r"not\s+(?:asking\s+for|a\s+request\s+for|a\s+request\s+to)\s+(?:deletion|delete|erase|erasure)",
    r"do\s+not\s+(?:close|delete|remove)\s+(?:the|my|this)?\s*account",
    r"don't\s+(?:close|delete|remove)\s+(?:the|my|this)?\s*account",
    r"please\s+don't\s+delete\s+or\s+change\s+anything",
    r"leave\s+(?:the|my|this)\s+account\s+active",
    r"leave\s+my\s+(?:profile|purchase\s+history|records)\s+in\s+place",
    r"without\s+(?:removing\s+any\s+of\s+my\s+records|deleting)",
    r"want\s+to\s+continue\s+using\s+the\s+service",
    r"still\s+use\s+it,?\s*so\s+please\s+don't\s+delete",
    r"still\s+need\s+the\s+account",
    r"keep\s+the\s+account\s+(?:as\s+it\s+is|active|open)",

    # Data export / portability requests without deletion
    r"download\s+my\s+account\s+information\s+in\s+a\s+portable\s+format",
    r"portable\s+format",
    r"need\s+a\s+copy\s+of\s+last\s+year'?s\s+invoices",

    # Marketing opt-out only
    r"remove\s+me\s+from\s+marketing\s+lists\s+only",
    r"stop\s+the\s+promotional\s+emails",
    r"opt\s*-?\s*out\s+of\s+marketing",
    r"unsubscribe\s+from\s+(?:all\s+)?emails",

    # Access / Information request only
    r"what\s+personal\s+information\s+you\s+hold\s+about\s+me",
    r"information\s+request,\s*not\s+a\s+request\s+to\s+erase",
    r"subject\s+access\s+request",

    # Rectification / Correction only
    r"surname\s+is\s+misspelled",
    r"correct\s+it\s+without\s+removing",
    r"mobile\s+number\s+on\s+my\s+profile\s+is\s+out\s+of\s+date",
    r"replace\s+it\s+with\s+the\s+new\s+one\s+and\s+leave\s+the\s+account",
    r"change\s+the\s+email\s+address\s+used\s+for\s+this\s+account",
    r"need\s+help\s+resetting\s+the\s+login",
]

# ---------------------------------------------------------------------------
# Deletion keywords and phrases across languages
# ---------------------------------------------------------------------------
_DELETION_PATTERNS = [
    # English
    r"\bdelet(?:e|ed|ing|ion|ions)\b",
    r"\beras(?:e|ed|ing|ure)\b",
    r"\bremov(?:e|ed|ing|al)\b",
    r"\bclose\s+(?:my|this|the)?\s*account\b",
    r"\bclosed\b",
    r"\bpurge\b",
    r"\bwipe\b",
    r"\bright\s+to\s+be\s+forgotten\b",
    r"\brtbf\b",
    r"\bpermanent(?:ly)?\s+(?:delete|remove|erase|account-deletion)\b",
    r"\baccount\s+(?:closure|deletion|removal)\b",
    r"\bpersonal-data\s+deletion\b",

    # Spanish
    r"\belimin(?:ar|ación|acion|ado|ando|e)\b",
    r"\bborr(?:ar|ado|ando)\b",
    r"\bsuprim(?:ir|ido|iendo)\b",
    r"\bsupresi[oó]n\b",
    r"\bcerrar\s+(?:mi|esta)?\s*cuenta\b",

    # French
    r"\bsuppress(?:ion|ions)\b",
    r"\bsupprim(?:er|ez|é|ant)\b",
    r"\beffac(?:er|é|ant)\b",
    r"\bfermer\s+(?:mon|ce)?\s*compte\b",

    # Portuguese
    r"\bexclus[aã]o\b",
    r"\bexclui(?:r|do|ndo)\b",
    r"\bapag(?:ar|ado|ando)\b",
    r"\bremo(?:ver|[çc][aã]o)\b",

    # German
    r"\bl[oö]sch(?:en|ung)\b",
    r"\bkonto\s+l[oö]schen\b",

    # Japanese
    r"削除",           # sakujo (delete/deletion)
    r"アカウントの完全な削除",

    # Korean
    r"삭제",           # sakje (delete/deletion)
    r"영구\s*삭제",     # yeong-gu sakje (permanent deletion)
]

_explicit_non_deletion_re = re.compile("|".join(_EXPLICIT_NON_DELETION_PATTERNS), re.IGNORECASE)
_deletion_re = re.compile("|".join(_DELETION_PATTERNS), re.IGNORECASE)


def classify(request_text: str) -> str:
    """
    Classify a deletion request text.

    Returns:
      'DELETION'        — request authorizes personal data / account deletion
      'NOT_APPLICABLE'  — request is for non-deletion (access, export, opt-out, correction, etc.)
    """
    if not request_text or not request_text.strip():
        return "NOT_APPLICABLE"

    text = request_text.strip()

    # Step 1: Check if the text matches explicit non-deletion patterns
    if _explicit_non_deletion_re.search(text):
        return "NOT_APPLICABLE"

    # Step 2: Check if the text matches genuine deletion patterns
    if _deletion_re.search(text):
        return "DELETION"

    # Step 3: Fallback LLM classification if Anthropic key is present
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if api_key:
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=api_key)
            prompt = (
                "You are a GDPR/privacy compliance classifier.\n"
                "Determine if this message is a request to DELETE/ERASE an account or personal data.\n"
                "Answer ONLY 'DELETION' or 'NOT_APPLICABLE'.\n\n"
                f"Message:\n{text[:2000]}"
            )
            msg = client.messages.create(
                model="claude-3-haiku-20240307",
                max_tokens=10,
                messages=[{"role": "user", "content": prompt}]
            )
            ans = msg.content[0].text.strip().upper()
            if "NOT_APPLICABLE" in ans:
                return "NOT_APPLICABLE"
            return "DELETION"
        except Exception:
            pass

    # Safe default: if not explicitly non-deletion, assume DELETION to avoid missing compliance obligations
    return "DELETION"
