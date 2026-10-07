from selfheal.agents.orchestrator import AgentOrchestrator


class FakeSurveyor:
    def analyze(
        self,
        *,
        incident,
        repository_context,
        structural_context="",
    ):
        return "survey finding"


class FakeCoder:
    def generate_patch(
        self,
        *,
        incident,
        surveyor_finding,
        repository_context,
        structural_context="",
    ):
        return "candidate patch"


class FakeReviewer:
    def review(
        self,
        *,
        incident,
        surveyor_finding,
        proposed_patch,
        repository_context,
        structural_context="",
    ):
        return "review finding"


def test_agent_orchestrator_runs_agents_in_order():
    orchestrator = AgentOrchestrator(
        surveyor=FakeSurveyor(),
        coder=FakeCoder(),
        reviewer=FakeReviewer(),
    )

    result = orchestrator.run(
        incident="NameError in app.py",
        repository_context="app.py contains foo()",
        structural_context="function foo",
    )

    assert result.survey == "survey finding"
    assert result.candidate == "candidate patch"
    assert result.review == "review finding"

class RecordingReviewer:
    def __init__(self):
        self.proposed_patch = None

    def review(
        self,
        *,
        incident,
        surveyor_finding,
        proposed_patch,
        repository_context,
        structural_context="",
    ):
        self.proposed_patch = proposed_patch
        return "review"


def test_agent_orchestrator_passes_candidate_to_reviewer():
    reviewer = RecordingReviewer()

    orchestrator = AgentOrchestrator(
        surveyor=FakeSurveyor(),
        coder=FakeCoder(),
        reviewer=reviewer,
    )

    orchestrator.run(
        incident="failure",
        repository_context="context",
    )

    assert reviewer.proposed_patch == "candidate patch"

class FakeGeminiResult:
    def __init__(self, text):
        self.text = text


class StructuredSurveyor:
    def analyze(
        self,
        *,
        incident,
        repository_context,
        structural_context="",
    ):
        return FakeGeminiResult("ROOT CAUSE: missing symbol")


class RecordingCoder:
    def __init__(self):
        self.surveyor_finding = None

    def generate_patch(
        self,
        *,
        incident,
        surveyor_finding,
        repository_context,
        structural_context="",
    ):
        self.surveyor_finding = surveyor_finding
        return FakeGeminiResult("diff --git a/app.py b/app.py")


class RecordingReviewer:
    def __init__(self):
        self.proposed_patch = None

    def review(
        self,
        *,
        incident,
        surveyor_finding,
        proposed_patch,
        repository_context,
        structural_context="",
    ):
        self.proposed_patch = proposed_patch
        return FakeGeminiResult("approved=false")


def test_orchestrator_passes_gemini_text_between_agents():
    coder = RecordingCoder()
    reviewer = RecordingReviewer()

    orchestrator = AgentOrchestrator(
        surveyor=StructuredSurveyor(),
        coder=coder,
        reviewer=reviewer,
    )

    result = orchestrator.run(
        incident="failure",
        repository_context="app.py",
    )

    assert coder.surveyor_finding == "ROOT CAUSE: missing symbol"
    assert reviewer.proposed_patch == "diff --git a/app.py b/app.py"
    assert result.review.text == "approved=false"