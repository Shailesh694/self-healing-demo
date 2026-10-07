from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from .models import Incident


@dataclass
class IncidentRecord:
    incident: Incident
    created_at: str
    status: str = "open"


class IncidentManager:
    """
    Keeps track of incidents handled by SelfHeal.

    With a state file (path argument or SELFHEAL_STATE_FILE) incidents are
    persisted as JSON, so separate processes (API server and MCP server)
    and restarts see the same incidents. Without it, state is in memory.
    """

    def __init__(self, path: str | os.PathLike | None = None) -> None:
        self._path = Path(path) if path else None
        self._incidents: list[IncidentRecord] = []
        self._load()

    # -- persistence
    def _load(self) -> None:
        if not self._path or not self._path.exists():
            return
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            self._incidents = [
                IncidentRecord(
                    incident=Incident(**row["incident"]),
                    created_at=row["created_at"],
                    status=row.get("status", "open"),
                )
                for row in data
            ]
        except (OSError, ValueError, TypeError, KeyError):
            self._incidents = []

    def _save(self) -> None:
        if not self._path:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(self._path.suffix + ".tmp")
        tmp.write_text(
            json.dumps([asdict(r) for r in self._incidents]),
            encoding="utf-8",
        )
        os.replace(tmp, self._path)

    # -- API
    def create(self, incident: Incident) -> IncidentRecord:
        self._load()
        record = IncidentRecord(
            incident=incident,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self._incidents.append(record)
        self._save()
        return record

    def close(self, record: IncidentRecord) -> None:
        self._load()
        for r in self._incidents:
            if r.created_at == record.created_at and r.incident == record.incident:
                r.status = "closed"
        record.status = "closed"
        self._save()

    def list_open(self) -> list[IncidentRecord]:
        self._load()
        return [r for r in self._incidents if r.status == "open"]
