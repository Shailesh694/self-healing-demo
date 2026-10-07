from unittest.mock import MagicMock

from selfheal.agents.gemini import GeminiClient
from selfheal.agents.reviewer import (
    AdversarialReviewer,
    ReviewFinding,
)
from selfheal.config import SelfHealConfig


def test_reviewer_can_reject_dangerous_patch():
    config = SelfHealConfig(
        gemini_enabled=True,
        gemini_api_key="test-key",
    )

    gemini = GeminiClient(config)

    mock_response = MagicMock()
    mock_response.text = """
    {
        "approved": false,
        "risk_level": "HIGH",
        "issues": [
            "Patch changes behavior outside the incident scope.",
            "No regression test is provided."
        ],
        "required_changes": [
            "Limit the patch to the failing expression.",
            "Add a regression test."
        ],
        "explanation": "The proposed change is broader than necessary.",
        "confidence": 0.96
    }
    """

    gemini._client.models.generate_content = MagicMock(
        return_value=mock_response
    )

    reviewer = AdversarialReviewer(gemini)

    result = reviewer.review(
        incident="NameError: name 'foo' is not defined",
        surveyor_finding="Undefined variable foo",
        proposed_patch=(
            "--- a/app.py\n"
            "+++ b/app.py\n"
            "@@ -1 +1 @@\n"
            "-print(foo)\n"
            "+modify_entire_application()\n"
        ),
        repository_context="print(foo)",
    )

    assert result.success is True
    assert isinstance(result.response, ReviewFinding)
    assert result.response.approved is False
    assert result.response.risk_level == "HIGH"
    assert len(result.response.issues) == 2


def test_reviewer_can_approve_safe_patch():
    config = SelfHealConfig(
        gemini_enabled=True,
        gemini_api_key="test-key",
    )

    gemini = GeminiClient(config)

    mock_response = MagicMock()
    mock_response.text = """
    {
        "approved": true,
        "risk_level": "LOW",
        "issues": [],
        "required_changes": [],
        "explanation": "The patch is minimal and directly addresses the incident.",
        "confidence": 0.92
    }
    """

    gemini._client.models.generate_content = MagicMock(
        return_value=mock_response
    )

    reviewer = AdversarialReviewer(gemini)

    result = reviewer.review(
        incident="NameError: name 'foo' is not defined",
        surveyor_finding="Undefined variable foo",
        proposed_patch=(
            "--- a/app.py\n"
            "+++ b/app.py\n"
            "@@ -1 +1 @@\n"
            "-print(foo)\n"
            "+print(\"fixed\")\n"
        ),
        repository_context="print(foo)",
    )

    assert result.success is True
    assert isinstance(result.response, ReviewFinding)
    assert result.response.approved is True
    assert result.response.risk_level == "LOW"


def test_reviewer_scrubs_secrets_before_model_call():
    config = SelfHealConfig(
        gemini_enabled=True,
        gemini_api_key="test-key",
    )

    gemini = GeminiClient(config)

    mock_response = MagicMock()
    mock_response.text = """
    {
        "approved": false,
        "risk_level": "HIGH",
        "issues": ["Credential exposure detected."],
        "required_changes": ["Remove the credential."],
        "explanation": "The patch contains a secret.",
        "confidence": 0.99
    }
    """

    mock_generate = MagicMock(return_value=mock_response)
    gemini._client.models.generate_content = mock_generate

    reviewer = AdversarialReviewer(gemini)

    secret = "api_key=super-secret-value-123456"

    result = reviewer.review(
        incident="Configuration failure",
        surveyor_finding="Credential exposure",
        proposed_patch=secret,
        repository_context=secret,
    )

    assert result.success is True

    sent_prompt = mock_generate.call_args.kwargs["contents"]

    assert "super-secret-value-123456" not in sent_prompt
    assert "[REDACTED]" in sent_prompt