from __future__ import annotations

import re


# Common credential patterns. These are intentionally conservative.
SECRET_PATTERNS = [
    (
        re.compile(
            r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b"
        ),
        "[REDACTED_GITHUB_TOKEN]",
    ),
    (
        re.compile(
            r"\bAIza[0-9A-Za-z_\-]{20,}\b"
        ),
        "[REDACTED_GOOGLE_KEY]",
    ),
    (
        re.compile(
            r"\beyJ[A-Za-z0-9_-]{10,}\."
            r"[A-Za-z0-9_-]{10,}\."
            r"[A-Za-z0-9_-]{10,}\b"
        ),
        "[REDACTED_JWT]",
    ),
    (
        re.compile(
            r"-----BEGIN [A-Z ]*PRIVATE KEY-----"
            r".*?"
            r"-----END [A-Z ]*PRIVATE KEY-----",
            re.DOTALL,
        ),
        "[REDACTED_PRIVATE_KEY]",
    ),
    (
        re.compile(
            r"(?i)(api[_-]?key|secret|password|token)"
            r"(\s*[:=]\s*)['\"]?([A-Za-z0-9_\-./+=]{8,})['\"]?"
        ),
        r"\1\2[REDACTED]",
    ),
    (
        re.compile(
            r"(?i)bearer\s+[A-Za-z0-9\-._~+/]+=*"
        ),
        "Bearer [REDACTED]",
    ),
]


def scrub_secrets(text: str) -> str:
    """
    Redact common secrets before repository context is sent to an AI model.

    This function is deterministic and does not contact any external service.
    """

    if not text:
        return text

    scrubbed = text

    for pattern, replacement in SECRET_PATTERNS:
        scrubbed = pattern.sub(replacement, scrubbed)

    return scrubbed