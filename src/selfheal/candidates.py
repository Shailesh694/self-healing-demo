"""
Authoritative record of repair candidates.

Only the engine writes gate results here. Execution looks results up by
candidate_id instead of trusting caller-supplied booleans.

Candidates are in memory by default; set SELFHEAL_STATE_FILE (or
SELFHEAL_CANDIDATE_FILE) to persist them so another process can execute
them by id. See CandidateStore.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass
class Candidate:
    incident_id: str
    project_path: str
    file_path: str            # absolute path of the approved target
    rel_target: str           # posix path relative to project_path
    patch: str
    source: str               # "rule_based" | "ai_surveyor_coder_reviewer"
    confidence: float
    patch_sha256: str
    target_sha256: str        # target content hash when the candidate was approved
    git_commit: bool = False
    test_command: list[str] = field(default_factory=list)
    candidate_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    status: str = "created"   # created | needs_review | rejected | approved | executed | failed
    risk: dict = field(default_factory=dict)
    validation_ok: bool = False
    policy_allowed: bool = False
    sandbox_passed: bool = False
    regression_passed: bool = False
    notes: list[str] = field(default_factory=list)

    def public(self) -> dict:
        data = asdict(self)
        data.pop("patch", None)
        return data


class CandidateStore:
    """
    Registry of repair candidates.

    - Without a file (default) candidates live in process memory.
    - With a file, candidates persist as JSON and are visible to other
      processes: the path is `path`, else SELFHEAL_CANDIDATE_FILE, else
      derived from SELFHEAL_STATE_FILE (`<name>.candidates.json`).
    - With SELFHEAL_STATE_KEY set, every record is HMAC-signed and records
      without a valid signature are ignored, so editing the file by hand
      cannot forge an approval. Without a key, anyone who can write the
      file can forge records: protect it with file permissions.

    Persisted candidates are always re-checked by the execution boundary
    (gate flags, patch hash, target hash) before anything runs. Writes are
    atomic (os.replace) but concurrent writers are last-write-wins.
    """

    MAX_RECORDS = 200

    def __init__(self, path: str | os.PathLike | None = None, *,
                 from_env: bool = False, key: str | None = None) -> None:
        self._path = Path(path) if path else None
        self._from_env = from_env
        self._key = key
        self._items: dict[str, Candidate] = {}
        self._lock = threading.Lock()

    # -- configuration
    def _file(self) -> Path | None:
        if self._path is not None:
            return self._path
        if self._from_env:
            explicit = os.getenv("SELFHEAL_CANDIDATE_FILE")
            if explicit:
                return Path(explicit)
            state = os.getenv("SELFHEAL_STATE_FILE")
            if state:
                p = Path(state)
                return p.with_name(p.stem + ".candidates.json")
        return None

    def _signing_key(self) -> bytes | None:
        key = self._key if self._key is not None else os.getenv("SELFHEAL_STATE_KEY")
        return key.encode() if key else None

    @staticmethod
    def _canonical(data: dict) -> str:
        return json.dumps(data, sort_keys=True, separators=(",", ":"))

    def _sign(self, data: dict) -> str | None:
        key = self._signing_key()
        if key is None:
            return None
        return hmac.new(key, self._canonical(data).encode(), hashlib.sha256).hexdigest()

    # -- file helpers
    def _read(self, path: Path) -> dict:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            return raw if isinstance(raw, dict) else {}
        except (OSError, ValueError):
            return {}

    def _write(self, path: Path, records: dict) -> None:
        if len(records) > self.MAX_RECORDS:
            ordered = sorted(records.items(), key=lambda kv: kv[1]["data"].get("created_at", ""))
            records = dict(ordered[-self.MAX_RECORDS:])
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
        tmp.write_text(json.dumps(records), encoding="utf-8")
        os.replace(tmp, path)

    # -- API
    def save(self, candidate: Candidate) -> Candidate:
        path = self._file()
        with self._lock:
            if path is None:
                self._items[candidate.candidate_id] = candidate
                return candidate
            records = self._read(path)
            data = asdict(candidate)
            records[candidate.candidate_id] = {"data": data, "sig": self._sign(data)}
            self._write(path, records)
        return candidate

    add = save

    def get(self, candidate_id: str) -> Candidate | None:
        path = self._file()
        with self._lock:
            if path is None:
                return self._items.get(candidate_id)
            record = self._read(path).get(candidate_id)
        if not isinstance(record, dict) or not isinstance(record.get("data"), dict):
            return None
        data = record["data"]
        if self._signing_key() is not None and not hmac.compare_digest(
            str(record.get("sig") or ""), self._sign(data) or ""
        ):
            return None  # unsigned or tampered record
        try:
            return Candidate(**data)
        except TypeError:
            return None

    def clear(self) -> None:
        path = self._file()
        with self._lock:
            self._items.clear()
            if path is not None and path.exists():
                path.unlink()


candidate_store = CandidateStore(from_env=True)
