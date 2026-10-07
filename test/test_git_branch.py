from pathlib import Path

import pytest

from selfheal.git import (
    GitRepository,
    validate_branch_name,
)


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

    return repo


def test_valid_branch_name_is_accepted():
    assert (
        validate_branch_name(
            "selfheal/fix-123"
        )
        == "selfheal/fix-123"
    )


def test_branch_can_be_created(tmp_path: Path):
    repo = create_repo(tmp_path / "repo")

    result = repo.create_branch(
        "selfheal/fix-123"
    )

    assert result.success is True

    current = repo.current_branch()

    assert current.success is True
    assert current.stdout.strip() == (
        "selfheal/fix-123"
    )


@pytest.mark.parametrize(
    "branch_name",
    [
        "",
        " ",
        "../evil",
        "feature..bad",
        "feature//bad",
        "/absolute",
        "feature/",
        "feature bad",
        "feature~bad",
        "feature^bad",
        "feature:bad",
        "feature?bad",
        "feature*bad",
        "feature[bad",
        "-unsafe",
    ],
)
def test_unsafe_branch_names_are_rejected(
    branch_name: str,
):
    with pytest.raises(ValueError):
        validate_branch_name(branch_name)