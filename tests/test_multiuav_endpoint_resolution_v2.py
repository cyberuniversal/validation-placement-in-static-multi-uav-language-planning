"""Safety boundaries for the post-hoc concrete endpoint resolver."""

from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from shepherd_ai.multiuav_context import project_agent_visible_context  # noqa: E402
from shepherd_ai.multiuav_endpoint_resolution_v2 import (  # noqa: E402
    resolve_concrete_endpoints,
)
from shepherd_ai.multiuav_grounding_validator import (  # noqa: E402
    ACCEPTED_STAGE,
    ENDPOINT_SCHEMA_STAGE,
    validate_grounded_plan,
)
from shepherd_ai.multiuav_plan_contract import parse_strict_model_output  # noqa: E402


def _context() -> dict:
    return project_agent_visible_context(
        {
            "id": "session-1",
            "task_type": "area_search",
            "canvas_width": 100,
            "canvas_height": 80,
            "is_distance_3d": True,
            "status": "active",
            "drones": [
                {
                    "id": "drone-1",
                    "name": "Drone 1",
                    "status": "idle",
                    "position": {"x": 5, "y": 6, "z": 0},
                    "heading": 0,
                    "max_altitude": 50,
                    "home_position": {"x": 5, "y": 6, "z": 0},
                }
            ],
            "environment": {
                "id": "environment-1",
                "name": "Clear",
                "weather": "clear",
            },
        },
        task_id="task-1",
        instruction="Have Drone 1 take off to 20 meters.",
    )


def _output(endpoint: str, parameters: dict) -> object:
    result = parse_strict_model_output(
        json.dumps(
            {
                "decision": "EXECUTE",
                "reason": "Ready.",
                "clarification_question": None,
                "api_plan": [{"endpoint": endpoint, "parameters": parameters}],
            }
        )
    )
    if result.parsed is None:
        raise AssertionError(result.to_dict())
    return result.parsed


class ConcreteEndpointResolutionTests(unittest.TestCase):
    def test_visible_concrete_path_resolves_and_preserves_parameters(self) -> None:
        output = _output(
            "/drones/drone-1/command/take_off", {"altitude": 20}
        )
        before = validate_grounded_plan(output, _context())

        result = resolve_concrete_endpoints(output, _context())

        self.assertEqual(before.containment_stage, ENDPOINT_SCHEMA_STAGE)
        self.assertEqual(result.resolved_calls, 1)
        self.assertEqual(
            result.output.api_plan[0].endpoint,
            "/drones/{id}/command/take_off",
        )
        self.assertEqual(
            result.output.api_plan[0].parameters,
            {"id": "drone-1", "altitude": 20},
        )
        self.assertEqual(
            validate_grounded_plan(result.output, _context()).containment_stage,
            ACCEPTED_STAGE,
        )
        self.assertEqual(output.api_plan[0].parameters, {"altitude": 20})

    def test_unknown_drone_command_and_conflicting_id_remain_invalid(self) -> None:
        cases = (
            ("/drones/unknown/command/take_off", {"altitude": 20}),
            ("/drones/drone-1/command/teleport", {"altitude": 20}),
            (
                "/drones/drone-1/command/take_off",
                {"id": "drone-2", "altitude": 20},
            ),
            (
                "/drones/drone-1/command/take_off?altitude=20",
                {"altitude": 20},
            ),
        )
        for endpoint, parameters in cases:
            with self.subTest(endpoint=endpoint, parameters=parameters):
                output = _output(endpoint, parameters)
                result = resolve_concrete_endpoints(output, _context())
                self.assertEqual(result.resolved_calls, 0)
                self.assertEqual(result.output, output)
                self.assertEqual(
                    validate_grounded_plan(result.output, _context()).containment_stage,
                    ENDPOINT_SCHEMA_STAGE,
                )

    def test_catalog_template_is_unchanged(self) -> None:
        output = _output(
            "/drones/{id}/command/take_off",
            {"id": "drone-1", "altitude": 20},
        )
        result = resolve_concrete_endpoints(output, _context())
        self.assertEqual(result.resolved_calls, 0)
        self.assertEqual(result.output, output)


if __name__ == "__main__":
    unittest.main()
