from __future__ import annotations

from pathlib import Path


def restore_file(
    *,
    file_path: str,
    original_content: str,
) -> bool:
    """
    Restore a file to its original content.
    """

    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(
            f"Cannot restore missing file: {file_path}"
        )

    path.write_text(
        original_content,
        encoding="utf-8",
    )

    return True