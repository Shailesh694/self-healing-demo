from __future__ import annotations

from dataclasses import asdict

from fastapi import FastAPI, HTTPException

from .events import incident_detected
from .incident_manager import IncidentManager
from .models import Incident
from .policy import RepairPolicy
from .webhook import parse_webhook
from .workflow import process_ci_failure


app = FastAPI(
    title="SelfHeal CI/CD",
    version="0.1.0",
)

incident_manager = IncidentManager()


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "service": "selfheal",
    }


@app.post("/webhook")
def webhook(payload: dict) -> dict:
    try:
        event = parse_webhook(
            payload,
            provider="generic",
            event_type="ci.failure",
        )
    except TypeError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    incident_id = str(
        event.payload.get(
            "incident_id",
            "unknown",
        )
    )

    incident = Incident(
        source="generic",
        code="ci.failure",
        message=str(
            event.payload.get(
                "logs",
                "CI failure",
            )
        ),
    )

    incident_manager.create(incident)

    healing_event = incident_detected(
        incident_id
    )

    auto_heal = bool(
        event.payload.get(
            "auto_heal",
            False,
        )
    )

    policy = RepairPolicy(
        allow_auto_apply=auto_heal,
    )

    workflow_result = process_ci_failure(
        event.payload,
        incident_id=incident_id,
        provider="generic",
        project_path=str(
            event.payload.get(
                "project_path",
                ".",
            )
        ),
        policy=policy,
    )

    return {
        "received": True,
        "event": asdict(event),
        "healing_event": asdict(healing_event),
        "workflow": workflow_result,
    }


@app.get("/incidents")
def incidents() -> dict:
    return {
        "incidents": [
            {
                "status": record.status,
                "created_at": record.created_at,
            }
            for record in incident_manager.list_open()
        ]
    }