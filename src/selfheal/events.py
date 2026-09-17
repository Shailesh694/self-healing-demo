from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class HealingEvent:
    name: str
    data: dict[str, Any]


def incident_detected(
    incident_id: str,
) -> HealingEvent:
    return HealingEvent(
        name="incident.detected",
        data={
            "incident_id": incident_id,
        },
    )


def repair_started(
    incident_id: str,
) -> HealingEvent:
    return HealingEvent(
        name="repair.started",
        data={
            "incident_id": incident_id,
        },
    )


def repair_completed(
    incident_id: str,
    status: str,
) -> HealingEvent:
    return HealingEvent(
        name="repair.completed",
        data={
            "incident_id": incident_id,
            "status": status,
        },
    )