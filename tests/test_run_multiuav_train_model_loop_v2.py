"""Fail-closed action resolution for the reviewed-train model loop."""

from __future__ import annotations

import json
import unittest

from scripts.run_multiuav_train_model_loop_v2 import (
    ModelActionSelector,
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


def choice(action: str, *, drone_id: str | None = "drone-1",
           target_id: str | None = None, direction: str | None = None) -> str:
    return json.dumps({
        "action": action, "drone_id": drone_id,
        "target_id": target_id, "direction": direction,
    })


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
    def resolve(self, raw: str, *, targets: list[dict] | None = None) -> tuple[dict | None, str]:
        return resolve_model_action(
            raw, [DRONE], {"drone-1": targets if targets is not None else [TARGET]},
            (20, 20), set(),
        )

    def test_prompt_excludes_privileged_task_fields(self) -> None:
        request = build_request("Find Fixed Target 1", [DRONE], {"drone-1": [TARGET]},
                                (20, 20), set(), 0)
        payload = json.loads(request.messages[1].content)
        self.assertEqual(payload["nearby_targets_by_drone"]["drone-1"][0]["id"], "target-1")
        self.assertEqual(payload["allowed_actions_by_drone"]["drone-1"], [
            "MOVE_TO_OBSERVED_TARGET", "SEARCH", "STOP",
        ])
        for forbidden in ("related_apis", "commands", "execution_check_apis", "official_plan"):
            self.assertNotIn(forbidden, request.messages[1].content)

    def test_grounded_drone_prompt_requires_takeoff(self) -> None:
        grounded = {**DRONE, "position": {"x": 10, "y": 10, "z": 0}}
        request = build_request("Search", [grounded], {"drone-1": []},
                                (20, 20), set(), 0)
        payload = json.loads(request.messages[1].content)
        self.assertEqual(payload["allowed_actions_by_drone"]["drone-1"], [
            "TAKE_OFF", "STOP",
        ])

    def test_observed_target_resolves_to_server_coordinate(self) -> None:
        action, status = self.resolve(choice("MOVE_TO_OBSERVED_TARGET", target_id="target-1"))
        self.assertEqual(status, "resolved")
        self.assertEqual((action["x"], action["y"]), (12, 11))

    def test_unobserved_target_and_raw_coordinates_fail(self) -> None:
        action, status = self.resolve(choice("MOVE_TO_OBSERVED_TARGET", target_id="hidden"))
        self.assertIsNone(action)
        self.assertEqual(status, "target_not_locally_observed")
        action, status = self.resolve('{"action":"SEARCH","drone_id":"drone-1",'
                                      '"target_id":null,"direction":"EAST","x":99}')
        self.assertIsNone(action)
        self.assertEqual(status, "action_schema_mismatch")

    def test_duplicate_json_key_fails_closed(self) -> None:
        raw = '{"action":"STOP","action":"SEARCH","drone_id":"drone-1",' \
              '"target_id":null,"direction":"EAST"}'
        action, status = self.resolve(raw)
        self.assertIsNone(action)
        self.assertEqual(status, "invalid_json")

    def test_search_uses_bounded_radius_and_rejects_outside_canvas(self) -> None:
        action, status = self.resolve(choice("SEARCH", direction="EAST"), targets=[])
        self.assertEqual(status, "resolved")
        self.assertEqual((action["x"], action["y"]), (15, 10))
        edge = {**DRONE, "position": {"x": 19, "y": 10, "z": 10}}
        action, status = resolve_model_action(
            choice("SEARCH", direction="EAST"), [edge], {"drone-1": []}, (20, 20), set()
        )
        self.assertIsNone(action)
        self.assertEqual(status, "destination_out_of_bounds")

    def test_takeoff_rejects_airborne_drone(self) -> None:
        action, status = self.resolve(choice("TAKE_OFF"))
        self.assertIsNone(action)
        self.assertEqual(status, "drone_already_airborne")

    def test_model_failure_is_preserved_without_action(self) -> None:
        backend = FakeBackend("not json")
        selector = ModelActionSelector(backend)
        action = selector("Find", [DRONE], {"drone-1": []}, (20, 20), set())
        self.assertIsNone(action)
        self.assertEqual(selector.trace[0]["resolution"], "invalid_json")
        self.assertEqual(selector.trace[0]["generation"]["raw_output"], "not json")

    def test_fake_model_drives_reobservation_then_stops(self) -> None:
        backend = SequenceBackend([
            choice("TAKE_OFF"),
            choice("SEARCH", direction="EAST"),
            choice("STOP", drone_id=None),
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

    def test_explicit_takeoff_prelude_uses_no_model_call(self) -> None:
        backend = SequenceBackend([choice("SEARCH", direction="EAST")])
        selector = ModelActionSelector(backend)
        grounded = {**DRONE, "position": {"x": 10, "y": 10, "z": 0}}
        first = selector("Take off and search", [grounded], {"drone-1": []},
                         (20, 20), set())
        self.assertEqual(first["command"], "take_off")
        self.assertEqual(backend.calls, 0)
        self.assertEqual(len(selector.deterministic_prelude), 1)
        second = selector(
            "Take off and search", [DRONE], {"drone-1": []}, (20, 20), set(),
        )
        self.assertEqual(second["command"], "move_to")
        self.assertEqual(backend.calls, 1)


if __name__ == "__main__":
    unittest.main()
