from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from .status import RepairStatus


@dataclass
class HealingState:
    incident_id: str
    status: RepairStatus = RepairStatus.DETECTED
    history: list[str] = field(default_factory=list)

    def transition(self, status: RepairStatus) -> None:
        self.status = status
        self.history.append(
            f"{datetime.now(timezone.utc).isoformat()}: "
            f"{status.value}"
        )