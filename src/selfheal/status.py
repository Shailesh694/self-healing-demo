from __future__ import annotations

from enum import Enum


class RepairStatus(str, Enum):
    DETECTED = "detected"
    ANALYZING = "analyzing"
    PROPOSED = "proposed"
    VALIDATING = "validating"
    REPAIRING = "repairing"
    VERIFIED = "verified"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


TERMINAL_STATUSES = {
    RepairStatus.VERIFIED,
    RepairStatus.FAILED,
    RepairStatus.ROLLED_BACK,
}


def is_terminal(status: RepairStatus) -> bool:
    return status in TERMINAL_STATUSES