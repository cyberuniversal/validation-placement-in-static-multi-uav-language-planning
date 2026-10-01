"""Guards for the bounded, train-only AGENT command loop."""

from __future__ import annotations

import unittest

from scripts.probe_multiuav_train_closed_loop_v2 import (
    issue_action,
    run_case,
    select_action,
)


DRONE = {
    "id": "drone-1", "name": "Drone 1", "position": {"x": 10, "y": 10, "z": 0},
    "max_altitude": 20, "perceived_radius": 5,
}


class FakeResponse:
    def __init__(self, status_code: int, body: object) -> None:
        self.status_code = status_code
        self.body = body

    def json(self) -> object:
        return self.body


class FakeClient:
    def __init__(self, *, privileged_status: int = 403) -> None:
        self.privileged_status = privileged_status
        self.drone = {**DRONE, "position": dict(DRONE["position"])}
        self.paths: list[str] = []

    def get(self, path: str, *, headers: dict[str, str]) -> FakeResponse:
        self.paths.append(path)
        if path == "/sessions/current/data":
            return FakeResponse(self.privileged_status, {})
        if path == "/drones":
            return FakeResponse(200, [self.drone])
        if path.endswith("/nearby/targets"):
            targets = [{"id": "target", "name": "Fixed Target 1", "position": {"x": 15, "y": 10}}]
            return FakeResponse(200, targets if self.drone["position"]["x"] >= 15 else [])
        if path == "/sessions/current/task-progress":
            return FakeResponse(200, {"progress_percentage": 0})
        if path == "/sessions/current/tasks/task-1/check":
            return FakeResponse(200, {"result": False})
        raise AssertionError(f"unexpected GET {path}")

    def post(self, path: str, *, params: dict[str, float], headers: dict[str, str]) -> FakeResponse:
        self.paths.append(path)
        if path.endswith("/take_off"):
            self.drone["position"]["z"] = params["altitude"]
        elif path.endswith("/move_to"):
            self.drone["position"]["x"] = params["x"]
            self.drone["position"]["y"] = params["y"]
        else:
            raise AssertionError(f"unexpected POST {path}")
        return FakeResponse(200, {"status": "success"})


class ClosedLoopProbeTests(unittest.TestCase):
    def test_takeoff_precedes_search(self) -> None:
        action = select_action("Find Fixed Target 1", [DRONE], {"drone-1": []}, (20, 20), set())
        self.assertEqual(action["command"], "take_off")

    def test_search_uses_visible_bounds_not_hidden_target(self) -> None:
        flying = {**DRONE, "position": {"x": 10, "y": 10, "z": 10}}
        action = select_action("Find Fixed Target 1", [flying], {"drone-1": []}, (20, 20), set())
        self.assertEqual((action["x"], action["y"]), (15, 10))
        self.assertEqual(action["source"], "bounded_local_search")

    def test_named_visible_target_is_used_only_after_observation(self) -> None:
        flying = {**DRONE, "position": {"x": 10, "y": 10, "z": 10}}
        target = {"id": "target", "name": "Fixed Target 1", "position": {"x": 12, "y": 11}}
        action = select_action(
            "Find Fixed Target 1", [flying], {"drone-1": [target]}, (20, 20), set()
        )
        self.assertEqual((action["x"], action["y"]), (12, 11))
        self.assertEqual(action["source"], "agent_local_target_observation")

    def test_relevant_observation_selects_its_drone(self) -> None:
        flying = {**DRONE, "position": {"x": 10, "y": 10, "z": 10}}
        second = {**flying, "id": "drone-2"}
        target = {"id": "target", "name": "Fixed Target 1", "position": {"x": 12, "y": 11}}
        action = select_action(
            "Find Fixed Target 1", [flying, second],
            {"drone-1": [], "drone-2": [target]}, (20, 20), set(),
        )
        self.assertEqual(action["drone_id"], "drone-2")
        self.assertEqual(action["source"], "agent_local_target_observation")

    def test_loop_reobserves_after_each_command(self) -> None:
        client = FakeClient()
        journal: list[dict] = []
        case = {
            "source_task_id": "task-1",
            "context": {
                "instruction": "Find Fixed Target 1",
                "session": {"canvas_width": 20, "canvas_height": 20},
            },
        }
        result = run_case(
            client, {"X-API-Key": "agent"}, case,
            max_commands=2, on_command=journal.append,
        )
        self.assertEqual(len(result["snapshots"]), 3)
        self.assertEqual([item["action"]["command"] for item in result["commands"]], [
            "take_off", "move_to",
        ])
        self.assertEqual(len(result["snapshots"][-1]["nearby_targets_by_drone"]["drone-1"]), 1)
        self.assertEqual(result["agent_privileged_data_http_status"], 403)
        self.assertEqual(result["task_check"]["result"], False)
        self.assertEqual(journal, result["commands"])

    def test_privileged_access_fails_closed(self) -> None:
        case = {
            "source_task_id": "task-1",
            "context": {"instruction": "Find", "session": {"canvas_width": 20, "canvas_height": 20}},
        }
        with self.assertRaisesRegex(RuntimeError, "privileged"):
            run_case(FakeClient(privileged_status=200), {"X-API-Key": "agent"}, case, max_commands=1)

    def test_command_budget_and_unknown_command_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "budget"):
            run_case(FakeClient(), {"X-API-Key": "agent"}, {}, max_commands=13)
        with self.assertRaisesRegex(ValueError, "unsupported"):
            issue_action(FakeClient(), {"X-API-Key": "agent"}, {
                "command": "delete", "drone_id": "drone-1",
            })


if __name__ == "__main__":
    unittest.main()
