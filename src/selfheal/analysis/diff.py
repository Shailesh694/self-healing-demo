from __future__ import annotations

from dataclasses import dataclass


@dataclass
class FileDiff:
    path: str
    additions: int
    deletions: int


@dataclass
class PatchFile:
    path: str
    old_path: str
    new_path: str
    hunks: list[str]


def parse_diff(diff_text: str) -> list[FileDiff]:
    """
    Parse a unified git diff and return basic change statistics.
    """
    results: list[FileDiff] = []

    current_file: str | None = None
    additions = 0
    deletions = 0

    for line in diff_text.splitlines():
        if line.startswith("+++ b/"):
            if current_file is not None:
                results.append(
                    FileDiff(
                        path=current_file,
                        additions=additions,
                        deletions=deletions,
                    )
                )

            current_file = line[6:]
            additions = 0
            deletions = 0

        elif line.startswith("+") and not line.startswith("+++"):
            additions += 1

        elif line.startswith("-") and not line.startswith("---"):
            deletions += 1

    if current_file is not None:
        results.append(
            FileDiff(
                path=current_file,
                additions=additions,
                deletions=deletions,
            )
        )

    return results


def parse_patch(patch_text: str) -> list[PatchFile]:
    """
    Parse the file-level structure of a unified git diff.

    This function intentionally does not apply the patch.
    It extracts the target paths and hunks so the executor
    can validate the patch before modifying a repository.
    """
    if not patch_text.strip():
        raise ValueError("Patch cannot be empty")

    lines = patch_text.splitlines()

    results: list[PatchFile] = []
    current: PatchFile | None = None
    current_hunk: list[str] | None = None

    for line in lines:
        if line.startswith("diff --git "):
            if current is not None:
                if current_hunk:
                    current.hunks.append("\n".join(current_hunk))
                results.append(current)

            parts = line.split()

            if len(parts) < 4:
                raise ValueError(
                    f"Malformed diff header: {line}"
                )

            old_path = parts[2][2:] if parts[2].startswith("a/") else parts[2]
            new_path = parts[3][2:] if parts[3].startswith("b/") else parts[3]

            current = PatchFile(
                path=new_path,
                old_path=old_path,
                new_path=new_path,
                hunks=[],
            )
            current_hunk = None

        elif line.startswith("@@ "):
            if current is None:
                raise ValueError(
                    "Patch hunk appears before a diff header"
                )

            if current_hunk:
                current.hunks.append("\n".join(current_hunk))

            current_hunk = [line]

        elif current is not None and current_hunk is not None:
            current_hunk.append(line)

    if current is not None:
        if current_hunk:
            current.hunks.append("\n".join(current_hunk))
        results.append(current)

    if not results:
        raise ValueError(
            "Patch does not contain a valid git diff"
        )

    for patch_file in results:
        if not patch_file.hunks:
            raise ValueError(
                f"Patch contains no hunks for {patch_file.path}"
            )

    return results