"""Run a bounded, model-driven AGENT loop on one reviewed training task."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "external/MultiUAV-Plat/server"))

from shepherd_ai.multiuav_model_cache import verify_cached_snapshot  # noqa: E402
from shepherd_ai.multiuav_prompts import PromptMessage, PromptRequest  # noqa: E402
from shepherd_ai.multiuav_qwen_backend import LocalQwenBackend, QwenBackendConfig  # noqa: E402
from shepherd_ai.multiuav_runner import ModelBackend  # noqa: E402
from scripts.probe_multiuav_train_closed_loop_v2 import run_case  # noqa: E402
from scripts.probe_multiuav_train_observations_v2 import (  # noqa: E402
    EXPECTED_BENCHMARK_SHA256,
    EXPECTED_UPSTREAM_COMMIT,
    load_source_session,
    session_payload,
    sha256,
)
from scripts.run_multiuav_train_pilot_v2 import (  # noqa: E402
    MODEL_ID,
    MODEL_REVISION,
    SEED,
    select_cases,
)

ACTION_SCHEMA = {
    "actions": ["TAKE_OFF", "MOVE_TO_OBSERVED_TARGET", "SEARCH", "STOP"],
    "fields": ["action", "drone_id", "target_id", "direction"],
    "search_directions": ["NORTH", "EAST", "SOUTH", "WEST"],
}
_DIRECTION = {
    "NORTH": (0, 1), "EAST": (1, 0),
    "SOUTH": (0, -1), "WEST": (-1, 0),
}


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def build_request(
    instruction: str,
    drones: list[dict[str, Any]],
    nearby_targets: Mapping[str, list[dict[str, Any]]],
    canvas: tuple[float, float],
    previous_destinations: set[tuple[float, float]],
    call_index: int,
) -> PromptRequest:
    """Expose only current AGENT observations and a high-level action catalog."""

    visible = {
        "instruction": instruction,
        "canvas": {"width": canvas[0], "height": canvas[1]},
        "drones": [
            {
                key: drone[key]
                for key in ("id", "name", "status", "position", "max_altitude", "perceived_radius")
            }
            for drone in drones
        ],
        "nearby_targets_by_drone": {
            drone_id: [
                {key: target[key] for key in ("id", "name", "position")}
                for target in targets
            ]
            for drone_id, targets in nearby_targets.items()
        },
        "allowed_actions_by_drone": {
            str(drone["id"]): (
                ["TAKE_OFF", "STOP"]
                if float(drone["position"]["z"]) <= 0
                else (["MOVE_TO_OBSERVED_TARGET", "SEARCH", "STOP"]
                      if nearby_targets.get(str(drone["id"])) else ["SEARCH", "STOP"])
            )
            for drone in drones
        },
        "previous_destinations": [list(point) for point in sorted(previous_destinations)],
        "action_schema": ACTION_SCHEMA,
    }
    messages = (
        PromptMessage(
            role="system",
            content=(
                "You control one bounded step of a training-only simulated UAV task. "
                "Return exactly one JSON object with keys action, drone_id, target_id, direction. "
                "Use null for unused fields. MOVE_TO_OBSERVED_TARGET requires a target ID "
                "in that drone's nearby_targets_by_drone list. SEARCH uses a cardinal "
                "direction and only a short bounded step. Never invent coordinates, "
                "target IDs, or drone IDs. Follow allowed_actions_by_drone: a "
                "grounded drone must TAKE_OFF before SEARCH or MOVE_TO_OBSERVED_TARGET. "
                "STOP when evidence is insufficient."
            ),
        ),
        PromptMessage(role="user", content=_canonical(visible)),
    )
    payload = [message.to_dict() for message in messages]
    return PromptRequest(
        prompt_contract_version="train_closed_loop_high_level_v2",
        method_id="train_followup_not_M1_to_M4",
        call_index=call_index,
        purpose="one_agent_visible_action",
        messages=messages,
        response_contract=ACTION_SCHEMA,
        context_sha256=_hash_text(_canonical(visible)),
        request_sha256=_hash_text(_canonical(payload)),
    )


def resolve_model_action(
    raw: str,
    drones: list[dict[str, Any]],
    nearby_targets: Mapping[str, list[dict[str, Any]]],
    canvas: tuple[float, float],
    previous_destinations: set[tuple[float, float]],
) -> tuple[dict[str, Any] | None, str]:
    """Fail closed unless the model's choice resolves from current visible state."""

    try:
        value = json.loads(raw, object_pairs_hook=_unique_pairs)
    except (ValueError, TypeError):
        return None, "invalid_json"
    if not isinstance(value, dict) or set(value) != set(ACTION_SCHEMA["fields"]):
        return None, "action_schema_mismatch"
    action = value["action"]
    if action == "STOP":
        if any(value[key] is not None for key in ("drone_id", "target_id", "direction")):
            return None, "stop_has_parameters"
        return None, "model_stop"
    if action not in ACTION_SCHEMA["actions"]:
        return None, "unknown_action"
    drone = next((item for item in drones if item["id"] == value["drone_id"]), None)
    if drone is None:
        return None, "unknown_drone"
    drone_id = str(drone["id"])
    position = drone["position"]
    if action == "TAKE_OFF":
        if value["target_id"] is not None or value["direction"] is not None:
            return None, "takeoff_has_extra_parameters"
        if float(position["z"]) > 0:
            return None, "drone_already_airborne"
        altitude = min(10.0, float(drone["max_altitude"]))
        if not math.isfinite(altitude) or altitude <= 0:
            return None, "invalid_altitude"
        return {"command": "take_off", "drone_id": drone_id, "altitude": altitude}, "resolved"
    if float(position["z"]) <= 0:
        return None, "drone_not_airborne"
    if action == "MOVE_TO_OBSERVED_TARGET":
        if value["direction"] is not None or not isinstance(value["target_id"], str):
            return None, "invalid_target_choice"
        target = next(
            (item for item in nearby_targets.get(drone_id, []) if item["id"] == value["target_id"]),
            None,
        )
        if target is None:
            return None, "target_not_locally_observed"
        x, y = (float(target["position"][axis]) for axis in ("x", "y"))
        source = "agent_local_target_observation"
    else:
        if value["target_id"] is not None or value["direction"] not in _DIRECTION:
            return None, "invalid_search_choice"
        dx, dy = _DIRECTION[value["direction"]]
        step = float(drone["perceived_radius"])
        if not math.isfinite(step) or step <= 0:
            return None, "invalid_search_step"
        x = float(position["x"]) + dx * step
        y = float(position["y"]) + dy * step
        source = "bounded_local_search"
    if not all(math.isfinite(v) for v in (x, y)) or not (0 <= x <= canvas[0] and 0 <= y <= canvas[1]):
        return None, "destination_out_of_bounds"
    if (x, y) in previous_destinations:
        return None, "repeated_destination"
    return {"command": "move_to", "drone_id": drone_id, "x": x, "y": y, "source": source}, "resolved"


class ModelActionSelector:
    def __init__(self, backend: ModelBackend) -> None:
        self.backend = backend
        self.trace: list[dict[str, Any]] = []

    def __call__(
        self,
        instruction: str,
        drones: list[dict[str, Any]],
        nearby_targets: Mapping[str, list[dict[str, Any]]],
        canvas: tuple[float, float],
        previous_destinations: set[tuple[float, float]],
    ) -> dict[str, Any] | None:
        request = build_request(
            instruction, drones, nearby_targets, canvas,
            previous_destinations, len(self.trace),
        )
        generation = self.backend.generate(request)
        if generation.generation_status != "GENERATED":
            action, resolution = None, "generation_not_completed"
        else:
            action, resolution = resolve_model_action(
                generation.raw_output, drones, nearby_targets, canvas, previous_destinations,
            )
        self.trace.append({
            "request": request.to_dict(),
            "generation": generation.to_dict(),
            "resolution": resolution,
        })
        return action


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--max-commands", type=int, default=4)
    parser.add_argument("--cache-audit", required=True, type=Path)
    parser.add_argument("--cache-dir", required=True, type=Path)
    parser.add_argument("--raw-output", required=True, type=Path)
    parser.add_argument("--summary-output", required=True, type=Path)
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args()
    if args.max_commands < 1 or args.max_commands > 12:
        raise ValueError("pilot command budget must be between 1 and 12")
    selected = {case["case_id"]: case for case in select_cases()}
    if args.case_id not in selected:
        raise ValueError("case must be a reviewed canonical training pilot case")
    case = selected[args.case_id]
    source = load_source_session(case["session_id"])
    audit = json.loads(args.cache_audit.read_text(encoding="utf-8"))
    if audit.get("model_id") != MODEL_ID or audit.get("revision") != MODEL_REVISION:
        raise ValueError("cache audit model identity differs from pilot")
    if Path(str(audit["cache_dir"])).resolve() != args.cache_dir.resolve():
        raise ValueError("cache directory differs from audited snapshot")
    verify_cached_snapshot(audit)
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip():
        raise ValueError("model pilot requires a clean, committed checkout")
    config = {
        "study": "train_only_closed_loop_model_pilot_v2_not_frozen_M1_to_M4",
        "code_commit": commit, "case_id": case["case_id"],
        "source_task_id": case["source_task_id"], "session_id": case["session_id"],
        "benchmark_sha256": EXPECTED_BENCHMARK_SHA256,
        "upstream_commit": EXPECTED_UPSTREAM_COMMIT,
        "model_id": MODEL_ID, "model_revision": MODEL_REVISION,
        "cache_audit_sha256": sha256(args.cache_audit),
        "max_commands": args.max_commands, "seed": SEED,
        "decoding": {"do_sample": False, "num_beams": 1, "max_new_tokens": 256},
    }
    summary = {
        "status": "preflight_only" if args.preflight_only else "running",
        "configuration": config, "model_loaded": False,
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    args.summary_output.parent.mkdir(parents=True, exist_ok=True)
    args.summary_output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.preflight_only:
        print(json.dumps({"status": "preflight_only", "case_id": case["case_id"]}))
        return
    selector: ModelActionSelector | None = None
    try:
        import torch  # noqa: PLC0415

        torch.manual_seed(SEED)
        backend = LocalQwenBackend.from_cached(QwenBackendConfig(
            model_id=MODEL_ID, revision=MODEL_REVISION, max_new_tokens=256,
            dtype="float16", cache_dir=str(args.cache_dir),
        ))
        selector = ModelActionSelector(backend)
        summary["model_loaded"] = True
        args.summary_output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
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
            run = run_case(client, headers, case, max_commands=args.max_commands, choose_action=selector)
        raw = {"configuration": config, "run": run, "model_calls": selector.trace}
        args.raw_output.parent.mkdir(parents=True, exist_ok=True)
        args.raw_output.write_text(json.dumps(raw, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        summary.update({
            "status": "complete_train_only_unscored",
            "model_call_count": len(selector.trace),
            "attempted_commands": len(run["commands"]),
            "successful_commands": sum(
                item["response"]["http_status"] == 200
                and item["response"]["body"].get("status") == "success"
                for item in run["commands"]
            ),
            "task_check_result": run["task_check"].get("result"),
            "stop_reason": run["stop_reason"],
            "last_model_action_resolution": selector.trace[-1]["resolution"] if selector.trace else None,
            "agent_privileged_data_http_status": run["agent_privileged_data_http_status"],
            "raw_sha256": sha256(args.raw_output),
            "completed_at_utc": datetime.now(timezone.utc).isoformat(),
        })
    except BaseException as error:
        summary.update({
            "status": "failed_preserved", "error_type": type(error).__name__,
            "error_message": str(error),
            "model_call_count": len(selector.trace) if selector else 0,
        })
        if selector and selector.trace:
            args.raw_output.parent.mkdir(parents=True, exist_ok=True)
            args.raw_output.write_text(
                json.dumps({"configuration": config, "model_calls": selector.trace}, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            summary["raw_sha256"] = sha256(args.raw_output)
        raise
    finally:
        args.summary_output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({key: summary[key] for key in (
        "status", "model_call_count", "attempted_commands", "task_check_result",
    )}, sort_keys=True))


if __name__ == "__main__":
    main()
