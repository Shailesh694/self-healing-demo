from __future__ import annotations

import difflib
import re
from pathlib import Path


NAME_ERROR_PATTERN = re.compile(
    r"name '([^']+)' is not defined"
)

PRINT_NAME_PATTERN = re.compile(
    r'^(\s*)print\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*\)\s*$'
)


def generate_repair_patch(
    *,
    file_path: str,
    error_type: str,
    message: str,
    line_number: int | None,
) -> str | None:
    """
    Generate a conservative unified diff for a supported NameError.

    Supported demonstration case:

        print(foo)

    when the CI diagnostic reports:

        NameError: name 'foo' is not defined

    The function never modifies the target file.
    """

    if error_type != "NameError":
        return None

    if line_number is None:
        return None

    match = NAME_ERROR_PATTERN.search(message)

    if not match:
        return None

    missing_name = match.group(1)

    if not missing_name.isidentifier():
        return None

    path = Path(file_path)

    if not path.exists() or not path.is_file():
        return None

    lines = path.read_text(
        encoding="utf-8"
    ).splitlines(keepends=True)

    index = line_number - 1

    if index < 0 or index >= len(lines):
        return None

    original_line = lines[index]

    line_without_newline = original_line.rstrip("\r\n")

    print_match = PRINT_NAME_PATTERN.match(
        line_without_newline
    )

    if not print_match:
        return None

    indentation = print_match.group(1)
    referenced_name = print_match.group(2)

    if referenced_name != missing_name:
        return None

    replacement_line = (
        f'{indentation}print("fixed")\n'
    )

    if original_line.endswith("\r\n"):
        replacement_line = (
            f'{indentation}print("fixed")\r\n'
        )
    elif not original_line.endswith("\n"):
        replacement_line = (
            f'{indentation}print("fixed")'
        )

    updated_lines = list(lines)
    updated_lines[index] = replacement_line

    diff = difflib.unified_diff(
        lines,
        updated_lines,
        fromfile=f"a/{path.name}",
        tofile=f"b/{path.name}",
        n=3,
    )

    diff_text = "".join(diff)

    if not diff_text:
        return None

    git_header = (
        f"diff --git a/{path.name} b/{path.name}\n"
    )

    return git_header + diff_text