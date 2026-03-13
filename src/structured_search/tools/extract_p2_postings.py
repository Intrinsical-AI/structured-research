"""Extract clean JobDescription JSON files from the malformed profile_example result.jsonl.

The raw JSONL has two structural issues produced by the LLM:
  1. Evidence sub-objects (e2, e3 …) emitted as separate lines instead of being
     embedded in the parent posting's evidence[] array.
  2. apply_url and location values contain Markdown link syntax
     "[https://url](url-encoded-rest)" — the real URL is the bracketed text.

This script:
  - Reads result.jsonl, keeps only posting-level objects
     (distinguishing them from evidence objects by id pattern and field presence)
  - Strips the leading "[" from URL fields to recover the real URL
  - Reconstructs clean location from geo.city / geo.country
  - Overrides seniority "mid" → "junior" for postings with trainee/prácticas signals
     (these were mis-mapped before Fix 1 corrected SeniorityInfo.level)
  - Writes one JobDescription-compatible JSON per posting to --output-dir
    (default: results/job_search/profile_example/postings/)

Usage:
  uv run structured-search tools extract-p2-postings
  uv run structured-search tools extract-p2-postings --input results/job_search/profile_example/result.jsonl
"""

import argparse
import json
import logging
import re
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

_EVIDENCE_ID_RE = re.compile(r"^e\d+$")
_TRAINEE_SIGNALS = {"prácticas", "trainee", "becario", "becaria", "intern", "beca"}


def is_posting(obj: dict) -> bool:
    """True if obj is a job posting, not a spilled evidence sub-object."""
    oid = str(obj.get("id", ""))
    if _EVIDENCE_ID_RE.match(oid):
        return False
    return "company" in obj and "title" in obj


def clean_url(value: str | None) -> str | None:
    """Strip leading '[' inserted by Markdown link syntax.

    The LLM emitted apply_url as '[https://url](url-encoded-rest)'.
    After JSON parsing the string value starts with '['.
    """
    if not value or not isinstance(value, str):
        return value
    text = value.strip()
    markdown_link = re.match(r"^\[(https?://[^\]]+)\]\(.*\)$", text)
    if markdown_link:
        return markdown_link.group(1)
    return text.lstrip("[")


def clean_location(obj: dict) -> str | None:
    """Reconstruct location from geo sub-object (clean) rather than the corrupted
    location string field."""
    geo = obj.get("geo") or {}
    parts = [geo.get("city"), geo.get("country")]
    joined = ", ".join(p for p in parts if p)
    return joined or None


def fix_seniority(obj: dict) -> str:
    """Return 'junior' when the posting has trainee/prácticas process signals.

    Before Fix 1 (SeniorityInfo.level missing 'junior'), the LLM was forced to
    report these as 'mid'. We correct that here.
    """
    process = obj.get("process") or []
    level = (obj.get("seniority") or {}).get("level", "mid")
    if level == "mid":
        process_lower = {str(p).lower() for p in process}
        title_lower = str(obj.get("title", "")).lower()
        notes_lower = str(obj.get("notes", "")).lower()
        if process_lower & _TRAINEE_SIGNALS or any(
            sig in title_lower or sig in notes_lower for sig in _TRAINEE_SIGNALS
        ):
            return "junior"
    return level


def to_job_description(obj: dict) -> dict:
    """Map a posting object to a JobDescription-compatible JSON dict.

    JobDescription fields (from BaseJobEntry + id + extra):
      id, title, company, stack, seniority (str), modality (str),
      location, description, url, extra
    """
    geo = obj.get("geo") or {}
    domain = obj.get("domain") or {}
    economics = obj.get("economics") or {}

    return {
        "id": obj["id"],
        "title": obj.get("title", ""),
        "company": obj.get("company", ""),
        "stack": obj.get("stack") or [],
        "seniority": fix_seniority(obj),
        "modality": obj.get("modality"),
        "location": clean_location(obj),
        "description": obj.get("notes"),
        "url": clean_url(obj.get("apply_url")),
        "extra": {
            "source": obj.get("source"),
            "posted_at": str(obj.get("posted_at")) if obj.get("posted_at") else None,
            "domain_tags": domain.get("tags", []),
            "geo_region": geo.get("region"),
            "process": obj.get("process") or [],
            "salary_eur_gross": economics.get("salary_eur_gross"),
            "title_canonical": obj.get("title_canonical"),
        },
    }


def extract(input_path: Path, output_dir: Path) -> int:
    output_dir.mkdir(parents=True, exist_ok=True)

    parse_errors = 0
    skipped_evidence = 0
    extracted = 0

    for line_no, line in enumerate(input_path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue

        try:
            obj = json.loads(line)
        except json.JSONDecodeError as e:
            parse_errors += 1
            logger.debug(f"Line {line_no}: JSON parse error — {e}")
            continue

        if not isinstance(obj, dict):
            continue

        if not is_posting(obj):
            skipped_evidence += 1
            continue

        jd = to_job_description(obj)
        out_file = output_dir / f"{jd['id']}.json"
        out_file.write_text(json.dumps(jd, indent=2, ensure_ascii=False), encoding="utf-8")
        extracted += 1
        logger.info(f"  [{extracted:02d}] {jd['company']} — {jd['title']}")

    print(f"\n{'=' * 60}")
    print("Profile-2 posting extraction")
    print(f"{'=' * 60}")
    print(f"  Extracted : {extracted} postings → {output_dir}/")
    print(f"  Skipped   : {skipped_evidence} evidence sub-objects")
    print(f"  Errors    : {parse_errors} unparseable lines")
    print()
    print("Next steps:")
    print("  1. Review examples/job_search/profile_example/candidate.json and adapt it as needed")
    print("  2. Build a gen_cv request per posting and execute task action:")
    print(f"     for f in {output_dir}/*.json; do")
    print("       python3 - <<'PY' \"$f\" > /tmp/gen_cv_request.json")
    print("import json,sys")
    print("job=json.load(open(sys.argv[1], encoding='utf-8'))")
    print(
        "candidate=json.load(open('examples/job_search/profile_example/candidate.json', encoding='utf-8'))"
    )
    print(
        "json.dump({'profile_id':'profile_example','job':job,'candidate_profile':candidate}, sys.stdout)"
    )
    print("PY")
    print(
        "       uv run structured-search task gen_cv action --action-name gen-cv --request /tmp/gen_cv_request.json \\"
    )
    print("         > results/gen_cv/profile_example/$(basename $f)")
    print("     done")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Extract clean JobDescription JSON files from a malformed profile_example result.jsonl"
    )
    parser.add_argument(
        "--input",
        default="results/job_search/profile_example/result.jsonl",
        help="Path to raw result.jsonl (default: results/job_search/profile_example/result.jsonl)",
    )
    parser.add_argument(
        "--output-dir",
        default="results/job_search/profile_example/postings",
        help="Output directory for extracted posting JSONs (default: results/job_search/profile_example/postings/)",
    )
    args = parser.parse_args(argv)

    input_path = Path(args.input)
    if not input_path.exists():
        logger.error(f"Input file not found: {input_path}")
        return 1

    return extract(input_path, Path(args.output_dir))


if __name__ == "__main__":
    raise SystemExit(main())
