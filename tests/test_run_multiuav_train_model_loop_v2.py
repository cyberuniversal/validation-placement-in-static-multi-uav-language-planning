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
        for forbidden in ("related_apis", "commands", "execution_check_apis", "official_plan"):
            self.assertNotIn(forbidden, request.messages[1].content)

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


if __name__ == "__main__":
    unittest.main()
