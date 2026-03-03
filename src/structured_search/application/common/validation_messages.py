"""Validation message helpers shared by application services."""

from __future__ import annotations

from pydantic import ValidationError


def format_schema_validation_error(exc: ValidationError) -> str:
    """Return a compact, actionable schema-validation message.

    Includes a specific hint for the `inferences` shape expected by BaseResult.
    """
    items: list[str] = []
    for err in exc.errors(include_url=False):
        loc = err.get("loc", ())
        msg = str(err.get("msg", "Invalid value"))
        err_type = str(err.get("type", ""))

        if (
            len(loc) >= 2
            and loc[0] == "inferences"
            and isinstance(loc[1], int)
            and err_type == "model_type"
        ):
            idx = loc[1]
            items.append(
                f"inferences[{idx}] must be an object with keys: "
                "field, value, reason, confidence, evidence_ids"
            )
            continue

        path = ".".join(str(p) for p in loc)
        items.append(f"{path}: {msg}" if path else msg)

    return "; ".join(items) if items else str(exc)
