from pathlib import Path

import pytest

from selfheal.mcp.server import mcp_server
from selfheal.mcp.tools import analyze_scope


def create_repository(
    root: Path,
) -> Path:
    root.mkdir()

    package = root / "app"
    package.mkdir()

    (package / "__init__.py").write_text(
        "",
        encoding="utf-8",
    )

    (package / "utils.py").write_text(
        "def helper():\n"
        "    return 42\n",
        encoding="utf-8",
    )

    (package / "service.py").write_text(
        "from app.utils import helper\n"
        "\n"
        "class Service:\n"
        "    def run(self):\n"
        "        value = helper()\n"
        "        return value\n",
        encoding="utf-8",
    )

    tests = root / "test"
    tests.mkdir()

    (tests / "test_service.py").write_text(
        "from app.service import Service\n"
        "\n"
        "def test_service():\n"
        "    assert Service().run() == 42\n",
        encoding="utf-8",
    )

    return root


def test_analyze_scope_returns_file_metadata(
    tmp_path: Path,
):
    repository = create_repository(
        tmp_path / "repo"
    )

    result = analyze_scope(
        str(repository),
        "app/service.py",
    )

    assert result["file_path"] == "app/service.py"
    assert result["language"] == "python"
    assert result["module"] == "app.service"
    assert result["lines"] == 6
    assert result["parse_error"] is None


def test_analyze_scope_returns_symbols(
    tmp_path: Path,
):
    repository = create_repository(
        tmp_path / "repo"
    )

    result = analyze_scope(
        str(repository),
        "app/service.py",
    )

    names = {
        symbol["name"]
        for symbol in result["symbols"]
    }

    assert "Service" in names
    assert "run" in names


def test_analyze_scope_returns_imports(
    tmp_path: Path,
):
    repository = create_repository(
        tmp_path / "repo"
    )

    result = analyze_scope(
        str(repository),
        "app/service.py",
    )

    assert result["imports"] == [
        {
            "module": "app.utils",
            "name": "helper",
            "alias": None,
            "line": 1,
        }
    ]


def test_analyze_scope_resolves_local_dependency(
    tmp_path: Path,
):
    repository = create_repository(
        tmp_path / "repo"
    )

    result = analyze_scope(
        str(repository),
        "app/service.py",
    )

    assert result["dependencies"] == [
        {
            "module": "app.utils",
            "file_path": "app/utils.py",
        }
    ]


def test_analyze_scope_returns_related_tests(
    tmp_path: Path,
):
    repository = create_repository(
        tmp_path / "repo"
    )

    result = analyze_scope(
        str(repository),
        "app/service.py",
    )

    assert "test/test_service.py" in (
        result["related_tests"]
    )


def test_analyze_scope_returns_ast_scope(
    tmp_path: Path,
):
    repository = create_repository(
        tmp_path / "repo"
    )

    result = analyze_scope(
        str(repository),
        "app/service.py",
        line=5,
    )

    assert result["ast"]["available"] is True

    assert result["ast"]["location"] is not None

    assert "Service" in (
        result["ast"]["scope"]["classes"]
    )

    assert "run" in (
        result["ast"]["scope"]["functions"]
    )


def test_analyze_scope_rejects_empty_repository(
):
    with pytest.raises(ValueError):
        analyze_scope(
            "",
            "app.py",
        )


def test_analyze_scope_rejects_empty_file(
    tmp_path: Path,
):
    repository = create_repository(
        tmp_path / "repo"
    )

    with pytest.raises(ValueError):
        analyze_scope(
            str(repository),
            "",
        )


def test_analyze_scope_rejects_missing_file(
    tmp_path: Path,
):
    repository = create_repository(
        tmp_path / "repo"
    )

    with pytest.raises(FileNotFoundError):
        analyze_scope(
            str(repository),
            "missing.py",
        )


def test_analyze_scope_rejects_invalid_line(
    tmp_path: Path,
):
    repository = create_repository(
        tmp_path / "repo"
    )

    with pytest.raises(ValueError):
        analyze_scope(
            str(repository),
            "app/service.py",
            line=0,
        )


def test_analyze_scope_rejects_line_outside_file(
    tmp_path: Path,
):
    repository = create_repository(
        tmp_path / "repo"
    )

    with pytest.raises(ValueError):
        analyze_scope(
            str(repository),
            "app/service.py",
            line=100,
        )


def test_mcp_server_registers_analyze_scope():
    tools = mcp_server._tool_manager.list_tools()

    names = {
        tool.name
        for tool in tools
    }

    assert "analyze_scope" in names