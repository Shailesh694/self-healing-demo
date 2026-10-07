from selfheal.gate import check_python_rewrite, check_requirements_rewrite

ORIG = "import os\n\ndef f(a,b):\n    return a+b\n"


def test_valid_small_fix_passes():
    assert check_python_rewrite("main.py", ORIG, "def f(a, b):\n    return a + b\n").ok


def test_syntax_error_rejected():
    assert not check_python_rewrite("main.py", ORIG, "def f(:\n").ok


def test_deleted_function_rejected():
    r = check_python_rewrite("main.py", ORIG, "x = 1\n")
    assert not r.ok and "removed" in r.reasons[0]


def test_sensitive_path_rejected():
    assert not check_python_rewrite(".github/x.py", ORIG, "def f(a, b):\n    return a + b\n").ok


def test_requirements_version_bump_ok():
    assert check_requirements_rewrite("flask==1.0\nrequests==2.0\n", "flask==3.1.0\nrequests==2.32.3\n").ok


def test_requirements_new_or_removed_or_url_rejected():
    o = "flask==1.0\n"
    assert not check_requirements_rewrite(o, "flask==1.0\nevilpkg==1\n").ok
    assert not check_requirements_rewrite(o, "").ok
    assert not check_requirements_rewrite(o, "flask @ https://x.io/f.whl\n").ok
    assert not check_requirements_rewrite(o, "--index-url http://evil\nflask==1.0\n").ok


def test_large_rewrite_of_big_file_rejected():
    big = "\n".join(f"x{i} = {i}" for i in range(40)) + "\n"
    new = "\n".join(f"y{i} = {i}" for i in range(40)) + "\n"
    r = check_python_rewrite("main.py", big, new)
    assert not r.ok
