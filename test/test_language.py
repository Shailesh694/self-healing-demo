from pathlib import Path

from selfheal.repository.language import (
    Language,
    SupportLevel,
    detect_language,
    support_level,
)


def test_detects_python():
    assert detect_language(Path("main.py")) == Language.PYTHON


def test_detects_typescript():
    assert detect_language(Path("app.tsx")) == Language.TYPESCRIPT


def test_unknown_extension():
    assert detect_language(Path("README.md")) == Language.UNKNOWN


def test_python_is_fully_supported():
    assert support_level(Language.PYTHON) == SupportLevel.FULL


def test_non_python_languages_are_explicitly_unsupported():
    """Spec rule #14: never claim support for a language that isn't implemented."""
    for lang in [
        Language.JAVASCRIPT,
        Language.TYPESCRIPT,
        Language.GO,
        Language.RUST,
        Language.JAVA,
        Language.CPP,
        Language.C,
    ]:
        assert support_level(lang) == SupportLevel.UNSUPPORTED