"""Unit tests for TolerantJSONLParser edge cases.

loading.py is intentionally NOT modified by these tests.
If a test reveals a bug, the fix goes in a separate commit with coverage.
"""

from __future__ import annotations

import textwrap

import pytest

from structured_search.infra.loading import TolerantJSONLParser


@pytest.fixture
def parser() -> TolerantJSONLParser:
    return TolerantJSONLParser()


# ---------------------------------------------------------------------------
# Case 1: valid JSONL, one object per line (baseline)
# ---------------------------------------------------------------------------


def test_valid_jsonl_line_by_line(parser: TolerantJSONLParser):
    text = textwrap.dedent("""\
        {"id": "1", "value": "a"}
        {"id": "2", "value": "b"}
        {"id": "3", "value": "c"}
    """)
    valid, errors = parser.parse(text)
    assert errors == []
    assert len(valid) == 3
    assert valid[0]["id"] == "1"
    assert valid[2]["id"] == "3"


# ---------------------------------------------------------------------------
# Case 2: well-formed multiline object
# ---------------------------------------------------------------------------


def test_multiline_well_formed_object(parser: TolerantJSONLParser):
    text = textwrap.dedent("""\
        {"id": "multi",
         "nested": {"a": 1},
         "value": "ok"}
    """)
    valid, errors = parser.parse(text)
    assert errors == []
    assert len(valid) == 1
    assert valid[0]["id"] == "multi"
    assert valid[0]["nested"] == {"a": 1}


# ---------------------------------------------------------------------------
# Case 3: truncated object → error accumulated, no crash
# ---------------------------------------------------------------------------


def test_truncated_object_yields_error_not_crash(parser: TolerantJSONLParser):
    text = textwrap.dedent("""\
        {"id": "broken", "value":
    """)
    valid, errors = parser.parse(text)
    assert valid == []
    assert len(errors) == 1
    assert errors[0].kind == "json_parse"
    assert errors[0].line_no == 1


# ---------------------------------------------------------------------------
# Case 4: mix — valid + malformed + valid → 2 valid, 1 error
# ---------------------------------------------------------------------------


def test_mix_valid_malformed_valid(parser: TolerantJSONLParser):
    text = textwrap.dedent("""\
        {"id": "first"}
        {bad json here}
        {"id": "third"}
    """)
    valid, errors = parser.parse(text)
    assert len(valid) == 2
    assert len(errors) == 1
    assert valid[0]["id"] == "first"
    assert valid[1]["id"] == "third"
    assert errors[0].kind == "json_parse"


# ---------------------------------------------------------------------------
# Case 5: deeply nested braces closing on a later line
# ---------------------------------------------------------------------------


def test_deeply_nested_braces_multiline(parser: TolerantJSONLParser):
    text = textwrap.dedent("""\
        {"id": "deep",
         "level1": {
           "level2": {
             "level3": "value"
           }
         }}
    """)
    valid, errors = parser.parse(text)
    assert errors == []
    assert len(valid) == 1
    assert valid[0]["level1"]["level2"]["level3"] == "value"


# ---------------------------------------------------------------------------
# Case 6: non-object JSON value → not_object error
# ---------------------------------------------------------------------------


def test_non_object_json_yields_not_object_error(parser: TolerantJSONLParser):
    valid, errors = parser.parse("[1, 2, 3]\n")
    assert valid == []
    assert len(errors) == 1
    assert errors[0].kind == "not_object"
    assert errors[0].line_no == 1
