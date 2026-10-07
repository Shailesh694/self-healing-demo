"""Live check of the Gemini integration. Run: python scripts/smoke_live.py (needs GEMINI_API_KEY)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

os.environ.setdefault("SELFHEAL_GEMINI_ENABLED", "true")

from selfheal.agents.gemini import GeminiClient  # noqa: E402
from selfheal.config import SelfHealConfig  # noqa: E402

config = SelfHealConfig.from_environment()
if not config.gemini_api_key:
    sys.exit("Set GEMINI_API_KEY first.")
result = GeminiClient(config).generate_json(
    'Reply as JSON: response_type="ping", summary="ok", confidence=1.0, data=[]'
)
print("success:", result.success, "| error:", result.error)
print(result.response)
sys.exit(0 if result.success else 1)
