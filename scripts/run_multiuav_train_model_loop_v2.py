"""Run a bounded, model-driven AGENT loop on one reviewed training task."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
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
from scripts.probe_multiuav_train_closed_loop_v2 import MAX_PILOT_COMMANDS, run_case  # noqa: E402
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

ACTION_SCHEMA = {"fields": ["option_id"], "stop_option_id": "STOP"}
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


def available_actions(
    drones: list[dict[str, Any]],
    nearby_targets: Mapping[str, list[dict[str, Any]]],
    canvas: tuple[float, float],
    previous_destinations: set[tuple[float, float]],
    instruction: str | None = None,
    search_counts: Mapping[str, int] | None = None,
) -> list[dict[str, Any]]:
    """Construct bounded commands only from the current AGENT observation."""

    width, height = canvas
    if not all(math.isfinite(v) and v > 0 for v in (width, height)):
        return []
    named_target_ids = {
        str(target["id"])
        for targets in nearby_targets.values()
        for target in targets
        if instruction and str(target["name"]).casefold() in instruction.casefold()
    }
    focused_drones = {
        drone_id for drone_id, targets in nearby_targets.items()
        if any(str(target["id"]) in named_target_ids for target in targets)
    }
    choices: list[dict[str, Any]] = []
    for drone in sorted(drones, key=lambda item: str(item["id"])):
        drone_id = str(drone["id"])
        if focused_drones and drone_id not in focused_drones:
            continue
        position = drone["position"]
        altitude = float(position["z"])
        if not math.isfinite(altitude):
            continue
        status = str(drone.get("status", "")).casefold()
        if status in {"idle", "ready"}:
            takeoff_altitude = min(10.0, float(drone["max_altitude"]))
            if math.isfinite(takeoff_altitude) and takeoff_altitude > 0:
                choices.append({
                    "description": f"Take off {drone['name']}",
                    "action": {
                        "command": "take_off", "drone_id": drone_id,
                        "altitude": takeoff_altitude,
                    },
                })
            continue
        if status not in {"hovering", "flying", "moving"}:
            continue
        for target in sorted(nearby_targets.get(drone_id, []), key=lambda item: str(item["id"])):
            if focused_drones and str(target["id"]) not in named_target_ids:
                continue
            sweep = (_circle_sweep_action(drone, target, canvas, previous_destinations)
                     or _rectangle_sweep_action(drone, target, canvas, previous_destinations))
            if sweep is not None:
                choices.append({
                    "description": f"Sweep observed {target['name']} area with {drone['name']}",
                    "action": sweep,
                })
            x, y = (float(target["position"][axis]) for axis in ("x", "y"))
            if (math.isfinite(x) and math.isfinite(y)
                    and 0 <= x <= width and 0 <= y <= height
                    and (x, y) not in previous_destinations):
                choices.append({
                    "description": f"Move {drone['name']} to observed {target['name']}",
                    "action": {
                        "command": "move_to", "drone_id": drone_id,
                        "x": x, "y": y, "source": "agent_local_target_observation",
                    },
                })
        if focused_drones:
            continue
        radius = float(drone["perceived_radius"])
        if not math.isfinite(radius) or radius <= 0:
            continue
        x0, y0 = (float(position[axis]) for axis in ("x", "y"))
        if not all(math.isfinite(v) for v in (x0, y0)):
            continue
        for direction, (dx, dy) in _DIRECTION.items():
            x, y = x0 + dx * radius, y0 + dy * radius
            if 0 <= x <= width and 0 <= y <= height and (x, y) not in previous_destinations:
                choices.append({
                    "description": f"Search {direction.lower()} with {drone['name']}",
                    "action": {
                        "command": "move_to", "drone_id": drone_id,
                        "x": x, "y": y, "source": "bounded_local_search",
                    },
                })
    if not choices and focused_drones:
        return available_actions(drones, nearby_targets, canvas,
                                 previous_destinations, search_counts=search_counts)
    if not focused_drones and search_counts is not None:
        search_choices = [
            choice for choice in choices
            if choice["action"].get("source") == "bounded_local_search"
        ]
        if search_choices:
            fewest = min(search_counts.get(choice["action"]["drone_id"], 0)
                         for choice in search_choices)
            choices = [
                choice for choice in choices
                if choice["action"].get("source") != "bounded_local_search"
                or search_counts.get(choice["action"]["drone_id"], 0) == fewest
            ]
    for index, choice in enumerate(choices, start=1):
        choice["option_id"] = f"O{index}"
    return choices


def _circle_sweep_action(
    drone: Mapping[str, Any], target: Mapping[str, Any],
    canvas: tuple[float, float], previous_destinations: set[tuple[float, float]],
) -> dict[str, Any] | None:
    if target.get("type") != "circle":
        return None
    try:
        cx = float(target["position"]["x"])
        cy = float(target["position"]["y"])
        radius = float(target["radius"])
        task_radius = float(drone["task_radius"])
    except (KeyError, TypeError, ValueError):
        return None
    width, height = canvas
    if (not all(math.isfinite(value) for value in (cx, cy, radius, task_radius))
            or radius <= 0 or task_radius <= 0
            or cx - radius < 0 or cx + radius > width
            or cy - radius < 0 or cy + radius > height):
        return None
    margin = min(task_radius, radius)
    low, high = -radius + margin, radius - margin
    rows = max(1, math.ceil((high - low) / (2 * task_radius)) + 1)
    if rows > 12:
        return None
    offsets = [0.0] if rows == 1 else [
        low + (high - low) * index / (rows - 1) for index in range(rows)
    ]
    waypoints = [
        {"x": cx + side * radius, "y": cy + offset}
        for index, offset in enumerate(offsets)
        for side in ((-1, 1) if index % 2 == 0 else (1, -1))
    ]
    next_waypoint = next(
        (point for point in waypoints
         if (point["x"], point["y"]) not in previous_destinations),
        None,
    )
    if next_waypoint is None:
        return None
    return {
        "command": "move_to", "drone_id": str(drone["id"]),
        "x": next_waypoint["x"], "y": next_waypoint["y"],
        "source": "agent_visible_circle_geometry_step",
    }


def _rectangle_sweep_action(
    drone: Mapping[str, Any], target: Mapping[str, Any],
    canvas: tuple[float, float], previous_destinations: set[tuple[float, float]],
) -> dict[str, Any] | None:
    if target.get("type") != "polygon":
        return None
    try:
        vertices = [(float(point["x"]), float(point["y"]))
                    for point in target["vertices"]]
        task_radius = float(drone["task_radius"])
    except (KeyError, TypeError, ValueError):
        return None
    if len(vertices) != 4 or not math.isfinite(task_radius) or task_radius <= 0:
        return None
    xs, ys = sorted({point[0] for point in vertices}), sorted({point[1] for point in vertices})
    if (len(xs) != 2 or len(ys) != 2
            or not all(math.isfinite(value) for point in vertices for value in point)
            or set(vertices) != {(x, y) for x in xs for y in ys}
            or xs[0] < 0 or ys[0] < 0 or xs[1] > canvas[0] or ys[1] > canvas[1]):
        return None
    margin_x = min(task_radius, (xs[1] - xs[0]) / 2)
    margin_y = min(task_radius, (ys[1] - ys[0]) / 2)
    left, right = xs[0] + margin_x, xs[1] - margin_x
    low, high = ys[0] + margin_y, ys[1] - margin_y
    rows = max(1, math.ceil((high - low) / (2 * task_radius)) + 1)
    if rows > 12:
        return None
    offsets = [low] if rows == 1 else [
        low + (high - low) * index / (rows - 1) for index in range(rows)
    ]
    waypoints = [
        (x, y)
        for index, y in enumerate(offsets)
        for x in ((left, right) if index % 2 == 0 else (right, left))
    ]
    next_waypoint = next(
        ((x, y) for x, y in waypoints if (x, y) not in previous_destinations),
        None,
    )
    if next_waypoint is None:
        return None
    return {
        "command": "move_to", "drone_id": str(drone["id"]),
        "x": next_waypoint[0], "y": next_waypoint[1],
        "source": "agent_visible_rectangle_geometry_step",
    }


def build_request(
    instruction: str,
    drones: list[dict[str, Any]],
    nearby_targets: Mapping[str, list[dict[str, Any]]],
    canvas: tuple[float, float],
    previous_destinations: set[tuple[float, float]],
    call_index: int,
    choices: list[dict[str, Any]] | None = None,
) -> PromptRequest:
    """Expose current AGENT observations and admissible one-step options."""

    if choices is None:
        choices = available_actions(drones, nearby_targets, canvas, previous_destinations,
                                    instruction)

    visible = {
        "instruction": instruction,
        "canvas": {"width": canvas[0], "height": canvas[1]},
        "drones": [
            {
                key: drone[key]
                for key in ("id", "name", "status", "position", "max_altitude", "perceived_radius", "task_radius")
                if key in drone
            }
            for drone in drones
        ],
        "nearby_targets_by_drone": {
            drone_id: [
                {key: target[key] for key in ("id", "name", "position", "type", "radius", "vertices")
                 if key in target}
                for target in targets
            ]
            for drone_id, targets in nearby_targets.items()
        },
        "previous_destinations": [list(point) for point in sorted(previous_destinations)],
        "options": [
            {"option_id": choice["option_id"], "description": choice["description"]}
            for choice in choices
        ],
        "stop_option_id": "STOP",
    }
    messages = (
        PromptMessage(
            role="system",
            content=(
                "You control one bounded step of a training-only simulated UAV task. "
                "Return exactly one JSON object with one key, option_id. Choose one "
                "option_id from options, or STOP if the mission instruction itself is "
                "insufficient, contradictory, or no listed step can responsibly help. "
                "A target absent from nearby_targets_by_drone may be found by a listed "
                "bounded search step; absence from this local observation alone is not "
                "a reason to STOP. For area coverage, prefer an offered observed-area "
                "sweep step to a target-center move. Never invent an option ID or coordinates."
            ),
        ),
        PromptMessage(role="user", content=_canonical(visible)),
    )
    payload = [message.to_dict() for message in messages]
    return PromptRequest(
        prompt_contract_version="train_closed_loop_option_menu_v10",
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
    choices: list[dict[str, Any]],
) -> tuple[dict[str, Any] | None, str]:
    """Fail closed unless the selected ID is in the freshly constructed menu."""

    try:
        value = json.loads(raw, object_pairs_hook=_unique_pairs)
    except (ValueError, TypeError):
        return None, "invalid_json"
    if not isinstance(value, dict) or set(value) != set(ACTION_SCHEMA["fields"]):
        return None, "action_schema_mismatch"
    option_id = value["option_id"]
    if option_id == "STOP":
        return None, "model_stop"
    choice = next((item for item in choices if item["option_id"] == option_id), None)
    if choice is None:
        return None, "unknown_option"
    return dict(choice["action"]), "resolved"


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
        search_counts: dict[str, int] = {}
        for item in self.trace:
            selected = item.get("selected_action")
            if selected is not None and selected.get("source") == "bounded_local_search":
                drone_id = str(selected["drone_id"])
                search_counts[drone_id] = search_counts.get(drone_id, 0) + 1
        choices = available_actions(drones, nearby_targets, canvas, previous_destinations,
                                    instruction, search_counts)
        if not choices:
            return None
        request = build_request(
            instruction, drones, nearby_targets, canvas,
            previous_destinations, len(self.trace), choices,
        )
        generation = self.backend.generate(request)
        if generation.generation_status != "GENERATED":
            action, resolution = None, "generation_not_completed"
        else:
            action, resolution = resolve_model_action(
                generation.raw_output, choices,
            )
        self.trace.append({
            "request": request.to_dict(),
            "generation": generation.to_dict(),
            "offered_actions": choices,
            "resolution": resolution,
            "selected_action": action,
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
    if args.max_commands < 1 or args.max_commands > MAX_PILOT_COMMANDS:
        raise ValueError(f"pilot command budget must be between 1 and {MAX_PILOT_COMMANDS}")
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
        "policy": "agent_visible_option_menu_v10_status_checked_balanced_search",
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
    journal_path = args.raw_output.with_suffix(".commands.jsonl")
    event_path = args.raw_output.with_suffix(".events.jsonl")
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
        if journal_path.exists() or event_path.exists():
            raise ValueError("attempt journal already exists; use a new attempt directory")
        journal_path.parent.mkdir(parents=True, exist_ok=True)

        def journal(record: dict[str, Any]) -> None:
            with journal_path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(record, sort_keys=True) + "\n")
                stream.flush()
                os.fsync(stream.fileno())

        def event(record: dict[str, Any]) -> None:
            record = {**record, "at_utc": datetime.now(timezone.utc).isoformat()}
            with event_path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(record, sort_keys=True) + "\n")
                stream.flush()
                os.fsync(stream.fileno())

        with TestClient(app) as client:
            setup = session_payload(source, case["source_task_id"])
            setup["id"] = source["id"]
            restored = session_controller.create_session_from_dict(setup)
            session_controller.sessions[restored.id] = restored
            if session_controller.set_current_session(restored.id) is None:
                raise RuntimeError("official session controller did not activate training session")
            run = run_case(
                client, headers, case, max_commands=args.max_commands,
                choose_action=selector, on_command=journal, on_event=event,
            )
        raw = {
            "configuration": config, "run": run,
            "model_calls": selector.trace,
        }
        args.raw_output.parent.mkdir(parents=True, exist_ok=True)
        args.raw_output.write_text(json.dumps(raw, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        summary.update({
            "status": "complete_train_only_unscored",
            "model_call_count": len(selector.trace),
            "deterministic_prelude_action_count": 0,
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
        if journal_path.exists():
            summary["command_journal_sha256"] = sha256(journal_path)
        if event_path.exists():
            summary["event_journal_sha256"] = sha256(event_path)
    except BaseException as error:
        summary.update({
            "status": "failed_preserved", "error_type": type(error).__name__,
            "error_message": str(error),
            "model_call_count": len(selector.trace) if selector else 0,
        })
        if selector and selector.trace:
            args.raw_output.parent.mkdir(parents=True, exist_ok=True)
            args.raw_output.write_text(
                json.dumps({
                    "configuration": config,
                    "model_calls": selector.trace,
                }, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            summary["raw_sha256"] = sha256(args.raw_output)
        if journal_path.exists():
            summary["command_journal_sha256"] = sha256(journal_path)
        if event_path.exists():
            summary["event_journal_sha256"] = sha256(event_path)
        raise
    finally:
        args.summary_output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({key: summary[key] for key in (
        "status", "model_call_count", "attempted_commands", "task_check_result",
    )}, sort_keys=True))


if __name__ == "__main__":
    main()
