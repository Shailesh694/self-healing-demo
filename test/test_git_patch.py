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
        "print('old')\n",
        encoding="utf-8",
    )

    assert repo._run("add", "app.py").success

    assert repo._run(
        "commit",
        "-m",
        "initial",
    ).success

    return repo


def test_valid_patch_is_applied(tmp_path: Path):
    repo = create_repo(tmp_path / "repo")

    patch = """\
diff --git a/app.py b/app.py
index 1234567..7654321 100644
--- a/app.py
+++ b/app.py
@@ -1 +1 @@
-print('old')
+print('new')
"""

    result = repo.apply_patch(patch)

    assert result.success is True

    content = (
        tmp_path
        / "repo"
        / "app.py"
    ).read_text(
        encoding="utf-8",
    )

    assert content == "print('new')\n"


def test_empty_patch_is_rejected(tmp_path: Path):
    repo = create_repo(tmp_path / "repo")

    try:
        repo.apply_patch("")
        assert False, "Expected ValueError"
    except ValueError as exc:
        assert "Patch cannot be empty" in str(exc)


def test_invalid_patch_is_rejected(tmp_path: Path):
    repo = create_repo(tmp_path / "repo")

    result = repo.apply_patch(
        "this is not a valid git patch"
    )

    assert result.success is False
    assert result.return_code != 0