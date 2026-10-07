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

    assert repo._run(
        "add",
        "app.py",
    ).success

    assert repo._run(
        "commit",
        "-m",
        "initial",
    ).success

    return repo


def test_commit_preparation_commits_candidate(
    tmp_path: Path,
):
    repo = create_repo(tmp_path / "repo")

    file_path = tmp_path / "repo" / "app.py"

    file_path.write_text(
        "print('fixed')\n",
        encoding="utf-8",
    )

    result = repo.prepare_commit(
        "selfheal: apply verified repair"
    )

    assert result.success is True

    log = repo._run(
        "log",
        "-1",
        "--pretty=%s",
    )

    assert log.success is True
    assert log.stdout.strip() == (
        "selfheal: apply verified repair"
    )


def test_empty_commit_message_is_rejected(
    tmp_path: Path,
):
    repo = create_repo(tmp_path / "repo")

    try:
        repo.prepare_commit("")
        assert False, "Expected ValueError"
    except ValueError as exc:
        assert "Commit message" in str(exc)