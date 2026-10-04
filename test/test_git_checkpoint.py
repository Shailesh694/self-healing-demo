from pathlib import Path

from selfheal.git import GitRepository


def create_repo(path: Path) -> GitRepository:
    path.mkdir()

    repo = GitRepository(path)

    assert repo._run("init").success

    assert repo._run(
        "config",
        "user.email",
        "test@example.com",
    ).success

    assert repo._run(
        "config",
        "user.name",
        "SelfHeal Test",
    ).success

    file_path = path / "app.py"
    file_path.write_text(
        "print('original')\n",
        encoding="utf-8",
    )

    assert repo._run("add", "app.py").success
    assert repo._run(
        "commit",
        "-m",
        "initial",
    ).success

    return repo


def test_checkpoint_stashes_working_changes(tmp_path: Path):
    repo = create_repo(tmp_path / "repo")

    file_path = tmp_path / "repo" / "app.py"

    file_path.write_text(
        "print('candidate')\n",
        encoding="utf-8",
    )

    result = repo.checkpoint(
        "before self-healing",
    )

    assert result.success is True

    status = repo.status()

    assert status.success is True
    assert status.stdout.strip() == ""


def test_rollback_restores_head_state(tmp_path: Path):
    repo = create_repo(tmp_path / "repo")

    file_path = tmp_path / "repo" / "app.py"

    file_path.write_text(
        "print('bad candidate')\n",
        encoding="utf-8",
    )

    result = repo.rollback()

    assert result.success is True

    assert file_path.read_text(
        encoding="utf-8",
    ) == "print('original')\n"


def test_checkpoint_rejects_empty_message(tmp_path: Path):
    repo = create_repo(tmp_path / "repo")

    try:
        repo.checkpoint("")
        assert False, "Expected ValueError"
    except ValueError as exc:
        assert "Checkpoint message" in str(exc)
        