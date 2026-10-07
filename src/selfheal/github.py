from __future__ import annotations

from dataclasses import dataclass


@dataclass
class GitHubContext:
    repository: str
    branch: str
    commit: str
    workflow: str


def create_context(
    *,
    repository: str,
    branch: str,
    commit: str,
    workflow: str,
) -> GitHubContext:
    """
    Store GitHub Actions context needed by SelfHeal.
    """

    if not repository:
        raise ValueError("repository cannot be empty")

    return GitHubContext(
        repository=repository,
        branch=branch,
        commit=commit,
        workflow=workflow,
    )