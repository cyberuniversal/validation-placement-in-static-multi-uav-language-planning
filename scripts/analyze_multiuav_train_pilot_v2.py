"""Classify a completed reviewed-train pilot without copying raw model text."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from shepherd_ai.multiuav_candidate_v2 import evaluate_candidate  # noqa: E402
from shepherd_ai.multiuav_plan_contract import parse_strict_model_output  # noqa: E402
from shepherd_ai.multiuav_scoring import _official_command_match  # noqa: E402

from scripts.run_multiuav_train_pilot_v2 import (  # noqa: E402
    DATASET,
    MODEL_ID,
    MODEL_REVISION,
    REVIEW,
    _lf_checkout_sha256,
    _registered_crlf_sha256,
    select_cases,
)

DEFAULT_BENCHMARK = ROOT / "external/MultiUAV-Plat/benchmark/benchmark.zip"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _official_commands(archive_path: Path, selected: set[str]) -> dict[str, list[str]]:
    expected_hash = json.loads(DATASET.read_text(encoding="utf-8"))[
        "metadata"
    ]["source_archive_sha256"]
    if _sha256(archive_path) != expected_hash:
        raise ValueError("benchmark archive hash differs from reviewed pilot")
    commands = {}
    with ZipFile(archive_path) as archive:
        for member in archive.namelist():
            if not member.endswith(".json"):
                continue
            session = json.loads(archive.read(member))
            for task in session["tasks"]:
                task_id = task["id"]
                if task_id in selected:
                    commands[task_id] = task["commands"]
    if set(commands) != selected:
        raise ValueError("benchmark archive does not contain selected tasks")
    return commands


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", required=True, type=Path)
    parser.add_argument("--run-summary", required=True, type=Path)
    parser.add_argument("--benchmark", type=Path, default=DEFAULT_BENCHMARK)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    run_summary = json.loads(args.run_summary.read_text(encoding="utf-8"))
    if run_summary["status"] != "complete_raw_unscored":
        raise ValueError("pilot raw run is not complete")
    config = run_summary["configuration"]
    selected = {case["case_id"]: case for case in select_cases()}
    if (
        config["model_id"] != MODEL_ID
        or config["model_revision"] != MODEL_REVISION
        or set(config["case_ids"]) != set(selected)
        or config["dataset_sha256"] != _registered_crlf_sha256(DATASET)
        or config["dataset_checkout_sha256"] not in {
            _sha256(DATASET), _lf_checkout_sha256(DATASET)
        }
        or config["review_sha256"] != _registered_crlf_sha256(REVIEW)
        or config["review_checkout_sha256"] not in {
            _sha256(REVIEW), _lf_checkout_sha256(REVIEW)
        }
        or run_summary["raw_results_sha256"] != _sha256(args.results)
    ):
        raise ValueError("raw run does not match selected training pilot")
    official = _official_commands(
        args.benchmark, {case["source_task_id"] for case in selected.values()}
    )
    seen: set[str] = set()
    counts: Counter[str] = Counter()
    derived = []
    for line in args.results.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        case_id = row["case_id"]
        if (
            case_id in seen
            or case_id not in selected
            or row["run_hash"] != run_summary["run_hash"]
        ):
            raise ValueError("raw row is duplicate or differs from frozen pilot")
        seen.add(case_id)
        case = selected[case_id]
        if row["generation"]["generation_status"] != "GENERATED":
            raise ValueError("pilot contains a failed model generation")
        parsed = parse_strict_model_output(row["generation"]["raw_output"])
        if parsed.parsed is None:
            stage = "model_parse_error"
            planned_commands: tuple[str, ...] = ()
            released = False
            official_match = False
        else:
            report = evaluate_candidate(parsed.parsed, case["context"])
            released = report.release_authorized
            stage = report.reason_code if report.reason_code != "postplan_rejected" else (
                report.postplan_stage or "postplan_rejected"
            )
            planned_commands = tuple(
                call.endpoint.rsplit("/", 1)[-1]
                for call in parsed.parsed.api_plan
            )
            official_match = released and _official_command_match(
                planned_commands, official[case["source_task_id"]]
            )
            if released and not official_match:
                stage = "released_wrong_command_sequence"
        counts[stage] += 1
        derived.append({
            "case_id": case_id,
            "source_task_id": case["source_task_id"],
            "session_id": case["session_id"],
            "scenario": case["scenario"],
            "difficulty": case["difficulty"],
            "stage": stage,
            "released": released,
            "official_command_match": official_match,
            "planned_commands": list(planned_commands),
            "official_commands": official[case["source_task_id"]],
        })
    if seen != set(selected):
        raise ValueError("pilot raw rows are incomplete")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    rows_path = args.output_dir / "derived_rows.jsonl"
    rows_path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in derived),
        encoding="utf-8",
    )
    analysis = {
        "status": "reviewed_train_pilot_diagnostic_not_paper_evaluation",
        "model_id": MODEL_ID,
        "model_revision": MODEL_REVISION,
        "code_commit": config["code_commit"],
        "run_hash": run_summary["run_hash"],
        "raw_results_sha256": _sha256(args.results),
        "benchmark_sha256": _sha256(args.benchmark),
        "derived_rows_sha256": _sha256(rows_path),
        "counts": dict(sorted(counts.items())),
        "case_count": len(derived),
        "simulator_execution": False,
    }
    (args.output_dir / "summary.json").write_text(
        json.dumps(analysis, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(analysis, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
