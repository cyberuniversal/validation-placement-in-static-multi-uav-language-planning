"""Fail-closed action resolution for the reviewed-train model loop."""

from __future__ import annotations

import json
import unittest

from scripts.run_multiuav_train_model_loop_v2 import (
    ModelActionSelector,
    available_actions,
    build_request,
    resolve_model_action,
)
from shepherd_ai.multiuav_runner import GenerationResult
from scripts.probe_multiuav_train_closed_loop_v2 import run_case


DRONE = {
    "id": "drone-1", "name": "Drone 1", "status": "hovering",
    "position": {"x": 10, "y": 10, "z": 10},
    "max_altitude": 20, "perceived_radius": 5,
}
TARGET = {"id": "target-1", "name": "Fixed Target 1", "position": {"x": 12, "y": 11}}


def choice(option_id: str) -> str:
    return json.dumps({"option_id": option_id})


class FakeBackend:
    def __init__(self, raw: str) -> None:
        self.raw = raw
        self.calls = 0

    def generate(self, request: object) -> GenerationResult:
        self.calls += 1
        return GenerationResult(raw_output=self.raw)


class SequenceBackend:
    def __init__(self, outputs: list[str]) -> None:
        self.outputs = outputs
        self.calls = 0

    def generate(self, request: object) -> GenerationResult:
        raw = self.outputs[self.calls]
        self.calls += 1
        return GenerationResult(raw_output=raw)


class FakeResponse:
    def __init__(self, status_code: int, body: object) -> None:
        self.status_code = status_code
        self.body = body

    def json(self) -> object:
        return self.body


class FakeClient:
    def __init__(self) -> None:
        self.drone = {**DRONE, "position": {"x": 10, "y": 10, "z": 0}}

    def get(self, path: str, *, headers: dict[str, str]) -> FakeResponse:
        if path == "/sessions/current/data":
            return FakeResponse(403, {})
        if path == "/drones":
            return FakeResponse(200, [self.drone])
        if path.endswith("/nearby/targets"):
            return FakeResponse(200, [])
        if path == "/sessions/current/task-progress":
            return FakeResponse(200, {"progress_percentage": 0})
        if path == "/sessions/current/tasks/task-1/check":
            return FakeResponse(200, {"result": False})
        raise AssertionError(f"unexpected GET {path}")

    def post(self, path: str, *, params: dict[str, float], headers: dict[str, str]) -> FakeResponse:
        if path.endswith("/take_off"):
            self.drone["position"]["z"] = params["altitude"]
        elif path.endswith("/move_to"):
            self.drone["position"]["x"] = params["x"]
            self.drone["position"]["y"] = params["y"]
        else:
            raise AssertionError(f"unexpected POST {path}")
        return FakeResponse(200, {"status": "success"})


class ModelLoopTests(unittest.TestCase):
    def menu(self, *, drone: dict | None = None,
             targets: list[dict] | None = None) -> list[dict]:
        return available_actions(
            [drone or DRONE], {"drone-1": targets if targets is not None else [TARGET]},
            (20, 20), set(),
        )

    def test_prompt_excludes_privileged_task_fields(self) -> None:
        request = build_request("Find Fixed Target 1", [DRONE], {"drone-1": [TARGET]},
                                (20, 20), set(), 0)
        payload = json.loads(request.messages[1].content)
        self.assertEqual(payload["nearby_targets_by_drone"]["drone-1"][0]["id"], "target-1")
        self.assertEqual(payload["options"][0]["description"],
                         "Move Drone 1 to observed Fixed Target 1")
        self.assertEqual(payload["stop_option_id"], "STOP")
        self.assertNotIn("action", payload["options"][0])
        for forbidden in ("related_apis", "commands", "execution_check_apis", "official_plan"):
            self.assertNotIn(forbidden, request.messages[1].content)

    def test_grounded_drone_prompt_requires_takeoff(self) -> None:
        grounded = {**DRONE, "position": {"x": 10, "y": 10, "z": 0}}
        request = build_request("Search", [grounded], {"drone-1": []},
                                (20, 20), set(), 0)
        payload = json.loads(request.messages[1].content)
        self.assertEqual(len(payload["options"]), 1)
        self.assertEqual(payload["options"][0]["description"], "Take off Drone 1")

    def test_observed_target_resolves_to_server_coordinate(self) -> None:
        action, status = resolve_model_action(choice("O1"), self.menu())
        self.assertEqual(status, "resolved")
        self.assertEqual((action["x"], action["y"]), (12, 11))

    def test_unoffered_option_and_raw_coordinates_fail(self) -> None:
        action, status = resolve_model_action(choice("O999"), self.menu())
        self.assertIsNone(action)
        self.assertEqual(status, "unknown_option")
        action, status = resolve_model_action('{"option_id":"O1","x":99}', self.menu())
        self.assertIsNone(action)
        self.assertEqual(status, "action_schema_mismatch")

    def test_duplicate_json_key_fails_closed(self) -> None:
        raw = '{"option_id":"STOP","option_id":"O1"}'
        action, status = resolve_model_action(raw, self.menu())
        self.assertIsNone(action)
        self.assertEqual(status, "invalid_json")

    def test_search_uses_bounded_radius_and_omits_outside_canvas(self) -> None:
        menu = self.menu(targets=[])
        east = next(item for item in menu if "east" in item["description"])
        action, status = resolve_model_action(choice(east["option_id"]), menu)
        self.assertEqual(status, "resolved")
        self.assertEqual((action["x"], action["y"]), (15, 10))
        edge = {**DRONE, "position": {"x": 19, "y": 10, "z": 10}}
        self.assertFalse(any(
            "east" in item["description"] for item in self.menu(drone=edge, targets=[])
        ))

    def test_takeoff_only_offered_when_grounded(self) -> None:
        self.assertFalse(any(item["action"]["command"] == "take_off" for item in self.menu()))
        grounded = {**DRONE, "position": {"x": 10, "y": 10, "z": 0}}
        self.assertEqual(self.menu(drone=grounded)[0]["action"]["command"], "take_off")

    def test_previous_destination_removes_target_and_search_option(self) -> None:
        menu = available_actions([DRONE], {"drone-1": [TARGET]},
                                 (20, 20), {(12, 11), (15, 10)})
        self.assertFalse(any("Fixed Target 1" in item["description"] for item in menu))
        self.assertFalse(any("east" in item["description"] for item in menu))

    def test_model_failure_is_preserved_without_action(self) -> None:
        backend = FakeBackend("not json")
        selector = ModelActionSelector(backend)
        action = selector("Find", [DRONE], {"drone-1": []}, (20, 20), set())
        self.assertIsNone(action)
        self.assertEqual(selector.trace[0]["resolution"], "invalid_json")
        self.assertEqual(selector.trace[0]["generation"]["raw_output"], "not json")

    def test_fake_model_drives_reobservation_then_stops(self) -> None:
        backend = SequenceBackend([
            choice("O1"),
            choice("O2"),
            choice("STOP"),
        ])
        selector = ModelActionSelector(backend)
        case = {
            "source_task_id": "task-1",
            "context": {
                "instruction": "Find Fixed Target 1",
                "session": {"canvas_width": 20, "canvas_height": 20},
            },
        }
        result = run_case(
            FakeClient(), {"X-API-Key": "agent"}, case,
            max_commands=3, choose_action=selector,
        )
        self.assertEqual([item["action"]["command"] for item in result["commands"]], [
            "take_off", "move_to",
        ])
        self.assertEqual(backend.calls, 3)
        self.assertEqual(selector.trace[-1]["resolution"], "model_stop")
        self.assertEqual(result["stop_reason"], "no_bounded_action")

    def test_explicit_takeoff_is_model_selected(self) -> None:
        backend = SequenceBackend([choice("O1")])
        selector = ModelActionSelector(backend)
        grounded = {**DRONE, "position": {"x": 10, "y": 10, "z": 0}}
        first = selector("Take off and search", [grounded], {"drone-1": []},
                         (20, 20), set())
        self.assertEqual(first["command"], "take_off")
        self.assertEqual(backend.calls, 1)

    def test_stop_never_issues_command(self) -> None:
        action, status = resolve_model_action(choice("STOP"), self.menu())
        self.assertIsNone(action)
        self.assertEqual(status, "model_stop")


if __name__ == "__main__":
    unittest.main()
