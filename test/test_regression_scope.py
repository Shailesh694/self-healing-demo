from selfheal.regression_scope import (
    FileSnapshot,
    compare_file_scope,
)


def test_approved_file_change_passes():
    baseline = [
        FileSnapshot(
            path="app.py",
            content="print('old')",
        ),
        FileSnapshot(
            path="test_app.py",
            content="def test_ok(): pass",
        ),
    ]

    candidate = [
        FileSnapshot(
            path="app.py",
            content="print('new')",
        ),
        FileSnapshot(
            path="test_app.py",
            content="def test_ok(): pass",
        ),
    ]

    result = compare_file_scope(
        baseline,
        candidate,
        approved_files={"app.py"},
    )

    assert result.passed is True
    assert result.changed_files == ("app.py",)
    assert result.unexpected_files == ()


def test_unapproved_file_change_is_rejected():
    baseline = [
        FileSnapshot(
            path="app.py",
            content="print('old')",
        ),
        FileSnapshot(
            path="config.py",
            content="DEBUG = False",
        ),
    ]

    candidate = [
        FileSnapshot(
            path="app.py",
            content="print('new')",
        ),
        FileSnapshot(
            path="config.py",
            content="DEBUG = True",
        ),
    ]

    result = compare_file_scope(
        baseline,
        candidate,
        approved_files={"app.py"},
    )

    assert result.passed is False
    assert result.changed_files == (
        "app.py",
        "config.py",
    )
    assert result.unexpected_files == (
        "config.py",
    )


def test_new_unapproved_file_is_rejected():
    baseline = [
        FileSnapshot(
            path="app.py",
            content="print('old')",
        ),
    ]

    candidate = [
        FileSnapshot(
            path="app.py",
            content="print('new')",
        ),
        FileSnapshot(
            path="malicious.py",
            content="print('unexpected')",
        ),
    ]

    result = compare_file_scope(
        baseline,
        candidate,
        approved_files={"app.py"},
    )

    assert result.passed is False
    assert result.unexpected_files == (
        "malicious.py",
    )


def test_deleted_unapproved_file_is_rejected():
    baseline = [
        FileSnapshot(
            path="app.py",
            content="print('old')",
        ),
        FileSnapshot(
            path="config.py",
            content="DEBUG = False",
        ),
    ]

    candidate = [
        FileSnapshot(
            path="app.py",
            content="print('new')",
        ),
    ]

    result = compare_file_scope(
        baseline,
        candidate,
        approved_files={"app.py"},
    )

    assert result.passed is False
    assert result.unexpected_files == (
        "config.py",
    )


def test_no_changes_pass():
    baseline = [
        FileSnapshot(
            path="app.py",
            content="print('same')",
        ),
    ]

    candidate = [
        FileSnapshot(
            path="app.py",
            content="print('same')",
        ),
    ]

    result = compare_file_scope(
        baseline,
        candidate,
        approved_files={"app.py"},
    )

    assert result.passed is True
    assert result.changed_files == ()
    assert result.unexpected_files == ()