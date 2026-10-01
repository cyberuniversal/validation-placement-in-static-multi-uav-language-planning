"""Probe official AGENT local perception on one reviewed training session."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from typing import Any, Mapping
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "external/MultiUAV-Plat/server"))

from scripts.run_multiuav_train_pilot_v2 import select_cases  # noqa: E402

BENCHMARK = ROOT / "external/MultiUAV-Plat/benchmark/benchmark.zip"
UPSTREAM = ROOT / "external/MultiUAV-Plat"
EXPECTED_BENCHMARK_SHA256 = (
    "b5040097d2bfdd44600f3bf486fdb43ee3eb1247fec9c67900b5fcda6feb94a3"
)
EXPECTED_UPSTREAM_COMMIT = "1794e45e421fb5de03094f0b63f9ca95f86ab42f"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def session_payload(session: Mapping[str, Any], source_task_id: str) -> dict[str, Any]:
    """Restore one task and its world through the server setup path."""

    tasks = [task for task in session["tasks"] if task["id"] == source_task_id]
    if len(tasks) != 1:
        raise ValueError("selected training task is absent or duplicated")
    return {
        key: session[key]
        for key in (
            "name", "description", "task_type", "task_description",
            "is_distance_3d", "canvas_width", "canvas_height", "drones",
            "targets", "obstacles", "environment",
        )
    } | {"tasks": tasks, "with_examples": False}


def require_agent_response(response: Any) -> Any:
    if response.status_code != 200:
        raise RuntimeError(f"AGENT observation returned HTTP {response.status_code}")
    return response.json()


def load_source_session(session_id: str) -> dict[str, Any]:
    if sha256(BENCHMARK) != EXPECTED_BENCHMARK_SHA256:
        raise ValueError("benchmark archive differs from pinned source")
    commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=UPSTREAM, text=True
    ).strip()
    if commit != EXPECTED_UPSTREAM_COMMIT:
        raise ValueError("upstream checkout differs from pinned source")
    with ZipFile(BENCHMARK) as archive:
        matches = []
        for member in archive.namelist():
            if member.endswith(".json"):
                session = json.loads(archive.read(member))
                if session.get("id") == session_id:
                    matches.append(session)
    if len(matches) != 1:
        raise ValueError("selected training session is absent or duplicated")
    return matches[0]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--raw-output", required=True, type=Path)
    parser.add_argument("--summary-output", required=True, type=Path)
    args = parser.parse_args()
    selected = {case["case_id"]: case for case in select_cases()}
    if args.case_id not in selected:
        raise ValueError("case must be a reviewed canonical training pilot case")
    case = selected[args.case_id]
    source = load_source_session(case["session_id"])

    from fastapi.testclient import TestClient  # noqa: PLC0415
    from api.server import ROLE_SECRETS, UserRole, app, session_controller  # noqa: PLC0415

    agent_headers = {"X-API-Key": ROLE_SECRETS[UserRole.AGENT]}
    print("stage=client_ready", flush=True)
    with TestClient(app) as client:
        print("stage=server_started", flush=True)
        setup = session_payload(source, case["source_task_id"])
        setup["id"] = source["id"]
        restored = session_controller.create_session_from_dict(setup)
        session_controller.sessions[restored.id] = restored
        activated = session_controller.set_current_session(restored.id)
        if activated is None:
            raise RuntimeError("official session controller did not activate training session")
        print("stage=training_session_active_controller_setup", flush=True)
        denied = client.get("/sessions/current/data", headers=agent_headers)
        print(f"stage=privileged_probe_http_{denied.status_code}", flush=True)
        if denied.status_code != 403:
            raise RuntimeError("AGENT unexpectedly accessed privileged session data")
        drones = require_agent_response(client.get("/drones", headers=agent_headers))
        print(f"stage=agent_drones_read_count_{len(drones)}", flush=True)
        observations = {
            str(drone["id"]): require_agent_response(
                client.get(f"/drones/{drone['id']}/nearby/targets", headers=agent_headers)
            )
            for drone in drones
        }

    raw = {
        "case_id": case["case_id"],
        "session_id": case["session_id"],
        "agent_drones": drones,
        "agent_nearby_targets_by_drone": observations,
    }
    args.raw_output.parent.mkdir(parents=True, exist_ok=True)
    args.raw_output.write_text(json.dumps(raw, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    seen = {str(target["id"]) for targets in observations.values() for target in targets}
    summary = {
        "status": "train_only_official_agent_observation_feasibility_not_paper_evaluation",
        "case_id": case["case_id"],
        "source_task_id": case["source_task_id"],
        "session_id": case["session_id"],
        "benchmark_sha256": sha256(BENCHMARK),
        "upstream_commit": EXPECTED_UPSTREAM_COMMIT,
        "raw_agent_observations_sha256": sha256(args.raw_output),
        "agent_drone_count": len(drones),
        "source_target_count_setup_only": len(source["targets"]),
        "distinct_locally_observed_target_count": len(seen),
        "nearby_target_counts_by_drone": {
            drone_id: len(targets) for drone_id, targets in sorted(observations.items())
        },
        "agent_privileged_data_http_status": denied.status_code,
        "setup_method": "official_session_controller_direct_not_http_post",
        "model_loaded": False,
        "drone_command_issued": False,
        "simulator_task_evaluated": False,
    }
    args.summary_output.parent.mkdir(parents=True, exist_ok=True)
    args.summary_output.write_text(
        json.dumps(summary, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
