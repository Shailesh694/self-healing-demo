import pytest

from selfheal.repository.language import Language, SupportLevel
from selfheal.repository.scanner import scan_repository, summarize_by_language


@pytest.fixture
def sample_repo(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("print('hi')\n")
    (tmp_path / "README.md").write_text("# hello\n")
    (tmp_path / "app.js").write_text("console.log('hi');\n")

    ignored = tmp_path / "__pycache__"
    ignored.mkdir()
    (ignored / "main.cpython-312.pyc").write_bytes(b"\x00\x01\x02")

    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    (git_dir / "HEAD").write_text("ref: refs/heads/main\n")

    return tmp_path


def test_scan_finds_real_files(sample_repo):
    files = scan_repository(sample_repo)
    paths = {f.path for f in files}
    assert "src/main.py" in paths
    assert "README.md" in paths
    assert "app.js" in paths


def test_scan_ignores_pycache_and_git(sample_repo):
    files = scan_repository(sample_repo)
    paths = {f.path for f in files}
    assert not any(".git" in p for p in paths)
    assert not any("__pycache__" in p for p in paths)


def test_scan_tags_language_and_support_level(sample_repo):
    files = {f.path: f for f in scan_repository(sample_repo)}
    assert files["src/main.py"].language == Language.PYTHON
    assert files["src/main.py"].support_level == SupportLevel.FULL
    assert files["app.js"].language == Language.JAVASCRIPT
    assert files["app.js"].support_level == SupportLevel.UNSUPPORTED


def test_scan_records_line_count_for_small_text_files(sample_repo):
    files = {f.path: f for f in scan_repository(sample_repo)}
    assert files["src/main.py"].line_count == 1


def test_scan_missing_root_raises():
    with pytest.raises(FileNotFoundError):
        scan_repository("/definitely/does/not/exist/xyz")


def test_summarize_by_language(sample_repo):
    files = scan_repository(sample_repo)
    counts = summarize_by_language(files)
    assert counts[Language.PYTHON] >= 1
    assert counts[Language.JAVASCRIPT] >= 1