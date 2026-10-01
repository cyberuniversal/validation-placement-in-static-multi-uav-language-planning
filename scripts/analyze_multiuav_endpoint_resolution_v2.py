"""Replay frozen M1 outputs with a strict concrete-URL resolver, post hoc."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
from typing import Any
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from shepherd_ai.multiuav_endpoint_resolution_v2 import (  # noqa: E402
    resolve_concrete_endpoints,
)
from shepherd_ai.multiuav_grounding_validator import (  # noqa: E402
    validate_grounded_plan,
)
from shepherd_ai.multiuav_plan_contract import (  # noqa: E402
    ApiCall,
    StrictModelOutput,
)
from shepherd_ai.multiuav_scoring import _official_command_match  # noqa: E402

PROTOCOL = ROOT / "datasets/multiuav_plat/endpoint_resolution_diagnostic_v2.json"
OUTPUT = ROOT / "outputs/evaluations/multiuav_endpoint_resolution_v2"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _bound_path(value: str, expected_sha256: str) -> Path:
    path = ROOT / value
    if _sha256(path) != expected_sha256:
        raise ValueError(f"input checksum mismatch: {value}")
    return path


def _load_scores(path: Path, model_id: str) -> dict[str, dict[str, Any]]:
    scores: dict[str, dict[str, Any]] = {}
    with ZipFile(path) as archive:
        for raw in archive.open("scored_rows.jsonl"):
            row = json.loads(raw)
            if row["method_id"] != "M1_monolithic":
                continue
            case_id = row["case_id"]
            if case_id in scores:
                raise ValueError(f"duplicate scored case: {case_id}")
            scores[case_id] = row
    if len(scores) != 1420:
        raise ValueError(f"expected 1420 M1 scored cases for {model_id}")
    return scores


def _parsed_output(payload: dict[str, Any]) -> StrictModelOutput:
    return StrictModelOutput(
        decision=payload["decision"],
        reason=payload["reason"],
        clarification_question=payload["clarification_question"],
        api_plan=tuple(
            ApiCall(call["endpoint"], dict(call["parameters"]))
            for call in payload["api_plan"]
        ),
    )


def _replay_model(
    model: dict[str, Any],
    *,
    output_dir: Path,
) -> dict[str, Any]:
    checkpoint = _bound_path(model["checkpoint"], model["checkpoint_sha256"])
    scored_archive = _bound_path(model["scored_rows"], model["scored_rows_sha256"])
    scores = _load_scores(scored_archive, model["model_id"])
    totals: Counter[str] = Counter()
    before_stages: Counter[str] = Counter()
    after_stages: Counter[str] = Counter()
    seen: set[str] = set()
    rows_path = output_dir / f"{model['short_name']}_derived_rows.jsonl"
    with ZipFile(checkpoint) as archive, rows_path.open("w", encoding="utf-8") as derived:
        for raw in archive.open("results.jsonl"):
            row = json.loads(raw)
            if row["method_id"] != "M1_monolithic":
                continue
            case_id = row["case_id"]
            if case_id in seen or case_id not in scores:
                raise ValueError(f"duplicate or unscored case: {case_id}")
            seen.add(case_id)
            score = scores[case_id]
            execute = score["registered_decision"] == "EXECUTE"
            totals["execute_cases" if execute else "nonexecute_cases"] += 1
            result = row["result"]
            parsed = result["final_parse"]["parsed"]
            before_stage = "parse_error"
            after_stage = "parse_error"
            resolved_calls = 0
            official_match = False
            if parsed is not None:
                context = json.loads(
                    result["calls"][0]["request"]["messages"][-1]["content"]
                )["AGENT_CONTEXT"]
                output = _parsed_output(parsed)
                before = validate_grounded_plan(output, context)
                resolved = resolve_concrete_endpoints(output, context)
                after = validate_grounded_plan(resolved.output, context)
                before_stage = before.containment_stage
                after_stage = after.containment_stage
                resolved_calls = resolved.resolved_calls
                totals["resolved_calls"] += resolved_calls
                if execute and after.valid:
                    official_match = _official_command_match(
                        score["planned_commands"], score["official_commands"]
                    )
                if output.decision == "EXECUTE" and before.valid:
                    totals["before_validator_admitted_execute" if execute else "before_validator_admitted_nonexecute"] += 1
                if output.decision == "EXECUTE" and after.valid:
                    totals["after_validator_admitted_execute" if execute else "after_validator_admitted_nonexecute"] += 1
                    if execute and official_match:
                        totals["potential_static_fidelity_execute"] += 1
            before_stages[before_stage] += 1
            after_stages[after_stage] += 1
            derived.write(
                json.dumps(
                    {
                        "case_id": case_id,
                        "model_id": model["model_id"],
                        "registered_decision": score["registered_decision"],
                        "raw_model_decision": score["raw_model_decision"],
                        "before_stage": before_stage,
                        "after_stage": after_stage,
                        "resolved_calls": resolved_calls,
                        "official_command_match_if_admitted": official_match,
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                )
                + "\n"
            )
    if seen != set(scores) or totals["execute_cases"] != 852 or totals["nonexecute_cases"] != 568:
        raise ValueError(f"M1 matrix does not match admitted score rows: {model['model_id']}")
    return {
        "model_id": model["model_id"],
        "model_revision": model["model_revision"],
        "counts": dict(sorted(totals.items())),
        "before_stage_counts": dict(sorted(before_stages.items())),
        "after_stage_counts": dict(sorted(after_stages.items())),
        "derived_rows": {
            "path": str(rows_path.relative_to(ROOT)).replace("\\", "/"),
            "sha256": _sha256(rows_path),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT)
    args = parser.parse_args()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    protocol = json.loads(PROTOCOL.read_text(encoding="utf-8"))
    models = [_replay_model(model, output_dir=output_dir) for model in protocol["models"]]
    summary = {
        "analysis_id": protocol["analysis_id"],
        "status": protocol["status"],
        "registered_study_changed": False,
        "new_model_inference": False,
        "protocol_sha256": _sha256(PROTOCOL),
        "source_sha256": _sha256(Path(__file__)),
        "resolver_sha256": _sha256(
            ROOT / "src/shepherd_ai/multiuav_endpoint_resolution_v2.py"
        ),
        "models": models,
        "interpretation": protocol["interpretation"],
    }
    (output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    for model in models:
        print(model["model_id"], model["counts"])


if __name__ == "__main__":
    main()
