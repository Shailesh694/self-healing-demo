from unittest.mock import MagicMock

from selfheal.agents.gemini import GeminiClient, GeminiResponse
from selfheal.config import SelfHealConfig


def test_gemini_disabled_by_default():
    config = SelfHealConfig()

    client = GeminiClient(config)

    result = client.generate_json("test prompt")

    assert result.success is False
    assert result.error == "Gemini is disabled by configuration."


def test_gemini_requires_api_key():
    config = SelfHealConfig(
        gemini_enabled=True,
        gemini_api_key=None,
    )

    client = GeminiClient(config)

    result = client.generate_json("test prompt")

    assert result.success is False
    assert result.error == "GEMINI_API_KEY is not configured."


def test_gemini_accepts_valid_structured_response():
    config = SelfHealConfig(
        gemini_enabled=True,
        gemini_api_key="test-key",
    )

    client = GeminiClient(config)

    mock_response = MagicMock()
    mock_response.text = """
    {
        "response_type": "analysis",
        "summary": "A likely missing import was detected.",
        "confidence": 0.91,
        "data": [
            "file: app.py",
            "line: 1"
        ]
    }
    """

    client._client.models.generate_content = MagicMock(
        return_value=mock_response
    )

    result = client.generate_json("Analyze this incident.")

    assert result.success is True
    assert isinstance(result.response, GeminiResponse)
    assert result.response.response_type == "analysis"
    assert result.response.confidence == 0.91
    assert "file: app.py" in result.response.data
    assert "line: 1" in result.response.data


def test_gemini_rejects_invalid_structured_response():
    config = SelfHealConfig(
        gemini_enabled=True,
        gemini_api_key="test-key",
    )

    client = GeminiClient(config)

    mock_response = MagicMock()
    mock_response.text = """
    {
        "response_type": "analysis",
        "summary": "Invalid confidence",
        "confidence": "not-a-number",
        "data": {}
    }
    """

    client._client.models.generate_content = MagicMock(
        return_value=mock_response
    )

    result = client.generate_json("Analyze this incident.")

    assert result.success is False
    assert result.error is not None
    assert "validation" in result.error.lower()

def test_gemini_does_not_retry_quota_exhausted_429():
    config = SelfHealConfig(
        gemini_enabled=True,
        gemini_api_key="test-key",
    )

    client = GeminiClient(config)

    client._client.models.generate_content = MagicMock(
        side_effect=Exception(
            "429 RESOURCE_EXHAUSTED: quota exceeded"
        )
    )

    result = client.generate_json("Analyze this incident.")

    assert result.success is False
    assert "RESOURCE_EXHAUSTED" in result.error
    assert client._client.models.generate_content.call_count == 1