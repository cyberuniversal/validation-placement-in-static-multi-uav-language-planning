"""Validate and aggregate train-only official AGENT observation probes."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from scripts.probe_multiuav_train_observations_v2 import (  # noqa: E402
    EXPECTED_BENCHMARK_SHA256,
    EXPECTED_UPSTREAM_COMMIT,
    sha256,
)
from scripts.run_multiuav_train_pilot_v2 import select_cases  # noqa: E402


def aggregate(root: Path, expected_cases: list[dict[str, Any]]) -> dict[str, Any]:
    """Reject incomplete or inconsistent raw/summary pairs before counting."""

    expected_by_id = {case["case_id"]: case for case in expected_cases}
    expected_ids = set(expected_by_id)
    if len(expected_by_id) != len(expected_cases):
        raise ValueError("selected case IDs are duplicated")
    observed_ids: set[str] = set()
    observed_sessions: set[str] = set()
    rows: list[dict[str, Any]] = []
    for path in sorted(root.glob("*/summary.json")):
        summary = json.loads(path.read_text(encoding="utf-8"))
        case_id = summary["case_id"]
        if case_id not in expected_ids or case_id in observed_ids:
            raise ValueError(f"unexpected or duplicate training case: {case_id}")
        expected = expected_by_id[case_id]
        if (summary["session_id"] != expected["session_id"]
                or summary["source_task_id"] != expected["source_task_id"]):
            raise ValueError(f"training selection identity mismatch: {case_id}")
        if summary["status"] != "train_only_official_agent_observation_feasibility_not_paper_evaluation":
            raise ValueError(f"unexpected probe status: {case_id}")
        raw_path = path.with_name("raw_agent_observations.json")
        if sha256(raw_path) != summary["raw_agent_observations_sha256"]:
            raise ValueError(f"raw observation checksum mismatch: {case_id}")
        raw = json.loads(raw_path.read_text(encoding="utf-8"))
        session_id = summary["session_id"]
        if raw["case_id"] != case_id or raw["session_id"] != session_id:
            raise ValueError(f"raw observation identity mismatch: {case_id}")
        if session_id in observed_sessions:
            raise ValueError(f"duplicate training session: {session_id}")
        observed_sessions.add(session_id)
        observed_ids.add(case_id)
        if summary["benchmark_sha256"] != EXPECTED_BENCHMARK_SHA256:
            raise ValueError(f"unexpected benchmark: {case_id}")
        if summary["upstream_commit"] != EXPECTED_UPSTREAM_COMMIT:
            raise ValueError(f"unexpected upstream commit: {case_id}")
        if summary["agent_privileged_data_http_status"] != 403:
            raise ValueError(f"AGENT role boundary failed: {case_id}")
        for key in ("model_loaded", "drone_command_issued", "simulator_task_evaluated"):
            if summary[key] is not False:
                raise ValueError(f"unexpected activity {key}: {case_id}")
        if summary["setup_method"] != "official_session_controller_direct_not_http_post":
            raise ValueError(f"unexpected setup method: {case_id}")
        drones = raw["agent_drones"]
        observations = raw["agent_nearby_targets_by_drone"]
        if len(drones) != summary["agent_drone_count"]:
            raise ValueError(f"drone count mismatch: {case_id}")
        if {str(drone["id"]) for drone in drones} != set(observations):
            raise ValueError(f"drone observation set mismatch: {case_id}")
        actual_counts = {key: len(value) for key, value in sorted(observations.items())}
        if actual_counts != summary["nearby_target_counts_by_drone"]:
            raise ValueError(f"per-drone target count mismatch: {case_id}")
        distinct_ids = {
            str(target["id"])
            for targets in observations.values()
            for target in targets
        }
        count = len(distinct_ids)
        if count != summary["distinct_locally_observed_target_count"]:
            raise ValueError(f"distinct target count mismatch: {case_id}")
        if count > summary["source_target_count_setup_only"]:
            raise ValueError(f"observed more targets than the restored source world: {case_id}")
        rows.append({
            "case_id": case_id,
            "session_id": session_id,
            "agent_drone_count": len(drones),
            "source_target_count_setup_only": summary["source_target_count_setup_only"],
            "distinct_locally_observed_target_count": count,
            "raw_agent_observations_sha256": summary["raw_agent_observations_sha256"],
        })
    if observed_ids != expected_ids:
        raise ValueError(f"missing training cases: {sorted(expected_ids - observed_ids)}")
    return {
        "status": "train_only_official_agent_observation_feasibility_not_paper_evaluation",
        "benchmark_sha256": EXPECTED_BENCHMARK_SHA256,
        "upstream_commit": EXPECTED_UPSTREAM_COMMIT,
        "case_count": len(rows),
        "distinct_session_count": len(observed_sessions),
        "cases_with_no_locally_observed_targets": sum(
            row["distinct_locally_observed_target_count"] == 0 for row in rows
        ),
        "cases_with_locally_observed_targets": sum(
            row["distinct_locally_observed_target_count"] > 0 for row in rows
        ),
        "all_agent_privileged_data_http_status": 403,
        "model_loaded": False,
        "drone_command_issued": False,
        "simulator_task_evaluated": False,
        "cases": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = aggregate(args.root, select_cases())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({key: result[key] for key in (
        "case_count", "distinct_session_count", "cases_with_no_locally_observed_targets",
        "cases_with_locally_observed_targets",
    )}, sort_keys=True))


if __name__ == "__main__":
    main()
