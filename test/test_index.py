from pathlib import Path

from selfheal.repository.index import RepositoryIndex


def test_index_discovers_python_files_and_symbols(
    tmp_path: Path,
) -> None:
    (tmp_path / "main.py").write_text(
        """
import os
from utils import helper


class Service:
    def run(self, value):
        return helper(value)


def calculate(a, b):
    return a + b
""".strip()
        + "\n",
        encoding="utf-8",
    )

    (tmp_path / "utils.py").write_text(
        "def helper(value):\n"
        "    return value\n",
        encoding="utf-8",
    )

    index = RepositoryIndex(tmp_path).build()

    assert set(index.files) == {
        "main.py",
        "utils.py",
    }

    assert [
        symbol.name
        for symbol in index.find_symbol("Service")
    ] == ["Service"]

    assert [
        symbol.name
        for symbol in index.find_symbol("calculate")
    ] == ["calculate"]

    imports = index.imports_for("main.py")

    assert {
        (item.module, item.name)
        for item in imports
    } == {
        ("os", None),
        ("utils", "helper"),
    }


def test_index_records_lines_and_references(
    tmp_path: Path,
) -> None:
    source = (
        "def calculate(a, b):\n"
        "    result = a + b\n"
        "    return result\n"
    )

    (tmp_path / "main.py").write_text(
        source,
        encoding="utf-8",
    )

    index = RepositoryIndex(tmp_path).build()

    symbols = index.find_symbol("calculate")

    assert len(symbols) == 1
    assert symbols[0].line == 1
    assert symbols[0].end_line == 3

    references = index.references_for("main.py")

    assert any(
        reference.name == "result"
        and reference.line == 3
        for reference in references
    )


def test_index_handles_parse_errors(
    tmp_path: Path,
) -> None:
    (tmp_path / "broken.py").write_text(
        "def broken(:\n"
        "    pass\n",
        encoding="utf-8",
    )

    index = RepositoryIndex(tmp_path).build()

    record = index.get_file("broken.py")

    assert record is not None
    assert record.parse_error is not None


def test_index_excludes_generated_directories(
    tmp_path: Path,
) -> None:
    excluded = tmp_path / ".venv"
    excluded.mkdir()

    (
        excluded / "fake.py"
    ).write_text(
        "def fake():\n"
        "    pass\n",
        encoding="utf-8",
    )

    (
        tmp_path / "real.py"
    ).write_text(
        "def real():\n"
        "    pass\n",
        encoding="utf-8",
    )

    index = RepositoryIndex(tmp_path).build()

    assert set(index.files) == {"real.py"}


def test_related_tests(
    tmp_path: Path,
) -> None:
    (
        tmp_path / "payment.py"
    ).write_text(
        "def pay():\n"
        "    pass\n",
        encoding="utf-8",
    )

    (
        tmp_path / "test_payment.py"
    ).write_text(
        "def test_pay():\n"
        "    pass\n",
        encoding="utf-8",
    )

    (
        tmp_path / "test_unrelated.py"
    ).write_text(
        "def test_other():\n"
        "    pass\n",
        encoding="utf-8",
    )

    index = RepositoryIndex(tmp_path).build()

    assert index.related_tests(
        "payment.py"
    ) == ["test_payment.py"]