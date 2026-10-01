"""Exercise a bounded AGENT observation-command loop on reviewed training tasks."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys
from typing import Any, Callable, Mapping

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "external/MultiUAV-Plat/server"))

from scripts.probe_multiuav_train_observations_v2 import (  # noqa: E402
    EXPECTED_BENCHMARK_SHA256,
    EXPECTED_UPSTREAM_COMMIT,
    load_source_session,
    require_agent_response,
    session_payload,
    sha256,
)
from scripts.run_multiuav_train_pilot_v2 import select_cases  # noqa: E402


def select_action(
    instruction: str,
    drones: list[dict[str, Any]],
    nearby_targets: Mapping[str, list[dict[str, Any]]],
    canvas: tuple[float, float],
    previous_destinations: set[tuple[float, float]],
) -> dict[str, Any] | None:
    """Choose a local target or bounded search move from visible state only."""

    if not drones:
        return None
    ordered = sorted(drones, key=lambda item: str(item["id"]))
    named_choices = [
        (drone, target)
        for drone in ordered
        for target in sorted(
            nearby_targets.get(str(drone["id"]), []),
            key=lambda item: str(item["id"]),
        )
        if str(target["name"]).casefold() in instruction.casefold()
        and all(
            math.isfinite(float(target["position"][axis]))
            and 0 <= float(target["position"][axis]) <= canvas[index]
            for index, axis in enumerate(("x", "y"))
        )
        and (
            float(target["position"]["x"]),
            float(target["position"]["y"]),
        ) not in previous_destinations
    ]
    drone = named_choices[0][0] if named_choices else ordered[0]
    drone_id = str(drone["id"])
    position = drone["position"]
    if float(position["z"]) <= 0:
        altitude = min(10.0, float(drone["max_altitude"]))
        if altitude <= 0:
            return None
        return {"command": "take_off", "drone_id": drone_id, "altitude": altitude}

    for selected_drone, target in named_choices:
        if selected_drone["id"] != drone_id:
            continue
        target_position = target["position"]
        destination = (float(target_position["x"]), float(target_position["y"]))
        return {
            "command": "move_to", "drone_id": drone_id,
            "x": destination[0], "y": destination[1],
            "source": "agent_local_target_observation",
        }

    radius = float(drone["perceived_radius"])
    width, height = canvas
    if not all(math.isfinite(value) and value > 0 for value in (radius, width, height)):
        return None
    step = radius
    x, y = float(position["x"]), float(position["y"])
    candidates = (
        (x + step, y), (x, y + step), (x - step, y), (x, y - step),
    )
    for destination in candidates:
        if (0 <= destination[0] <= width and 0 <= destination[1] <= height
                and destination not in previous_destinations):
            return {
                "command": "move_to", "drone_id": drone_id,
                "x": destination[0], "y": destination[1],
                "source": "bounded_local_search",
            }
    return None


def agent_snapshot(client: Any, headers: dict[str, str]) -> dict[str, Any]:
    drones = require_agent_response(client.get("/drones", headers=headers))
    targets = {
        str(drone["id"]): require_agent_response(
            client.get(f"/drones/{drone['id']}/nearby/targets", headers=headers)
        )
        for drone in drones
    }
    progress = require_agent_response(
        client.get("/sessions/current/task-progress", headers=headers)
    )
    return {"drones": drones, "nearby_targets_by_drone": targets, "task_progress": progress}


def issue_action(client: Any, headers: dict[str, str], action: Mapping[str, Any]) -> dict[str, Any]:
    drone_id = action["drone_id"]
    if action["command"] == "take_off":
        path = f"/drones/{drone_id}/command/take_off"
        params = {"altitude": action["altitude"]}
    elif action["command"] == "move_to":
        path = f"/drones/{drone_id}/command/move_to"
        params = {"x": action["x"], "y": action["y"]}
    else:
        raise ValueError("unsupported pilot command")
    response = client.post(path, params=params, headers=headers)
    return {"http_status": response.status_code, "body": response.json()}


def run_case(
    client: Any,
    headers: dict[str, str],
    case: Mapping[str, Any],
    *,
    max_commands: int,
    choose_action: Callable[
        [str, list[dict[str, Any]], Mapping[str, list[dict[str, Any]]],
         tuple[float, float], set[tuple[float, float]]], dict[str, Any] | None,
    ] = select_action,
    on_command: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    if max_commands < 1 or max_commands > 12:
        raise ValueError("pilot command budget must be between 1 and 12")
    denied = client.get("/sessions/current/data", headers=headers)
    if denied.status_code != 403:
        raise RuntimeError("AGENT unexpectedly accessed privileged session data")
    canvas = (
        float(case["context"]["session"]["canvas_width"]),
        float(case["context"]["session"]["canvas_height"]),
    )
    snapshots = [agent_snapshot(client, headers)]
    commands: list[dict[str, Any]] = []
    destinations: set[tuple[float, float]] = set()
    stop_reason = "command_budget_exhausted"
    for _ in range(max_commands):
        state = snapshots[-1]
        action = choose_action(
            case["context"]["instruction"], state["drones"],
            state["nearby_targets_by_drone"], canvas, destinations,
        )
        if action is None:
            stop_reason = "no_bounded_action"
            break
        if action["command"] == "move_to":
            destinations.add((action["x"], action["y"]))
        response = issue_action(client, headers, action)
        command_record = {"action": action, "response": response}
        commands.append(command_record)
        if on_command is not None:
            on_command(command_record)
        snapshots.append(agent_snapshot(client, headers))
        if response["http_status"] != 200 or response["body"].get("status") != "success":
            stop_reason = "command_rejected_or_failed"
            break
    task_id = case["source_task_id"]
    task_check = client.get(f"/sessions/current/tasks/{task_id}/check", headers=headers)
    if task_check.status_code != 200:
        raise RuntimeError(f"AGENT task check returned HTTP {task_check.status_code}")
    return {
        "snapshots": snapshots, "commands": commands,
        "stop_reason": stop_reason, "task_check": task_check.json(),
        "agent_privileged_data_http_status": denied.status_code,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--max-commands", type=int, default=4)
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

    headers = {"X-API-Key": ROLE_SECRETS[UserRole.AGENT]}
    with TestClient(app) as client:
        setup = session_payload(source, case["source_task_id"])
        setup["id"] = source["id"]
        restored = session_controller.create_session_from_dict(setup)
        session_controller.sessions[restored.id] = restored
        if session_controller.set_current_session(restored.id) is None:
            raise RuntimeError("official session controller did not activate training session")
        result = run_case(client, headers, case, max_commands=args.max_commands)

    raw = {
        "case_id": case["case_id"], "source_task_id": case["source_task_id"],
        "session_id": case["session_id"], "run": result,
    }
    args.raw_output.parent.mkdir(parents=True, exist_ok=True)
    args.raw_output.write_text(json.dumps(raw, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    seen_initial = {
        str(target["id"])
        for targets in result["snapshots"][0]["nearby_targets_by_drone"].values()
        for target in targets
    }
    seen_final = {
        str(target["id"])
        for targets in result["snapshots"][-1]["nearby_targets_by_drone"].values()
        for target in targets
    }
    summary = {
        "status": "train_only_scripted_agent_loop_not_model_or_paper_evaluation",
        "case_id": case["case_id"], "source_task_id": case["source_task_id"],
        "session_id": case["session_id"],
        "benchmark_sha256": EXPECTED_BENCHMARK_SHA256,
        "upstream_commit": EXPECTED_UPSTREAM_COMMIT,
        "raw_sha256": sha256(args.raw_output),
        "max_commands": args.max_commands,
        "attempted_commands": len(result["commands"]),
        "successful_commands": sum(
            item["response"]["http_status"] == 200
            and item["response"]["body"].get("status") == "success"
            for item in result["commands"]
        ),
        "initial_locally_observed_target_count": len(seen_initial),
        "final_locally_observed_target_count": len(seen_final),
        "task_check_result": result["task_check"].get("result"),
        "stop_reason": result["stop_reason"],
        "agent_privileged_data_http_status": result["agent_privileged_data_http_status"],
        "model_loaded": False,
        "policy": "deterministic_visible_target_or_local_search_v1",
    }
    args.summary_output.parent.mkdir(parents=True, exist_ok=True)
    args.summary_output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
