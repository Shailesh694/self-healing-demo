from unittest.mock import MagicMock

from selfheal.agents.gemini import GeminiClient
from selfheal.agents.surveyor import SurveyorAgent, SurveyorFinding
from selfheal.config import SelfHealConfig


def test_surveyor_returns_structured_finding():
    config = SelfHealConfig(
        gemini_enabled=True,
        gemini_api_key="test-key",
    )

    gemini = GeminiClient(config)

    mock_response = MagicMock()
    mock_response.text = """
    {
        "root_cause": "Undefined variable used in app.py",
        "affected_files": ["app.py"],
        "affected_symbols": [],
        "relevant_tests": ["test_app.py"],
        "explanation": "The variable is referenced before definition.",
        "confidence": 0.94
    }
    """

    gemini._client.models.generate_content = MagicMock(
        return_value=mock_response
    )

    surveyor = SurveyorAgent(gemini)

    result = surveyor.analyze(
        incident="NameError: name 'foo' is not defined",
        repository_context='print(foo)',
        structural_context="app.py -> test_app.py",
    )

    assert result.success is True
    assert isinstance(result.response, SurveyorFinding)
    assert result.response.root_cause == "Undefined variable used in app.py"
    assert result.response.affected_files == ["app.py"]
    assert result.response.relevant_tests == ["test_app.py"]
    assert result.response.confidence == 0.94


def test_surveyor_scrubs_secrets_before_model_call():
    config = SelfHealConfig(
        gemini_enabled=True,
        gemini_api_key="test-key",
    )

    gemini = GeminiClient(config)

    mock_response = MagicMock()
    mock_response.text = """
    {
        "root_cause": "Credential exposure",
        "affected_files": ["config.py"],
        "affected_symbols": [],
        "relevant_tests": [],
        "explanation": "A secret was found in supplied context.",
        "confidence": 0.80
    }
    """

    mock_generate = MagicMock(return_value=mock_response)
    gemini._client.models.generate_content = mock_generate

    surveyor = SurveyorAgent(gemini)

    secret = "api_key=super-secret-value-123456"

    result = surveyor.analyze(
        incident="Configuration failure",
        repository_context=secret,
    )

    assert result.success is True

    sent_prompt = mock_generate.call_args.kwargs["contents"]

    assert "super-secret-value-123456" not in sent_prompt
    assert "[REDACTED]" in sent_prompt


def test_surveyor_does_not_modify_repository_context():
    config = SelfHealConfig(
        gemini_enabled=False,
    )

    gemini = GeminiClient(config)
    surveyor = SurveyorAgent(gemini)

    repository_context = 'print(foo)'

    result = surveyor.analyze(
        incident="NameError",
        repository_context=repository_context,
    )

    assert result.success is False
    assert repository_context == 'print(foo)'