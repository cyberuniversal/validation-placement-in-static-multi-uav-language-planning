"""Safety checks for the exploratory follow-up candidate."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from shepherd_ai.multiuav_context import project_agent_visible_context  # noqa: E402
from shepherd_ai.multiuav_candidate_v2 import (  # noqa: E402
    evaluate_candidate,
    screen_visible_request,
)
from shepherd_ai.multiuav_plan_contract import parse_strict_model_output  # noqa: E402


def _context(instruction: str) -> dict:
    return project_agent_visible_context(
        {
            "id": "session-1",
            "task_type": "area_search",
            "canvas_width": 100,
            "canvas_height": 80,
            "is_distance_3d": True,
            "status": "active",
            "drones": [{
                "id": "drone-1", "name": "Drone 1", "status": "idle",
                "position": {"x": 5, "y": 6, "z": 0}, "heading": 0,
                "max_altitude": 50,
                "home_position": {"x": 5, "y": 6, "z": 0},
            }],
            "environment": {"id": "environment-1", "name": "Clear", "weather": "clear"},
        },
        task_id="task-1",
        instruction=instruction,
    )


def _output(endpoint: str = "/drones/drone-1/command/take_off"):
    parsed = parse_strict_model_output(json.dumps({
        "decision": "EXECUTE", "reason": "Ready.",
        "clarification_question": None,
        "api_plan": [{"endpoint": endpoint, "parameters": {"altitude": 20}}],
    })).parsed
    if parsed is None:
        raise AssertionError("test output did not parse")
    return parsed


class CandidateTests(unittest.TestCase):
    def test_grounded_concrete_endpoint_can_release(self) -> None:
        report = evaluate_candidate(
            _output(), _context("Have Drone 1 take off to 20 meters."),
        )
        self.assertEqual(report.reason_code, "grounded_plan")
        self.assertTrue(report.release_authorized)
        self.assertEqual(report.resolved_calls, 1)

    def test_unresolved_assignment_requests_clarification(self) -> None:
        context = _context("Have assigned UAV A take off to 20 meters.")
        report = evaluate_candidate(_output(), context)
        self.assertEqual((report.decision, report.reason_code),
                         ("CLARIFY", "unresolved_assigned_uav"))
        self.assertFalse(report.release_authorized)
        self.assertEqual(
            screen_visible_request(_context(
                "Have assigned UAV A (Drone 1) take off to 20 meters."
            ))[0], "EXECUTE",
        )

    def test_unresolved_threshold_requests_clarification(self) -> None:
        self.assertEqual(
            screen_visible_request(_context(
                "Continue until progress exceeds the required threshold."
            ))[0], "CLARIFY",
        )
        self.assertEqual(
            screen_visible_request(_context(
                "Continue until progress exceeds the required threshold (50%)."
            ))[0], "EXECUTE",
        )

    def test_missing_required_drone_blocks(self) -> None:
        context = _context("Have Drone 2 take off to 20 meters.")
        report = evaluate_candidate(_output(), context)
        self.assertEqual((report.decision, report.reason_code),
                         ("BLOCK", "visible_fleet_conflict"))
        self.assertFalse(report.release_authorized)

    def test_no_fleet_blocks_generic_request(self) -> None:
        context = deepcopy(_context("Take off to 20 meters."))
        context["drones"] = []
        self.assertEqual(screen_visible_request(context)[0], "BLOCK")

    def test_requested_fleet_cardinality_must_be_visible(self) -> None:
        context = _context("Send two drones north.")
        self.assertEqual(screen_visible_request(context),
                         ("BLOCK", "visible_fleet_conflict"))

    def test_postplan_validation_remains_mandatory(self) -> None:
        report = evaluate_candidate(
            _output("/drones/drone-1/command/teleport"),
            _context("Have Drone 1 take off to 20 meters."),
        )
        self.assertEqual(report.reason_code, "postplan_rejected")
        self.assertFalse(report.release_authorized)


if __name__ == "__main__":
    unittest.main()
