from pathlib import Path

from selfheal.sandbox.executor import SandboxExecutor


def test_sandbox_runs_command_without_modifying_source(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()

    source_file = project / "app.py"
    source_file.write_text(
        "print('original')\n",
        encoding="utf-8",
    )

    executor = SandboxExecutor(timeout_seconds=10)

    result = executor.run(
        source_path=project,
        command=[
            "python",
            "-c",
            "from pathlib import Path; "
            "Path('app.py').write_text('modified'); "
            "print(Path('app.py').read_text())",
        ],
    )

    assert result.passed is True
    assert "modified" in result.stdout

    # The real repository copy must remain untouched.
    assert source_file.read_text(
        encoding="utf-8"
    ) == "print('original')\n"


def test_sandbox_captures_failure(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()

    executor = SandboxExecutor(timeout_seconds=10)

    result = executor.run(
        source_path=project,
        command=[
            "python",
            "-c",
            "print('failure-output'); raise SystemExit(3)",
        ],
    )

    assert result.passed is False
    assert result.return_code == 3
    assert "failure-output" in result.stdout
    assert result.timed_out is False


def test_sandbox_enforces_timeout(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()

    executor = SandboxExecutor(timeout_seconds=1)

    result = executor.run(
        source_path=project,
        command=[
            "python",
            "-c",
            "import time; time.sleep(5)",
        ],
    )

    assert result.passed is False
    assert result.timed_out is True


def test_sandbox_rejects_empty_command(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()

    executor = SandboxExecutor()

    try:
        executor.run(
            source_path=project,
            command=[],
        )
        assert False, "Expected ValueError"
    except ValueError as exc:
        assert "command cannot be empty" in str(exc)