"""Guards for the train-only official observation feasibility probe."""

from __future__ import annotations

import unittest

from scripts.probe_multiuav_train_observations_v2 import session_payload


class TrainObservationProbeTests(unittest.TestCase):
    def test_setup_uses_one_task_and_excludes_history(self) -> None:
        session = {
            "name": "train", "description": "", "task_type": "area_search",
            "task_description": "", "is_distance_3d": False,
            "canvas_width": 10.0, "canvas_height": 10.0,
            "drones": [], "targets": [], "obstacles": [], "environment": {},
            "tasks": [{"id": "chosen"}, {"id": "other"}],
            "history": {"secret": "not-restored"},
            "statistics": {"secret": "not-restored"},
        }
        payload = session_payload(session, "chosen")
        self.assertEqual(payload["tasks"], [{"id": "chosen"}])
        self.assertNotIn("history", payload)
        self.assertNotIn("statistics", payload)

    def test_setup_rejects_missing_task(self) -> None:
        with self.assertRaisesRegex(ValueError, "absent or duplicated"):
            session_payload({"tasks": []}, "missing")


if __name__ == "__main__":
    unittest.main()
