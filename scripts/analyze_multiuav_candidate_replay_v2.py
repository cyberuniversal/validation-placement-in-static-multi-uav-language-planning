"""Replay frozen M1 traces through a test-contaminated follow-up candidate."""

from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from shepherd_ai.multiuav_candidate_v2 import evaluate_candidate  # noqa: E402
from shepherd_ai.multiuav_scoring import _official_command_match  # noqa: E402

from analyze_multiuav_endpoint_resolution_v2 import (  # noqa: E402
    PROTOCOL,
    _bound_path,
    _load_scores,
    _parsed_output,
)

OUTPUT = ROOT / "outputs/evaluations/multiuav_candidate_v2"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    protocol = json.loads(PROTOCOL.read_text(encoding="utf-8"))
    OUTPUT.mkdir(parents=True, exist_ok=True)
    models = []
    for model in protocol["models"]:
        scores = _load_scores(
            _bound_path(model["scored_rows"], model["scored_rows_sha256"]),
            model["model_id"],
        )
        seen: set[str] = set()
        counts: Counter[str] = Counter()
        rows_path = OUTPUT / f"{model['short_name']}_inspected_test_replay.jsonl"
        with ZipFile(
            _bound_path(model["checkpoint"], model["checkpoint_sha256"])
        ) as archive, rows_path.open("w", encoding="utf-8") as output:
            for raw in archive.open("results.jsonl"):
                row = json.loads(raw)
                if row["method_id"] != "M1_monolithic":
                    continue
                case_id = row["case_id"]
                if case_id in seen or case_id not in scores:
                    raise ValueError(f"duplicate or unscored case: {case_id}")
                seen.add(case_id)
                score = scores[case_id]
                label = score["registered_decision"]
                counts[f"label_{label.lower()}"] += 1
                parsed = row["result"]["final_parse"]["parsed"]
                decision = "NOT_EVALUATED"
                reason = "model_parse_error"
                released = False
                matched = False
                if parsed is None:
                    counts["parse_errors"] += 1
                else:
                    context = json.loads(
                        row["result"]["calls"][0]["request"]["messages"][-1]
                        ["content"]
                    )["AGENT_CONTEXT"]
                    report = evaluate_candidate(_parsed_output(parsed), context)
                    decision = report.decision
                    reason = report.reason_code
                    released = report.release_authorized
                    if released:
                        counts[
                            "released_execute" if label == "EXECUTE"
                            else "released_nonexecute"
                        ] += 1
                        if label == "EXECUTE":
                            matched = _official_command_match(
                                score["planned_commands"],
                                score["official_commands"],
                            )
                            if matched:
                                counts["potential_static_fidelity_execute"] += 1
                output.write(json.dumps({
                    "case_id": case_id,
                    "source_task_id": score["source_task_id"],
                    "variant": score["variant"],
                    "registered_decision": label,
                    "candidate_decision": decision,
                    "reason_code": reason,
                    "release_authorized": released,
                    "official_command_match_if_released": matched,
                }, sort_keys=True) + "\n")
        if seen != set(scores):
            raise ValueError(f"missing M1 cases for {model['model_id']}")
        models.append({
            "model_id": model["model_id"],
            "model_revision": model["model_revision"],
            "counts": {
                key: counts[key]
                for key in (
                    "label_execute", "label_clarify", "label_block",
                    "parse_errors", "released_execute", "released_nonexecute",
                    "potential_static_fidelity_execute",
                )
            },
            "rows_path": str(rows_path.relative_to(ROOT)).replace("\\", "/"),
            "rows_sha256": _sha256(rows_path),
        })
    summary = {
        "status": "retrospective_test_contaminated_engineering_diagnostic",
        "model_inference_performed": False,
        "frozen_study_changed": False,
        "protocol_sha256": _sha256(PROTOCOL),
        "candidate_sha256": _sha256(
            ROOT / "src/shepherd_ai/multiuav_candidate_v2.py"
        ),
        "source_sha256": _sha256(Path(__file__)),
        "models": models,
        "interpretation": (
            "The previously inspected test traces informed candidate design. "
            "These counts are not prospective held-out performance; "
            "the screen matches generator artifacts, and some generated "
            "missing-fact labels retain the removed value."
        ),
    }
    (OUTPUT / "inspected_test_replay_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(models, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
