from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ASTLocation:
    """AST node information for a source location."""

    node_type: str
    name: str | None
    line_start: int
    line_end: int
    column_start: int
    column_end: int


@dataclass(frozen=True)
class ASTScope:
    """The logical scopes containing a source location."""

    module: str
    classes: tuple[str, ...]
    functions: tuple[str, ...]


class PythonASTAnalyzer:
    """
    Analyze Python source using the standard-library AST.

    This analyzer is read-only. It never modifies source files.
    """

    def parse_file(self, path: str | Path) -> ast.AST:
        """Parse a Python file into an AST."""

        source_path = Path(path)

        source = source_path.read_text(
            encoding="utf-8",
            errors="replace",
        )

        return ast.parse(
            source,
            filename=str(source_path),
        )

    def parse_source(self, source: str) -> ast.AST:
        """Parse Python source text into an AST."""

        return ast.parse(source)

    def locate(
        self,
        tree: ast.AST,
        line: int,
        column: int | None = None,
    ) -> ASTLocation | None:
        """
        Find the smallest AST node containing a source location.
        """

        best: ast.AST | None = None

        for node in ast.walk(tree):
            node_line = getattr(node, "lineno", None)
            node_end_line = getattr(node, "end_lineno", None)

            if node_line is None or node_end_line is None:
                continue

            if not (
                node_line <= line <= node_end_line
            ):
                continue

            if column is not None:
                start_column = getattr(
                    node,
                    "col_offset",
                    0,
                )

                end_column = getattr(
                    node,
                    "end_col_offset",
                    start_column,
                )

                if (
                    line == node_line
                    and column < start_column
                ):
                    continue

                if (
                    line == node_end_line
                    and column > end_column
                ):
                    continue

            if best is None:
                best = node
                continue

            best_size = self._node_size(best)
            current_size = self._node_size(node)

            if current_size < best_size:
                best = node

        if best is None:
            return None

        return ASTLocation(
            node_type=type(best).__name__,
            name=self._node_name(best),
            line_start=getattr(best, "lineno", 0),
            line_end=getattr(
                best,
                "end_lineno",
                getattr(best, "lineno", 0),
            ),
            column_start=getattr(best, "col_offset", 0),
            column_end=getattr(
                best,
                "end_col_offset",
                getattr(best, "col_offset", 0),
            ),
        )

    def scope_at(
        self,
        tree: ast.AST,
        line: int,
    ) -> ASTScope:
        """
        Determine the class/function scopes containing a line.
        """

        classes: list[str] = []
        functions: list[str] = []

        self._collect_scopes(
            tree,
            line,
            classes,
            functions,
        )

        return ASTScope(
            module="<module>",
            classes=tuple(classes),
            functions=tuple(functions),
        )

    def source_segment(
        self,
        source: str,
        tree: ast.AST,
        line: int,
    ) -> str | None:
        """
        Return the smallest useful AST source segment containing a line.

        This is useful for building targeted LLM context later.
        """

        candidates: list[ast.AST] = []

        for node in ast.walk(tree):
            start = getattr(node, "lineno", None)
            end = getattr(node, "end_lineno", None)

            if start is None or end is None:
                continue

            if start <= line <= end:
                candidates.append(node)

        if not candidates:
            return None

        node = min(
            candidates,
            key=self._node_size,
        )

        return ast.get_source_segment(
            source,
            node,
        )

    @staticmethod
    def _node_size(node: ast.AST) -> tuple[int, int]:
        start = getattr(node, "lineno", 0)
        end = getattr(node, "end_lineno", start)

        return (
            end - start,
            getattr(node, "col_offset", 0),
        )

    @staticmethod
    def _node_name(node: ast.AST) -> str | None:
        name = getattr(node, "name", None)

        if isinstance(name, str):
            return name

        return None

    def _collect_scopes(
        self,
        node: ast.AST,
        target_line: int,
        classes: list[str],
        functions: list[str],
    ) -> None:
        for child in ast.iter_child_nodes(node):
            start = getattr(child, "lineno", None)
            end = getattr(child, "end_lineno", None)

            if start is None or end is None:
                continue

            if not (
                start <= target_line <= end
            ):
                continue

            if isinstance(child, ast.ClassDef):
                classes.append(child.name)

                self._collect_scopes(
                    child,
                    target_line,
                    classes,
                    functions,
                )

            elif isinstance(
                child,
                (
                    ast.FunctionDef,
                    ast.AsyncFunctionDef,
                ),
            ):
                functions.append(child.name)

                self._collect_scopes(
                    child,
                    target_line,
                    classes,
                    functions,
                )

            else:
                self._collect_scopes(
                    child,
                    target_line,
                    classes,
                    functions,
                )