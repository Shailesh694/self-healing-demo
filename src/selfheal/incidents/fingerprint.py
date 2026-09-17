from __future__ import annotations

import hashlib
import re

from selfheal.models import Incident


class IncidentFingerprinter:
    """
    Generate stable identifiers for normalized incidents.

    Fingerprints are deterministic: the same logical incident should
    produce the same fingerprint across different runs.
    """

    def fingerprint(self, incident: Incident) -> str:
        """
        Generate a stable fingerprint for an incident.

        The fingerprint intentionally uses normalized diagnostic fields
        rather than the entire raw tool output.
        """

        canonical = self._canonical_form(incident)

        digest = hashlib.sha256(
            canonical.encode("utf-8")
        ).hexdigest()

        return digest[:16]

    def canonical(self, incident: Incident) -> str:
        """
        Return the normalized string used as the fingerprint input.

        This is useful for debugging and testing.
        """

        return self._canonical_form(incident)

    def _canonical_form(self, incident: Incident) -> str:
        source = self._normalize_text(incident.source)
        code = self._normalize_text(incident.code)
        path = self._normalize_path(incident.file_path)
        line = incident.line or 0
        column = incident.column or 0
        message = self._normalize_message(incident.message)

        return "|".join(
            (
                source,
                code,
                path,
                str(line),
                str(column),
                message,
            )
        )

    @staticmethod
    def _normalize_text(value: str | None) -> str:
        if not value:
            return ""

        return " ".join(value.strip().lower().split())

    @staticmethod
    def _normalize_path(value: str | None) -> str:
        if not value:
            return ""

        return value.replace("\\", "/").strip().lower()

    @staticmethod
    def _normalize_message(value: str | None) -> str:
        if not value:
            return ""

        message = value.strip().lower()

        # Remove memory addresses such as 0x7ffabc123.
        message = re.sub(
            r"0x[0-9a-f]+",
            "<address>",
            message,
        )

        # Normalize repeated whitespace.
        message = " ".join(message.split())

        return message