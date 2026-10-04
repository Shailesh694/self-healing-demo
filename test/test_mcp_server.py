from pathlib import Path

from selfheal.mcp.server import (
    mcp_server,
)
from selfheal.mcp.tools import (
    scan_repository,
)


def create_repository(
    root: Path,
) -> Path:
    root.mkdir()

    (root / "app.py").write_text(
        "print('hello')\n",
        encoding="utf-8",
    )

    (root / "README.md").write_text(
        "# Test Repository\n",
        encoding="utf-8",
    )

    ignored = root / ".git"
    ignored.mkdir()

    (ignored / "config").write_text(
        "ignored\n",
        encoding="utf-8",
    )

    return root


def test_scan_repository_returns_metadata(
    tmp_path: Path,
):
    repository = create_repository(
        tmp_path / "repo"
    )

    result = scan_repository(
        str(repository)
    )

    assert result["file_count"] == 2

    paths = {
        file["path"]
        for file in result["files"]
    }

    assert paths == {
        "app.py",
        "README.md",
    }


def test_scan_repository_returns_languages(
    tmp_path: Path,
):
    repository = create_repository(
        tmp_path / "repo"
    )

    result = scan_repository(
        str(repository)
    )

    assert "python" in result["languages"]
    assert result["languages"]["python"] == 1
    assert result["languages"]["unknown"] == 1


def test_scan_repository_rejects_empty_path():
    try:
        scan_repository("")
        assert False, "Expected ValueError"
    except ValueError as exc:
        assert "repository_path" in str(exc)


def test_scan_repository_rejects_missing_path(
    tmp_path: Path,
):
    missing = (
        tmp_path
        / "does-not-exist"
    )

    try:
        scan_repository(
            str(missing)
        )
        assert False, (
            "Expected FileNotFoundError"
        )
    except FileNotFoundError:
        pass


def test_scan_repository_rejects_file_path(
    tmp_path: Path,
):
    file_path = tmp_path / "app.py"

    file_path.write_text(
        "print('hello')\n",
        encoding="utf-8",
    )

    try:
        scan_repository(
            str(file_path)
        )
        assert False, "Expected ValueError"
    except ValueError as exc:
        assert "not a directory" in str(exc)


def test_mcp_server_registers_scan_tool():
    tools = mcp_server._tool_manager.list_tools()

    names = {
        tool.name
        for tool in tools
    }

    assert "scan_repository" in names