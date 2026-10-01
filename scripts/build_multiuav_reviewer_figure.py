"""Build the reviewer-revised, refusal-aware primary outcomes figure."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from shepherd_ai.multiuav_reviewer_analysis import (  # noqa: E402
    build_refusal_aware_outcomes_figure,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scoring-summary",
        type=Path,
        default=ROOT / "outputs/evaluations/multiuav_accuracy_scoring_v1/summary.json",
    )
    parser.add_argument(
        "--reviewer-summary",
        type=Path,
        default=ROOT / "outputs/evaluations/multiuav_reviewer_analysis_v1/summary.json",
    )
    parser.add_argument(
        "--output-stem",
        type=Path,
        default=ROOT / "paper/figures/accuracy_refusal_aware_outcomes_v2",
    )
    args = parser.parse_args()
    scoring = json.loads(args.scoring_summary.read_text(encoding="utf-8-sig"))
    reviewer = json.loads(args.reviewer_summary.read_text(encoding="utf-8-sig"))
    outputs = build_refusal_aware_outcomes_figure(
        scoring_summary=scoring,
        reviewer_summary=reviewer,
        output_stem=args.output_stem,
    )
    manifest = {
        "schema_version": 1,
        "status": "reviewer_revised_figure_complete",
        "source_files": [_record(args.scoring_summary), _record(args.reviewer_summary)],
        "outputs": [_record(path) for path in outputs],
        "claim_limit": (
            "Always BLOCK is a post-hoc deterministic reference and not a registered "
            "model baseline. Both plotted outcomes are positively oriented."
        ),
    }
    output = args.output_stem.parent / "accuracy_refusal_aware_outcomes_v2_manifest.json"
    output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2, sort_keys=True))


def _record(path: Path) -> dict:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    try:
        rendered = path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        rendered = path.resolve().as_posix()
    return {"path": rendered, "bytes": path.stat().st_size, "sha256": digest}


if __name__ == "__main__":
    main()
