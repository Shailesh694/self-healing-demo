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


def _generate_name_error_patch(
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


def _diff_for(path: Path, before: list[str], after: list[str]) -> str | None:
    diff_text = "".join(
        difflib.unified_diff(
            before,
            after,
            fromfile=f"a/{path.name}",
            tofile=f"b/{path.name}",
            n=3,
        )
    )
    if not diff_text:
        return None
    return f"diff --git a/{path.name} b/{path.name}\n" + diff_text


def _read_lines(file_path: str, line_number: int | None):
    if line_number is None:
        return None
    path = Path(file_path)
    if not path.exists() or not path.is_file():
        return None
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    if not 1 <= line_number <= len(lines):
        return None
    return path, lines


UNUSED_IMPORT_PATTERN = re.compile(r"'([^']+)' imported but unused")
SIMPLE_IMPORT = re.compile(r"^\s*import\s+([\w.]+)\s*$")
SIMPLE_FROM_IMPORT = re.compile(r"^\s*from\s+[\w.]+\s+import\s+(\w+)\s*$")


def _generate_unused_import_patch(file_path, message, line_number):
    """Remove a single-name unused import reported by flake8 (F401)."""
    loaded = _read_lines(file_path, line_number)
    match = UNUSED_IMPORT_PATTERN.search(message)
    if loaded is None or not match:
        return None
    path, lines = loaded
    reported = match.group(1)
    index = line_number - 1
    line = lines[index].rstrip("\r\n")

    plain = SIMPLE_IMPORT.match(line)
    from_import = SIMPLE_FROM_IMPORT.match(line)
    if plain and plain.group(1) == reported:
        base = reported.split(".")[0]
    elif from_import and reported.endswith("." + from_import.group(1)):
        base = from_import.group(1)
    else:
        return None  # multi-name, aliased, or mismatched line: not safe

    import ast

    try:
        tree = ast.parse("".join(lines))
    except SyntaxError:
        return None
    if any(isinstance(n, ast.Name) and n.id == base for n in ast.walk(tree)):
        return None  # the name is actually used somewhere

    return _diff_for(path, lines, lines[:index] + lines[index + 1:])


def _generate_trailing_whitespace_patch(file_path, line_number):
    """Strip trailing whitespace on the reported line (W291 / W293)."""
    loaded = _read_lines(file_path, line_number)
    if loaded is None:
        return None
    path, lines = loaded
    index = line_number - 1
    original = lines[index]
    body = original.rstrip("\r\n")
    ending = original[len(body):]
    fixed = body.rstrip() + ending
    if fixed == original:
        return None
    updated = list(lines)
    updated[index] = fixed
    return _diff_for(path, lines, updated)


_OPERATORS = {
    "E225": re.compile(r"^(==|!=|<=|>=|\+=|-=|\*=|/=|=|<|>)"),
    "E226": re.compile(r"^(\*\*|//|\+|-|\*|/|@)"),   # arithmetic
    "E227": re.compile(r"^(<<|>>|&|\||\^)"),          # bitwise / shift
    "E228": re.compile(r"^(%)"),                       # modulo
}


def _still_valid_python(before: list[str], after: list[str]) -> bool:
    """A style fix must never turn a parseable file into an unparseable one."""
    import ast

    try:
        ast.parse("".join(before))
    except SyntaxError:
        return False
    try:
        ast.parse("".join(after))
    except SyntaxError:
        return False
    return True


def _generate_blank_lines_patch(file_path, message, line_number):
    """E302 / E305: insert the missing blank lines before the reported line."""
    loaded = _read_lines(file_path, line_number)
    match = re.search(r"expected (\d+) blank lines?.*?found (\d+)", message)
    if loaded is None or not match:
        return None
    needed = int(match.group(1)) - int(match.group(2))
    if needed <= 0 or needed > 2:
        return None
    path, lines = loaded
    index = line_number - 1
    after = lines[:index] + ["\n"] * needed + lines[index:]
    if not _still_valid_python(lines, after):
        return None
    return _diff_for(path, lines, after)


def _generate_space_after_patch(file_path, line_number, column):
    """E231: add a space after the ',' ';' or ':' at the reported column."""
    loaded = _read_lines(file_path, line_number)
    if loaded is None or not column:
        return None
    path, lines = loaded
    index = line_number - 1
    line = lines[index]
    pos = column - 1
    if pos >= len(line) or line[pos] not in ",;:":
        return None
    if pos + 1 < len(line) and line[pos + 1] in " \t\r\n":
        return None
    updated = list(lines)
    updated[index] = line[: pos + 1] + " " + line[pos + 1:]
    if not _still_valid_python(lines, updated):
        return None
    return _diff_for(path, lines, updated)


def _generate_operator_space_patch(file_path, line_number, column, code="E225"):
    """E225-E228: put a space on each side of the operator at the reported column."""
    loaded = _read_lines(file_path, line_number)
    if loaded is None or not column:
        return None
    path, lines = loaded
    index = line_number - 1
    line = lines[index]
    pos = column - 1
    match = _OPERATORS[code].match(line[pos:])
    if not match:
        return None
    op = match.group(1)
    before, after_text = line[:pos], line[pos + len(op):]
    lead = "" if before.endswith((" ", "\t")) else " "
    trail = "" if after_text[:1] in (" ", "\t", "\r", "\n") else " "
    updated = list(lines)
    updated[index] = before + lead + op + trail + after_text
    if updated[index] == line or not _still_valid_python(lines, updated):
        return None
    return _diff_for(path, lines, updated)


def generate_repair_patch(
    *,
    file_path: str,
    error_type: str,
    message: str,
    line_number: int | None,
    column: int | None = None,
) -> str | None:
    """
    Deterministic repair strategies. Supported:

    - NameError: ``print(foo)`` of an undefined name
    - F401: single-name unused import (flake8)
    - W291 / W293: trailing whitespace (flake8)
    - E302 / E305: missing blank lines (flake8)
    - E231: missing whitespace after ',' ';' ':' (flake8)
    - E225-E228: missing whitespace around an operator (flake8)

    Never modifies the file; returns a git-style unified diff or None.
    """
    if error_type == "NameError":
        return _generate_name_error_patch(
            file_path=file_path,
            error_type=error_type,
            message=message,
            line_number=line_number,
        )
    if error_type == "F401":
        return _generate_unused_import_patch(file_path, message, line_number)
    if error_type in {"W291", "W293"}:
        return _generate_trailing_whitespace_patch(file_path, line_number)
    if error_type in {"E302", "E305"}:
        return _generate_blank_lines_patch(file_path, message, line_number)
    if error_type == "E231":
        return _generate_space_after_patch(file_path, line_number, column)
    if error_type in _OPERATORS:
        return _generate_operator_space_patch(file_path, line_number, column, error_type)
    return None
