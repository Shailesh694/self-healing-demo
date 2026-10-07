from pathlib import Path

from selfheal.regression_snapshot import (
    check_result_from_verification,
    snapshot_files,
)


def test_snapshot_files_captures_text_files(tmp_path: Path):
    target = tmp_path / "app.py"
    target.write_text(
        "print('hello')\n",
        encoding="utf-8",
    )

    snapshots = snapshot_files(str(tmp_path))

    assert len(snapshots) == 1
    assert snapshots[0].path == "app.py"
    assert snapshots[0].content == "print('hello')\n"


def test_snapshot_files_ignores_git_directory(tmp_path: Path):
    git_file = tmp_path / ".git" / "config"
    git_file.parent.mkdir()
    git_file.write_text(
        "internal",
        encoding="utf-8",
    )

    snapshots = snapshot_files(str(tmp_path))

    assert snapshots == []


def test_check_result_from_verification():
    result = check_result_from_verification(
        name="pytest",
        passed=True,
        return_code=0,
        output="3 passed",
    )

    assert result.name == "pytest"
    assert result.passed is True
    assert result.return_code == 0
    assert result.stdout == "3 passed"
    assert result.stderr == ""