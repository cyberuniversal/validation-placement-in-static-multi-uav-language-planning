"""Analysis guards for the train-only local-perception probe."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from scripts.analyze_multiuav_train_observations_v2 import aggregate
from scripts.probe_multiuav_train_observations_v2 import (
    EXPECTED_BENCHMARK_SHA256,
    EXPECTED_UPSTREAM_COMMIT,
    sha256,
)


class ObservationAggregateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.case_dir = self.root / "case"
        self.case_dir.mkdir()
        self.raw_path = self.case_dir / "raw_agent_observations.json"
        self.summary_path = self.case_dir / "summary.json"
        raw = {
            "case_id": "case", "session_id": "session",
            "agent_drones": [{"id": "drone"}],
            "agent_nearby_targets_by_drone": {"drone": [{"id": "target"}]},
        }
        self.raw_path.write_text(json.dumps(raw), encoding="utf-8")
        self.summary = {
            "case_id": "case", "session_id": "session", "source_task_id": "task",
            "status": "train_only_official_agent_observation_feasibility_not_paper_evaluation",
            "raw_agent_observations_sha256": sha256(self.raw_path),
            "benchmark_sha256": EXPECTED_BENCHMARK_SHA256,
            "upstream_commit": EXPECTED_UPSTREAM_COMMIT,
            "agent_privileged_data_http_status": 403,
            "model_loaded": False, "drone_command_issued": False,
            "simulator_task_evaluated": False,
            "setup_method": "official_session_controller_direct_not_http_post",
            "agent_drone_count": 1,
            "nearby_target_counts_by_drone": {"drone": 1},
            "distinct_locally_observed_target_count": 1,
            "source_target_count_setup_only": 2,
        }
        self.save_summary()

    def save_summary(self) -> None:
        self.summary_path.write_text(json.dumps(self.summary), encoding="utf-8")

    def expected(self) -> list[dict[str, str]]:
        return [{"case_id": "case", "session_id": "session", "source_task_id": "task"}]

    def test_valid_probe_is_counted_without_exposing_target(self) -> None:
        result = aggregate(self.root, self.expected())
        self.assertEqual(result["cases_with_locally_observed_targets"], 1)
        self.assertEqual(result["distinct_session_count"], 1)
        self.assertNotIn('"id": "target"', json.dumps(result))

    def test_missing_case_fails(self) -> None:
        with self.assertRaisesRegex(ValueError, "missing training cases"):
            aggregate(self.root, self.expected() + [{
                "case_id": "other", "session_id": "other", "source_task_id": "other",
            }])

    def test_modified_raw_fails_checksum(self) -> None:
        self.raw_path.write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "checksum mismatch"):
            aggregate(self.root, self.expected())

    def test_privileged_access_fails(self) -> None:
        self.summary["agent_privileged_data_http_status"] = 200
        self.save_summary()
        with self.assertRaisesRegex(ValueError, "role boundary failed"):
            aggregate(self.root, self.expected())

    def test_model_activity_fails(self) -> None:
        self.summary["model_loaded"] = True
        self.save_summary()
        with self.assertRaisesRegex(ValueError, "unexpected activity"):
            aggregate(self.root, self.expected())

    def test_wrong_selected_session_fails(self) -> None:
        self.summary["session_id"] = "different"
        self.save_summary()
        with self.assertRaisesRegex(ValueError, "selection identity mismatch"):
            aggregate(self.root, self.expected())


if __name__ == "__main__":
    unittest.main()
