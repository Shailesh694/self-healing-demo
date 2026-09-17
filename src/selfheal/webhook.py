from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class WebhookEvent:
    provider: str
    event_type: str
    payload: dict[str, Any]


def parse_webhook(
    payload: dict[str, Any],
    *,
    provider: str = "generic",
    event_type: str = "unknown",
) -> WebhookEvent:
    """
    Convert an incoming CI/CD webhook payload into
    a normalized SelfHeal event.
    """

    if not isinstance(payload, dict):
        raise TypeError(
            "Webhook payload must be a dictionary"
        )

    return WebhookEvent(
        provider=provider,
        event_type=event_type,
        payload=payload,
    )