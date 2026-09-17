from selfheal.incidents.fingerprint import IncidentFingerprinter
from selfheal.incidents.parser import IncidentParser


def test_parse_flake8_output():
    parser = IncidentParser()

    output = (
        "main.py:4:5: F401 'os' imported but unused\n"
        "main.py:5:1: E302 expected 2 blank lines, found 1\n"
    )

    incidents = parser.parse(output, source="flake8")

    assert len(incidents) == 2

    assert incidents[0].source == "flake8"
    assert incidents[0].code == "F401"
    assert incidents[0].file_path == "main.py"
    assert incidents[0].line == 4
    assert incidents[0].column == 5

    assert incidents[1].code == "E302"
    assert incidents[1].line == 5


def test_parse_empty_output():
    parser = IncidentParser()

    incidents = parser.parse("", source="flake8")

    assert incidents == []


def test_parse_unknown_source():
    parser = IncidentParser()

    output = "src/service.py:42: unexpected failure"

    incidents = parser.parse(output, source="unknown")

    assert len(incidents) == 1
    assert incidents[0].file_path == "src/service.py"
    assert incidents[0].line == 42


def test_fingerprint_is_deterministic():
    parser = IncidentParser()
    fingerprinter = IncidentFingerprinter()

    output = "main.py:4:5: F401 'os' imported but unused"

    incident = parser.parse(
        output,
        source="flake8",
    )[0]

    first = fingerprinter.fingerprint(incident)
    second = fingerprinter.fingerprint(incident)

    assert first == second
    assert len(first) == 16


def test_same_incident_has_same_fingerprint():
    parser = IncidentParser()
    fingerprinter = IncidentFingerprinter()

    output1 = "main.py:4:5: F401 'os' imported but unused"
    output2 = "main.py:4:5: F401 'os' imported but unused"

    incident1 = parser.parse(output1, source="flake8")[0]
    incident2 = parser.parse(output2, source="flake8")[0]

    assert fingerprinter.fingerprint(incident1) == (
        fingerprinter.fingerprint(incident2)
    )


def test_fingerprint_changes_for_different_incidents():
    parser = IncidentParser()
    fingerprinter = IncidentFingerprinter()

    incident1 = parser.parse(
        "main.py:4:5: F401 'os' imported but unused",
        source="flake8",
    )[0]

    incident2 = parser.parse(
        "main.py:5:1: E302 expected 2 blank lines, found 1",
        source="flake8",
    )[0]

    assert fingerprinter.fingerprint(incident1) != (
        fingerprinter.fingerprint(incident2)
    )


def test_path_normalization():
    parser = IncidentParser()

    output = r"src\service.py:10:2: E999 invalid syntax"

    incidents = parser.parse(
        output,
        source="flake8",
    )

    assert len(incidents) == 1
    assert incidents[0].file_path == "src/service.py"