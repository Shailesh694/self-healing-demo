from __future__ import annotations

import re
from pathlib import Path

from selfheal.models import Incident


class IncidentParser:
    """
    Convert raw tool output into normalized Incident objects.

    The parser currently understands common Python/CI failure formats.
    Tool-specific parsers can be extended without changing the Incident model.
    """

    _LOCATION_PATTERN = re.compile(
        r"(?P<path>[^\s:]+):(?P<line>\d+)(?::(?P<column>\d+))?"
    )

    _FLAKE8_PATTERN = re.compile(
        r"(?P<code>[A-Z]\d{3})\s+(?P<message>.+)"
    )

    _PYTEST_PATTERN = re.compile(
        r"(?P<path>[^\s:]+\.py):(?P<line>\d+)"
        r"(?:.*?)(?P<message>AssertionError.*)?"
    )

    def parse(
        self,
        output: str,
        *,
        source: str = "unknown",
        repository_root: str | Path | None = None,
    ) -> list[Incident]:
        """
        Parse raw diagnostic output into normalized incidents.
        """

        if not output.strip():
            return []

        parser = getattr(
            self,
            f"_parse_{source.lower().replace('-', '_')}",
            self._parse_generic,
        )

        return parser(
            output,
            repository_root=repository_root,
        )

    def _parse_flake8(
        self,
        output: str,
        *,
        repository_root: str | Path | None = None,
    ) -> list[Incident]:
        incidents: list[Incident] = []

        for line in output.splitlines():
            location = self._LOCATION_PATTERN.search(line)

            if not location:
                continue

            code_match = self._FLAKE8_PATTERN.search(
                line[location.end():].strip()
            )

            if not code_match:
                continue

            path = self._normalize_path(
                location.group("path"),
                repository_root,
            )

            incidents.append(
                self._build_incident(
                    path=path,
                    line=int(location.group("line")),
                    column=self._optional_int(location.group("column")),
                    code=code_match.group("code"),
                    message=code_match.group("message"),
                    source="flake8",
                )
            )

        return incidents

    def _parse_pytest(
        self,
        output: str,
        *,
        repository_root: str | Path | None = None,
    ) -> list[Incident]:
        incidents: list[Incident] = []

        for line in output.splitlines():
            location = self._LOCATION_PATTERN.search(line)

            if not location:
                continue

            path = self._normalize_path(
                location.group("path"),
                repository_root,
            )

            if not path.endswith(".py"):
                continue

            incidents.append(
                self._build_incident(
                    path=path,
                    line=int(location.group("line")),
                    column=self._optional_int(location.group("column")),
                    code="PYTEST_FAILURE",
                    message=line.strip(),
                    source="pytest",
                )
            )

        return incidents

    def _parse_generic(
        self,
        output: str,
        *,
        repository_root: str | Path | None = None,
    ) -> list[Incident]:
        incidents: list[Incident] = []

        for line in output.splitlines():
            location = self._LOCATION_PATTERN.search(line)

            if not location:
                continue

            path = self._normalize_path(
                location.group("path"),
                repository_root,
            )

            message = line[location.end():].strip(" :-")

            if not message:
                message = line.strip()

            incidents.append(
                self._build_incident(
                    path=path,
                    line=int(location.group("line")),
                    column=self._optional_int(location.group("column")),
                    code="UNKNOWN",
                    message=message,
                    source="unknown",
                )
            )

        return incidents

    def _build_incident(
        self,
        *,
        path: str,
        line: int,
        column: int | None,
        code: str,
        message: str,
        source: str,
    ) -> Incident:
        """
        Construct the common Incident model.

        All external tools are converted into this single representation.
        """

        return Incident(
            source=source,
            code=code,
            message=message,
            file_path=path,
            line=line,
            column=column,
        )

    @staticmethod
    def _optional_int(value: str | None) -> int | None:
        if value is None:
            return None

        return int(value)

    @staticmethod
    def _normalize_path(
        path: str,
        repository_root: str | Path | None,
    ) -> str:
        """
        Convert an absolute path into a repository-relative path when possible.
        """

        normalized = path.replace("\\", "/")

        if repository_root is None:
            return normalized

        try:
            root = Path(repository_root).resolve()
            candidate = Path(path).resolve()
            return candidate.relative_to(root).as_posix()
        except (ValueError, OSError):
            return normalized