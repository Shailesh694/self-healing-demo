from __future__ import annotations


import subprocess
from pathlib import Path

from .diff import parse_patch


def apply_patch(
    *,
    file_path: str,
    patch: str,
    dry_run: bool = True,
) -> bool:
    """
    Apply a unified git diff to a target file.

    Works both inside and outside a Git repository.
    """

    path = Path(file_path).resolve()

    if not path.exists():
        raise FileNotFoundError(
            f"Target file does not exist: {file_path}"
        )

    if not patch.strip():
        raise ValueError("Patch cannot be empty")

    patch_files = parse_patch(patch)

    if len(patch_files) != 1:
        raise ValueError(
            "Patch must modify exactly one file"
        )

    patch_file = patch_files[0]

    if patch_file.new_path not in {
        path.as_posix(),
        path.name,
    }:
        raise ValueError(
            "Patch target does not match requested file: "
            f"{patch_file.new_path}"
        )

    if dry_run:
        return True

    # First try normal Git application when the target
    # belongs to a Git repository.
    git_root_result = subprocess.run(
        [
            "git",
            "rev-parse",
            "--show-toplevel",
        ],
        cwd=path.parent,
        capture_output=True,
        text=True,
    )

    if git_root_result.returncode == 0:
        git_root = Path(
            git_root_result.stdout.strip()
        ).resolve()

        try:
            relative_parent = path.parent.relative_to(
                git_root
            )
        except ValueError:
            relative_parent = Path(".")

        command = [
            "git",
            "apply",
            "--ignore-whitespace",
        ]

        if str(relative_parent) != ".":
            command.append(
                f"--directory={relative_parent.as_posix()}"
            )

        command.append("-")

        result = subprocess.run(
            command,
            input=patch,
            text=True,
            capture_output=True,
            cwd=git_root,
        )

        if result.returncode == 0:
            return True

        raise ValueError(
            "Patch could not be applied: "
            + result.stderr.strip()
        )

    # Temporary test projects may not be Git repositories.
    # In that case, apply the unified diff directly to the
    # requested file.
    old_text = path.read_text(
        encoding="utf-8"
    )

    lines = old_text.splitlines(
        keepends=True
    )

    old_lines: list[str] = []
    new_lines: list[str] = []

    for line in patch.splitlines():
        if line.startswith("--- ") or line.startswith("+++ "):
            continue

        if line.startswith("@@"):
            continue

        if line.startswith("-"):
            old_lines.append(line[1:] + "\n")

        elif line.startswith("+"):
            new_lines.append(line[1:] + "\n")

        elif line.startswith(" "):
            old_lines.append(line[1:] + "\n")
            new_lines.append(line[1:] + "\n")

    if not old_lines:
        raise ValueError(
            "Patch does not contain removable lines"
        )

    old_block = "".join(old_lines)
    new_block = "".join(new_lines)

    if old_block not in old_text:
        raise ValueError(
            "Patch context does not match target file"
        )

    updated_text = old_text.replace(
        old_block,
        new_block,
        1,
    )

    path.write_text(
        updated_text,
        encoding="utf-8",
    )

    return True