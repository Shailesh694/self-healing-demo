from __future__ import annotations

import hashlib
import hmac
import json
import os
import uuid
from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.concurrency import run_in_threadpool

from .ci import normalize_github_payload
from .diagnostics import diagnose
from .events import incident_detected
from .logger import get_logger
from .models import Incident
from .policy import RepairPolicy
from .runtime import incident_manager
from .security.paths import ensure_allowed
from .webhook import parse_webhook
from .workflow import process_ci_failure

log = get_logger("selfheal.server")

app = FastAPI(
    title="SelfHeal CI/CD",
    version="0.2.0",
)


def _authenticate(raw: bytes, token: str | None, signature: str | None) -> None:
    """
    Open when neither SELFHEAL_WEBHOOK_TOKEN nor SELFHEAL_WEBHOOK_SECRET is
    set. Otherwise accept a matching X-Selfheal-Token or a valid GitHub-style
    X-Hub-Signature-256 HMAC of the raw body.
    """
    expected_token = os.getenv("SELFHEAL_WEBHOOK_TOKEN")
    secret = os.getenv("SELFHEAL_WEBHOOK_SECRET")
    if not expected_token and not secret:
        return

    if expected_token and token and hmac.compare_digest(expected_token, token):
        return

    if secret and signature:
        digest = "sha256=" + hmac.new(
            secret.encode(), raw, hashlib.sha256
        ).hexdigest()
        if hmac.compare_digest(digest, signature):
            return

    log.warning("webhook rejected: authentication failed")
    raise HTTPException(status_code=401, detail="Invalid webhook credentials")


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "selfheal"}


def _handle(payload: dict, provider: str) -> dict:
    try:
        event = parse_webhook(
            payload, provider=provider, event_type="ci.failure"
        )
    except TypeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # The caller may not point the engine at an arbitrary directory:
    # SELFHEAL_PROJECT_PATH (server-configured) wins; otherwise the requested
    # path must be inside SELFHEAL_ALLOWED_ROOTS (default: the current directory).
    configured = os.getenv("SELFHEAL_PROJECT_PATH")
    try:
        project_root = (
            Path(configured).resolve()
            if configured
            else ensure_allowed(event.payload.get("project_path") or ".")
        )
    except ValueError as exc:
        log.warning("webhook rejected: %s", exc)
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    event.payload["project_path"] = str(project_root)

    incident_id = str(event.payload.get("incident_id") or uuid.uuid4())
    event.payload["incident_id"] = incident_id

    logs = str(event.payload.get("logs", "CI failure"))
    diag = diagnose(logs)

    incident_manager.create(
        Incident(
            source=provider,
            code=diag.error_type if diag.error_type != "unknown" else "ci.failure",
            message=logs,
            file_path=diag.file_path,
            line=diag.line_number,
        )
    )
    healing_event = incident_detected(incident_id)
    log.info("incident=%s created provider=%s", incident_id, provider)

    policy = RepairPolicy(
        allow_auto_apply=bool(event.payload.get("auto_heal", False))
    )

    try:
        workflow_result = process_ci_failure(
            event.payload,
            incident_id=incident_id,
            provider=provider,
            project_path=str(project_root),
            policy=policy,
        )
    except Exception as exc:  # never crash the webhook on a repair error
        log.exception("incident=%s workflow failed", incident_id)
        workflow_result = {"status": "error", "error": str(exc)}

    return {
        "received": True,
        "event": asdict(event),
        "healing_event": asdict(healing_event),
        "workflow": workflow_result,
    }


@app.post("/webhook")
async def webhook(
    request: Request,
    x_selfheal_token: str | None = Header(default=None),
    x_hub_signature_256: str | None = Header(default=None),
    x_github_event: str | None = Header(default=None),
) -> dict:
    raw = await request.body()
    _authenticate(raw, x_selfheal_token, x_hub_signature_256)

    try:
        payload = json.loads(raw or b"null")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON body") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=422, detail="Payload must be a JSON object")

    provider = "generic"
    if x_github_event or "workflow_run" in payload:
        provider = "github"
        payload = normalize_github_payload(payload)

    return await run_in_threadpool(_handle, payload, provider)


@app.get("/incidents")
def incidents() -> dict:
    return {
        "incidents": [
            {
                "status": record.status,
                "created_at": record.created_at,
                "code": record.incident.code,
                "file_path": record.incident.file_path,
                "line": record.incident.line,
            }
            for record in incident_manager.list_open()
        ]
    }
