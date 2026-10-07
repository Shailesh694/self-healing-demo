from __future__ import annotations

from dataclasses import dataclass

from .diff import parse_patch


@dataclass
class ValidationResult:
    valid: bool
    errors: list[str]


def validate_candidate(
    *,
    file_path: str,
    confidence: float,
    patch: str | None,
) -> ValidationResult:
    errors: list[str] = []

    if not file_path:
        errors.append("Missing target file path")

    if not 0.0 <= confidence <= 1.0:
        errors.append("Confidence must be between 0.0 and 1.0")

    if patch is None:
        errors.append("No patch was provided")
    elif not patch.strip():
        errors.append("Patch cannot be empty")
    else:
        try:
            patch_files = parse_patch(patch)
        except ValueError as exc:
            errors.append(str(exc))
        else:
            if len(patch_files) != 1:
                errors.append(
                    "Patch must modify exactly one file"
                )
            else:
                target = patch_files[0].new_path
                normalized_file = file_path.replace(
                    "\\",
                    "/",
                )

                if target not in {
                    normalized_file,
                    normalized_file.rsplit("/", 1)[-1],
                }:
                    errors.append(
                        "Patch target does not match "
                        "the candidate file path"
                    )

    return ValidationResult(
        valid=not errors,
        errors=errors,
    )