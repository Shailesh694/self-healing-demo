from __future__ import annotations

import os
import sys

from .incident_manager import IncidentManager

# Shared runtime state for the API and MCP layers.
#
# The package can be imported as `src.selfheal` (uvicorn) or `selfheal`
# (MCP / tests). Python treats these as different modules, so a plain
# module-level instance would be duplicated. The instance is therefore
# registered once under a path-independent key in sys.modules.
_KEY = "_selfheal_shared_incident_manager"

if _KEY not in sys.modules:
    sys.modules[_KEY] = IncidentManager(os.getenv("SELFHEAL_STATE_FILE"))  # type: ignore[assignment]

incident_manager: IncidentManager = sys.modules[_KEY]  # type: ignore[assignment]
