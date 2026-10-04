from pathlib import Path

import pytest

from selfheal.git import GitRepository


def init_repository(path: Path) -> GitRepository:
    path.mkdir()

    repo = GitRepository(path)

    result = repo._run(
        "init",
    )

    assert result.success is True

    repo._run(
        "config",
        "user.email",
        "test@example.com",
    )

    repo._run(
        "config",
        "user.name",
        "SelfHeal Test",
    )

    return repo


def test_status_works(tmp_path: Path):
    repo = init_repository(tmp_path / "repo")

    result = repo.status()

    assert result.success is True


def test_current_branch_returns_branch(tmp_path: Path):
    repo = init_repository(tmp_path / "repo")

    result = repo.current_branch()

    assert result.success is True


def test_diff_detects_file_change(tmp_path: Path):
    repo = init_repository(tmp_path / "repo")

    file_path = tmp_path / "repo" / "app.py"

    file_path.write_text(
        "print('hello')\n",
        encoding="utf-8",
    )

    repo._run("add", "app.py")
    repo._run(
        "commit",
        "-m",
        "initial",
    )

    file_path.write_text(
        "print('changed')\n",
        encoding="utf-8",
    )

    result = repo.diff()

    assert result.success is True
    assert "changed" in result.stdout


def test_empty_branch_name_is_rejected(tmp_path: Path):
    repo = init_repository(tmp_path / "repo")

    with pytest.raises(ValueError):
        repo.create_branch("")


def test_empty_patch_is_rejected(tmp_path: Path):
    repo = init_repository(tmp_path / "repo")

    with pytest.raises(ValueError):
        repo.apply_patch("")


def test_empty_commit_message_is_rejected(tmp_path: Path):
    repo = init_repository(tmp_path / "repo")

    with pytest.raises(ValueError):
        repo.prepare_commit("")