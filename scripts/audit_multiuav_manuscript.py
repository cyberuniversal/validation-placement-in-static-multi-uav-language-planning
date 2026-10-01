"""Audit aggregate evidence and claim boundaries in the active manuscript."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from shepherd_ai.multiuav_manuscript_audit import (  # noqa: E402
    audit_multiuav_manuscript,
    render_manuscript_audit,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--manuscript", type=Path, default=None)
    parser.add_argument("--resource-manifest", type=Path, default=None)
    parser.add_argument("--reviewer-summary", type=Path, default=None)
    parser.add_argument(
        "--output-json",
        type=Path,
        default=(
            ROOT
            / "outputs"
            / "evaluations"
            / "multiuav_manuscript_traceability_v1.json"
        ),
    )
    parser.add_argument(
        "--output-markdown",
        type=Path,
        default=ROOT / "reports" / "multiuav_manuscript_traceability_v1.md",
    )
    args = parser.parse_args()

    audit = audit_multiuav_manuscript(
        args.root,
        manuscript_path=args.manuscript,
        resource_manifest_path=args.resource_manifest,
        reviewer_summary_path=args.reviewer_summary,
    )
    audit["source_code_sha256"]["audit_multiuav_manuscript.py"] = _sha256_file(
        Path(__file__)
    )
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_markdown.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(audit, indent=2, sort_keys=True) + "\n"
    args.output_json.write_bytes(rendered.encode("utf-8"))
    args.output_markdown.write_bytes(render_manuscript_audit(audit).encode("utf-8"))
    print(rendered, end="")
    if not audit["valid"]:
        raise SystemExit(1)


def _sha256_file(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


if __name__ == "__main__":
    main()
