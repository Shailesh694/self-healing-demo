from pathlib import Path

from selfheal.sandbox.verification import SandboxVerifier


def test_verification_passes(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()

    verifier = SandboxVerifier(timeout_seconds=10)

    result = verifier.verify(
        repository_path=project,
        command=[
            "python",
            "-c",
            "print('verification passed')",
        ],
    )

    assert result.passed is True
    assert result.command == (
        "python",
        "-c",
        "print('verification passed')",
    )
    assert "verification passed" in result.sandbox_result.stdout


def test_verification_fails(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()

    verifier = SandboxVerifier(timeout_seconds=10)

    result = verifier.verify(
        repository_path=project,
        command=[
            "python",
            "-c",
            "raise SystemExit(2)",
        ],
    )

    assert result.passed is False
    assert result.sandbox_result.return_code == 2


def test_verification_rejects_empty_command(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()

    verifier = SandboxVerifier()

    try:
        verifier.verify(
            repository_path=project,
            command=[],
        )
        assert False, "Expected ValueError"
    except ValueError as exc:
        assert "command cannot be empty" in str(exc)