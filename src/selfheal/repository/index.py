"""
Deterministic repository structural index.

Phase 4:
- Index Python files discovered by the repository scanner.
- Record classes and functions.
- Record imports.
- Record name references.
- Record source line ranges.
- Identify likely related test files.

This module does NOT:
- call Gemini
- modify repository files
- generate patches
- perform remediation

Those responsibilities belong to later phases.
"""

from __future__ import annotations

import ast
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class SymbolRecord:
    """A class or function discovered in a Python file."""

    name: str
    qualified_name: str
    kind: str
    file: str
    line: int
    end_line: int | None
    parent: str | None = None


@dataclass(frozen=True)
class ImportRecord:
    """An import statement discovered in a Python file."""

    module: str
    name: str | None
    alias: str | None
    file: str
    line: int


@dataclass(frozen=True)
class ReferenceRecord:
    """A name reference discovered inside a Python file."""

    name: str
    file: str
    line: int
    context: str | None = None


@dataclass
class FileRecord:
    """Structural information about one indexed repository file."""

    path: str
    language: str
    module: str | None = None
    lines: int = 0
    symbols: list[SymbolRecord] = field(default_factory=list)
    imports: list[ImportRecord] = field(default_factory=list)
    references: list[ReferenceRecord] = field(default_factory=list)
    parse_error: str | None = None


class RepositoryIndex:
    """
    Deterministic, Python-first structural repository index.

    This phase uses Python's standard-library AST parser.

    It does not modify the repository.
    It does not call an LLM.
    """

    def __init__(
        self,
        root: str | Path,
        *,
        excluded_dirs: Iterable[str] | None = None,
        max_files: int = 20_000,
        max_file_bytes: int = 1_000_000,
    ) -> None:
        self.max_files = max_files
        self.max_file_bytes = max_file_bytes
        self.truncated = False
        self.skipped_large: list[str] = []
        self.skipped_unparsable: list[str] = []
        self.root = Path(root).resolve()

        self.excluded_dirs = set(
            excluded_dirs
            or {
                ".git",
                ".hg",
                ".svn",
                ".venv",
                "venv",
                "env",
                "node_modules",
                "__pycache__",
                ".mypy_cache",
                ".pytest_cache",
                ".tox",
                "dist",
                "build",
            }
        )

        self.files: dict[str, FileRecord] = {}

    def build(self) -> "RepositoryIndex":
        """Build or rebuild the repository index."""

        self.files.clear()
        self.truncated = False
        self.skipped_large = []
        self.skipped_unparsable = []

        for path in self._iter_python_files():
            if len(self.files) >= self.max_files:
                self.truncated = True
                break

            try:
                if path.stat().st_size > self.max_file_bytes:
                    self.skipped_large.append(self._relative(path))
                    continue
                self._index_python_file(path)
            except (SyntaxError, ValueError, OSError):
                self.files.pop(self._relative(path), None)
                self.skipped_unparsable.append(self._relative(path))

        return self

    def _iter_python_files(self):
        """Deterministic walk that prunes excluded directories early."""
        for dirpath, dirnames, filenames in os.walk(self.root):
            dirnames[:] = sorted(
                d for d in dirnames if d not in self.excluded_dirs
            )
            for name in sorted(filenames):
                if name.endswith(".py"):
                    yield Path(dirpath) / name

    def get_file(self, path: str | Path) -> FileRecord | None:
        """Return structural information for a specific file."""

        key = self._relative(path)
        return self.files.get(key)

    def find_symbol(self, name: str) -> list[SymbolRecord]:
        """Find all classes/functions having the given short name."""

        return [
            symbol
            for record in self.files.values()
            for symbol in record.symbols
            if symbol.name == name
        ]

    def find_symbol_in_file(
        self,
        path: str | Path,
        name: str,
    ) -> list[SymbolRecord]:
        """Find a named symbol inside one specific file."""

        record = self.get_file(path)

        if record is None:
            return []

        return [
            symbol
            for symbol in record.symbols
            if symbol.name == name
        ]

    def imports_for(
        self,
        path: str | Path,
    ) -> list[ImportRecord]:
        """Return imports recorded for a file."""

        record = self.get_file(path)

        if record is None:
            return []

        return list(record.imports)

    def references_for(
        self,
        path: str | Path,
    ) -> list[ReferenceRecord]:
        """Return references recorded for a file."""

        record = self.get_file(path)

        if record is None:
            return []

        return list(record.references)

    def related_tests(
        self,
        path: str | Path,
    ) -> list[str]:
        """
        Return likely test files for a module.

        This is intentionally conservative.

        A more sophisticated dependency/test graph will be added
        in later analysis phases.
        """

        record = self.get_file(path)

        if record is None:
            return []

        stem = Path(record.path).stem
        candidates: list[str] = []

        for other in self.files.values():
            other_path = Path(other.path)

            is_test = (
                other_path.name.startswith("test_")
                or other_path.name.endswith("_test.py")
            )

            if not is_test:
                continue

            if stem in other_path.stem:
                candidates.append(other.path)

        return sorted(candidates)

    def summary(self) -> dict[str, int]:
        """Return basic index statistics."""

        return {
            "python_files": len(self.files),
            "symbols": sum(
                len(record.symbols)
                for record in self.files.values()
            ),
            "imports": sum(
                len(record.imports)
                for record in self.files.values()
            ),
            "references": sum(
                len(record.references)
                for record in self.files.values()
            ),
            "parse_errors": sum(
                1
                for record in self.files.values()
                if record.parse_error is not None
            ),
        }

    def _index_python_file(self, path: Path) -> None:
        relative = self._relative(path)

        source = path.read_text(
            encoding="utf-8",
            errors="replace",
        )

        record = FileRecord(
            path=relative,
            language="python",
            module=self._module_name(path),
            lines=len(source.splitlines()),
        )

        self.files[relative] = record

        try:
            tree = ast.parse(
                source,
                filename=str(path),
            )

        except SyntaxError as exc:
            record.parse_error = (
                f"{exc.msg} (line {exc.lineno})"
            )
            return

        visitor = _PythonVisitor(relative)

        visitor.visit(tree)

        record.symbols.extend(visitor.symbols)
        record.imports.extend(visitor.imports)
        record.references.extend(visitor.references)

    def _module_name(self, path: Path) -> str:
        relative = path.relative_to(self.root).with_suffix("")

        parts = list(relative.parts)

        if parts and parts[-1] == "__init__":
            parts.pop()

        return ".".join(parts)

    def _relative(self, path: str | Path) -> str:
        candidate = Path(path)

        if not candidate.is_absolute():
            candidate = self.root / candidate

        return candidate.resolve().relative_to(
            self.root
        ).as_posix()

    def _excluded(self, path: Path) -> bool:
        try:
            relative = path.relative_to(self.root)

        except ValueError:
            return True

        return any(
            part in self.excluded_dirs
            for part in relative.parts
        )


class _PythonVisitor(ast.NodeVisitor):
    """
    Walk a Python AST and extract structural information.
    """

    def __init__(self, file: str) -> None:
        self.file = file

        self.symbols: list[SymbolRecord] = []
        self.imports: list[ImportRecord] = []
        self.references: list[ReferenceRecord] = []

        self._scope: list[str] = []

    def visit_FunctionDef(
        self,
        node: ast.FunctionDef,
    ) -> None:
        self._visit_function(
            node,
            "function",
        )

    def visit_AsyncFunctionDef(
        self,
        node: ast.AsyncFunctionDef,
    ) -> None:
        self._visit_function(
            node,
            "async_function",
        )

    def _visit_function(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        kind: str,
    ) -> None:
        qualified = ".".join(
            self._scope + [node.name]
        )

        self.symbols.append(
            SymbolRecord(
                name=node.name,
                qualified_name=qualified,
                kind=kind,
                file=self.file,
                line=node.lineno,
                end_line=getattr(
                    node,
                    "end_lineno",
                    None,
                ),
                parent=(
                    self._scope[-1]
                    if self._scope
                    else None
                ),
            )
        )

        self._scope.append(node.name)

        self.generic_visit(node)

        self._scope.pop()

    def visit_ClassDef(
        self,
        node: ast.ClassDef,
    ) -> None:
        qualified = ".".join(
            self._scope + [node.name]
        )

        self.symbols.append(
            SymbolRecord(
                name=node.name,
                qualified_name=qualified,
                kind="class",
                file=self.file,
                line=node.lineno,
                end_line=getattr(
                    node,
                    "end_lineno",
                    None,
                ),
                parent=(
                    self._scope[-1]
                    if self._scope
                    else None
                ),
            )
        )

        self._scope.append(node.name)

        self.generic_visit(node)

        self._scope.pop()

    def visit_Import(
        self,
        node: ast.Import,
    ) -> None:
        for alias in node.names:
            self.imports.append(
                ImportRecord(
                    module=alias.name,
                    name=None,
                    alias=alias.asname,
                    file=self.file,
                    line=node.lineno,
                )
            )

        self.generic_visit(node)

    def visit_ImportFrom(
        self,
        node: ast.ImportFrom,
    ) -> None:
        module = (
            "." * node.level
            + (node.module or "")
        )

        for alias in node.names:
            self.imports.append(
                ImportRecord(
                    module=module,
                    name=alias.name,
                    alias=alias.asname,
                    file=self.file,
                    line=node.lineno,
                )
            )

        self.generic_visit(node)

    def visit_Name(
        self,
        node: ast.Name,
    ) -> None:
        self.references.append(
            ReferenceRecord(
                name=node.id,
                file=self.file,
                line=node.lineno,
                context=(
                    self._scope[-1]
                    if self._scope
                    else None
                ),
            )
        )

        self.generic_visit(node)