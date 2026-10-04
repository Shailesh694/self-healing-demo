from __future__ import annotations

from .incident_manager import IncidentManager


# Shared runtime state for the API and MCP layers.
#
# Keeping this instance in a top-level module prevents the
# FastAPI server and MCP tools from maintaining separate
# incident stores.
incident_manager = IncidentManager()