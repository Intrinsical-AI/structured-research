"""Export TypeScript API types for the UI from an OpenAPI JSON document."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

DEFAULT_OPENAPI = "docs/openapi_v1.json"
DEFAULT_OUTPUT = "ui/lib/generated/api-types.ts"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--openapi",
        default=DEFAULT_OPENAPI,
        help=f"OpenAPI JSON input path (default: {DEFAULT_OPENAPI})",
    )
    parser.add_argument(
        "--output",
        default=DEFAULT_OUTPUT,
        help=f"TypeScript output path (default: {DEFAULT_OUTPUT})",
    )
    return parser.parse_args(argv)


def _ref_name(ref: str) -> str:
    return ref.rsplit("/", maxsplit=1)[-1]


def _parenthesize_if_needed(ts_type: str) -> str:
    if "|" in ts_type or "&" in ts_type:
        return f"({ts_type})"
    return ts_type


def _literal(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _schema_to_ts(schema: dict[str, Any]) -> str:
    if "$ref" in schema:
        return _ref_name(str(schema["$ref"]))

    if "anyOf" in schema:
        variants = [_schema_to_ts(item) for item in schema.get("anyOf", [])]
        variants = [item for item in variants if item]
        return " | ".join(dict.fromkeys(variants)) or "unknown"

    if "allOf" in schema:
        variants = [_schema_to_ts(item) for item in schema.get("allOf", [])]
        variants = [item for item in variants if item]
        return " & ".join(dict.fromkeys(variants)) or "unknown"

    if "oneOf" in schema:
        variants = [_schema_to_ts(item) for item in schema.get("oneOf", [])]
        variants = [item for item in variants if item]
        return " | ".join(dict.fromkeys(variants)) or "unknown"

    if "enum" in schema:
        values = schema.get("enum", [])
        if not isinstance(values, list) or not values:
            return "unknown"
        return " | ".join(_literal(value) for value in values)

    schema_type = schema.get("type")
    if isinstance(schema_type, list):
        variants = []
        for type_item in schema_type:
            variants.append(_schema_to_ts({**schema, "type": type_item}))
        return " | ".join(dict.fromkeys(variants)) or "unknown"

    if schema_type == "string":
        return "string"
    if schema_type in {"integer", "number"}:
        return "number"
    if schema_type == "boolean":
        return "boolean"
    if schema_type == "null":
        return "null"
    if schema_type == "array":
        item_type = _schema_to_ts(schema.get("items", {}))
        return f"{_parenthesize_if_needed(item_type)}[]"

    properties = schema.get("properties")
    additional = schema.get("additionalProperties")

    if schema_type == "object" or properties is not None or additional is not None:
        if isinstance(properties, dict) and properties:
            required = set(schema.get("required", []))
            lines: list[str] = ["{"]
            for key, value in properties.items():
                optional = "" if key in required else "?"
                prop_type = _schema_to_ts(value if isinstance(value, dict) else {})
                lines.append(f"  {json.dumps(key)}{optional}: {prop_type};")
            if additional is True:
                lines.append("  [key: string]: unknown;")
            elif isinstance(additional, dict):
                lines.append(f"  [key: string]: {_schema_to_ts(additional)};")
            lines.append("}")
            return "\n".join(lines)

        if additional is True:
            return "Record<string, unknown>"
        if isinstance(additional, dict):
            return f"Record<string, {_schema_to_ts(additional)}>"
        return "Record<string, unknown>"

    return "unknown"


def _render_types(openapi: dict[str, Any]) -> str:
    schemas = openapi.get("components", {}).get("schemas", {})
    if not isinstance(schemas, dict):
        raise RuntimeError("OpenAPI document has no components.schemas object")

    lines: list[str] = [
        "// AUTO-GENERATED FILE. DO NOT EDIT.",
        "// Source: docs/openapi_v1.json",
        "",
    ]

    for name in sorted(schemas):
        schema = schemas[name]
        if not isinstance(schema, dict):
            continue
        ts_type = _schema_to_ts(schema)
        lines.append(f"export type {name} = {ts_type}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    openapi_path = Path(args.openapi)
    output_path = Path(args.output)

    if not openapi_path.is_file():
        raise FileNotFoundError(f"OpenAPI input not found: {openapi_path}")

    openapi = json.loads(openapi_path.read_text(encoding="utf-8"))
    rendered = _render_types(openapi)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(rendered, encoding="utf-8")
    print(f"UI API types exported: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
