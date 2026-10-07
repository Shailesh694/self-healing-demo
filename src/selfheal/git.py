from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path


# Shared by every `git apply` call in the project (CRLF-safe on Windows).
GIT_APPLY_FLAGS = ("--ignore-whitespace",)



@dataclass(frozen=True)
class GitResult:
    """Result of a Git command."""

    success: bool
    return_code: int
    stdout: str
    stderr: str


def validate_branch_name(branch_name: str) -> str:
    """
    Validate a branch name before passing it to Git.
    """

    if not branch_name.strip():
        raise ValueError(
            "Branch name cannot be empty"
        )

    if branch_name != branch_name.strip():
        raise ValueError(
            "Branch name cannot contain leading or trailing whitespace"
        )

    if branch_name.startswith("-"):
        raise ValueError(
            "Branch name cannot start with '-'"
        )

    if branch_name.startswith("/"):
        raise ValueError(
            "Branch name cannot start with '/'"
        )

    if branch_name.endswith("/"):
        raise ValueError(
            "Branch name cannot end with '/'"
        )

    if ".." in branch_name:
        raise ValueError(
            "Branch name cannot contain '..'"
        )

    if "//" in branch_name:
        raise ValueError(
            "Branch name cannot contain consecutive '/'"
        )

    if "@{" in branch_name:
        raise ValueError(
            "Branch name cannot contain '@{'"
        )

    if any(
        character in branch_name
        for character in [
            " ",
            "~",
            "^",
            ":",
            "?",
            "*",
            "[",
            "\\",
        ]
    ):
        raise ValueError(
            "Branch name contains an invalid character"
        )

    if not re.fullmatch(
        r"[A-Za-z0-9._/-]+",
        branch_name,
    ):
        raise ValueError(
            "Branch name contains invalid characters"
        )

    return branch_name


class GitRepository:
    """
    Thin deterministic abstraction over Git.

    This class does not decide whether a remediation is safe.
    Policy and verification remain separate concerns.
    """

    def __init__(
        self,
        repository_path: str | Path,
    ):
        self.repository_path = Path(
            repository_path
        ).resolve()

        if not self.repository_path.exists():
            raise FileNotFoundError(
                f"Repository path does not exist: "
                f"{self.repository_path}"
            )

    def _run(
        self,
        *args: str,
    ) -> GitResult:
        result = subprocess.run(
            ["git", *args],
            cwd=self.repository_path,
            capture_output=True,
            text=True,
        )

        return GitResult(
            success=result.returncode == 0,
            return_code=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
        )

    def status(self) -> GitResult:
        return self._run(
            "status",
            "--short",
        )

    def diff(self) -> GitResult:
        return self._run(
            "diff",
        )

    def current_branch(self) -> GitResult:
        return self._run(
            "branch",
            "--show-current",
        )

    def create_branch(
        self,
        branch_name: str,
    ) -> GitResult:
        branch_name = validate_branch_name(
            branch_name
        )

        return self._run(
            "switch",
            "-c",
            branch_name,
        )

    def apply_patch(
        self,
        patch: str,
    ) -> GitResult:
        """
        Apply a unified Git patch to the repository.

        The patch is passed through stdin to `git apply`.
        """

        if not patch.strip():
            raise ValueError(
                "Patch cannot be empty"
            )

        return subprocess_result_from_patch(
            self.repository_path,
            patch,
        )

    def checkpoint(
        self,
        message: str = "selfheal checkpoint",
    ) -> GitResult:
        """
        Save the current working-tree state.

        Git stash is used so the repository can return to
        a clean state before remediation continues.
        """

        if not message.strip():
            raise ValueError(
                "Checkpoint message cannot be empty"
            )

        return self._run(
            "stash",
            "push",
            "-u",
            "-m",
            message,
        )

    def rollback(self) -> GitResult:
        """
        Restore tracked files to HEAD.

        This intentionally does not make policy decisions.
        """

        return self._run(
            "reset",
            "--hard",
            "HEAD",
        )

    def checkout(self, branch_name: str) -> GitResult:
        return self._run("switch", validate_branch_name(branch_name))

    def delete_branch(self, branch_name: str) -> GitResult:
        return self._run("branch", "-D", validate_branch_name(branch_name))

    def branch_name(self) -> str:
        return self.current_branch().stdout.strip()

    def is_repository(self) -> bool:
        return self._run(
            "rev-parse", "--is-inside-work-tree"
        ).success

    def has_tracked_changes(self) -> bool:
        """True if tracked files have uncommitted changes."""
        result = self._run(
            "status", "--porcelain", "--untracked-files=no"
        )
        return (not result.success) or bool(result.stdout.strip())

    def prepare_commit(
        self,
        message: str,
    ) -> GitResult:
        """
        Create a commit for the current tracked changes.

        The caller is responsible for deciding whether the
        candidate has passed verification and policy checks.
        """

        if not message.strip():
            raise ValueError(
                "Commit message cannot be empty"
            )

        return self._run(
            "commit",
            "-am",
            message,
        )


def subprocess_result_from_patch(
    repository_path: Path,
    patch: str,
) -> GitResult:
    """
    Apply a unified patch using git apply.
    """

    result = subprocess.run(
        [
            "git",
            "apply",
            *GIT_APPLY_FLAGS,
            "-",
        ],
        cwd=repository_path,
        input=patch,
        capture_output=True,
        text=True,
    )

    return GitResult(
        success=result.returncode == 0,
        return_code=result.returncode,
        stdout=result.stdout,
        stderr=result.stderr,
    )