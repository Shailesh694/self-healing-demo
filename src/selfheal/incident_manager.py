from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from .models import Incident


@dataclass
class IncidentRecord:
    incident: Incident
    created_at: str
    status: str = "open"


class IncidentManager:
    """
    Keeps track of incidents handled by SelfHeal.
    """

    def __init__(self) -> None:
        self._incidents: list[IncidentRecord] = []

    def create(self, incident: Incident) -> IncidentRecord:
        record = IncidentRecord(
            incident=incident,
            created_at=datetime.now(
                timezone.utc
            ).isoformat(),
        )

        self._incidents.append(record)

        return record

    def close(self, record: IncidentRecord) -> None:
        record.status = "closed"

    def list_open(self) -> list[IncidentRecord]:
        return [
            record
            for record in self._incidents
            if record.status == "open"
        ]