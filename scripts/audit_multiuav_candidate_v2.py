"""Audit the agent-visible screen against generated train/calibration labels."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from shepherd_ai.multiuav_candidate_v2 import screen_visible_request  # noqa: E402
from shepherd_ai.multiuav_interventions import materialize_case_context  # noqa: E402

DATASET = ROOT / "datasets/multiuav_plat/intervention_dataset_v1.json"
OUTPUT = ROOT / "outputs/evaluations/multiuav_candidate_v2"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", choices=("train", "calibration"), default="train")
    args = parser.parse_args()
    split = args.split
    clusters = json.loads(DATASET.read_text(encoding="utf-8"))["clusters"]
    rows: list[dict] = []
    confusion: Counter[tuple[str, str]] = Counter()
    retained_fact_count = 0
    for cluster in clusters:
        if cluster["split"] != split:
            continue
        for case in cluster["cases"]:
            context = materialize_case_context(cluster, case)
            decision, reason = screen_visible_request(context)
            registered = case["proposed_decision"]
            confusion[(registered, decision)] += 1
            retained_fact = False
            if case["variant"] == "missing_information_clarify":
                retained_fact = any(
                    re.search(
                        r"(?<![A-Za-z0-9])" + re.escape(value) + r"(?![A-Za-z0-9])",
                        context["instruction"],
                        re.IGNORECASE,
                    )
                    for value in cluster["intervention"]["removed_values"]
                )
                retained_fact_count += retained_fact
            rows.append({
                "case_id": case["case_id"],
                "source_task_id": cluster["source_task_id"],
                "session_id": cluster["session_id"],
                "split": split,
                "fact_kind": cluster["intervention"]["missing_fact_kind"],
                "variant": case["variant"],
                "proposed_decision": registered,
                "screen_decision": decision,
                "reason_code": reason,
                "removed_fact_still_literal_in_instruction": retained_fact,
            })
    if not rows:
        raise ValueError(f"no cases found for {split}")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    rows_path = OUTPUT / f"{split}_screen_rows.jsonl"
    rows_path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )
    summary = {
        "status": "generated_label_screen_audit_not_model_evaluation",
        "split": split,
        "clusters": len({row["source_task_id"] for row in rows}),
        "cases": len(rows),
        "confusion": [
            {"proposed_decision": expected, "screen_decision": actual, "count": count}
            for (expected, actual), count in sorted(confusion.items())
        ],
        "removed_fact_still_literal_in_missing_instruction": retained_fact_count,
        "dataset_sha256": _sha256(DATASET),
        "candidate_sha256": _sha256(
            ROOT / "src/shepherd_ai/multiuav_candidate_v2.py"
        ),
        "rows_sha256": _sha256(rows_path),
        "interpretation": (
            "Checks a deterministic screen against generated proposed labels only; "
            "no model output, official execution, or independent human adjudication."
        ),
    }
    (OUTPUT / f"{split}_screen_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
