"""Export FastAPI OpenAPI contract JSON to a versioned file."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

DEFAULT_OUTPUT = "docs/openapi_v1.json"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        default=DEFAULT_OUTPUT,
        help=f"Output JSON file path (default: {DEFAULT_OUTPUT})",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    from structured_search.api.app import app

    payload = app.openapi()
    output.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"OpenAPI exported: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
