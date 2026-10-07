from pathlib import Path
from unittest.mock import MagicMock

from selfheal.agents.coder import CoderAgent, CoderPatch
from selfheal.agents.gemini import GeminiClient
from selfheal.config import SelfHealConfig


def test_coder_returns_structured_patch():
    config = SelfHealConfig(
        gemini_enabled=True,
        gemini_api_key="test-key",
    )

    gemini = GeminiClient(config)

    mock_response = MagicMock()
    mock_response.text = """
    {
        "summary": "Replace undefined variable with fixed value",
        "patch": "--- a/app.py\\n+++ b/app.py\\n@@ -1 +1 @@\\n-print(foo)\\n+print(\\\"fixed\\\")",
        "target_files": ["app.py"],
        "explanation": "The undefined variable causes the NameError.",
        "confidence": 0.93
    }
    """

    gemini._client.models.generate_content = MagicMock(
        return_value=mock_response
    )

    coder = CoderAgent(gemini)

    result = coder.generate_patch(
        incident="NameError: name 'foo' is not defined",
        surveyor_finding="Undefined variable foo in app.py",
        repository_context='print(foo)',
        structural_context="app.py -> test_app.py",
    )

    assert result.success is True
    assert isinstance(result.response, CoderPatch)
    assert result.response.target_files == ["app.py"]
    assert "print(\"fixed\")" in result.response.patch
    assert result.response.confidence == 0.93


def test_coder_scrubs_secrets_before_model_call():
    config = SelfHealConfig(
        gemini_enabled=True,
        gemini_api_key="test-key",
    )

    gemini = GeminiClient(config)

    mock_response = MagicMock()
    mock_response.text = """
    {
        "summary": "Fix configuration",
        "patch": "--- a/config.py\\n+++ b/config.py",
        "target_files": ["config.py"],
        "explanation": "Configuration requires correction.",
        "confidence": 0.80
    }
    """

    mock_generate = MagicMock(return_value=mock_response)
    gemini._client.models.generate_content = mock_generate

    coder = CoderAgent(gemini)

    secret = "api_key=super-secret-value-123456"

    result = coder.generate_patch(
        incident="Configuration failure",
        surveyor_finding="Credential exposure",
        repository_context=secret,
    )

    assert result.success is True

    sent_prompt = mock_generate.call_args.kwargs["contents"]

    assert "super-secret-value-123456" not in sent_prompt
    assert "[REDACTED]" in sent_prompt


def test_coder_does_not_modify_repository(tmp_path: Path):
    app_file = tmp_path / "app.py"
    original_content = "print(foo)\n"
    app_file.write_text(original_content)

    config = SelfHealConfig(
        gemini_enabled=True,
        gemini_api_key="test-key",
    )

    gemini = GeminiClient(config)

    mock_response = MagicMock()
    mock_response.text = """
    {
        "summary": "Fix undefined variable",
        "patch": "--- a/app.py\\n+++ b/app.py\\n@@ -1 +1 @@\\n-print(foo)\\n+print(\\\"fixed\\\")",
        "target_files": ["app.py"],
        "explanation": "Fixes the undefined variable.",
        "confidence": 0.90
    }
    """

    gemini._client.models.generate_content = MagicMock(
        return_value=mock_response
    )

    coder = CoderAgent(gemini)

    result = coder.generate_patch(
        incident="NameError",
        surveyor_finding="Undefined variable",
        repository_context=original_content,
    )

    assert result.success is True
    assert app_file.read_text() == original_content