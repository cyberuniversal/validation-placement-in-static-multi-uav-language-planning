"""Train-only pilot selection and durable checkpoint guards."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from scripts.run_multiuav_train_pilot_v2 import _read_completed, select_cases
from scripts.analyze_multiuav_train_pilot_v2 import (
    DEFAULT_BENCHMARK,
    _official_commands,
)


class TrainPilotTests(unittest.TestCase):
    def test_selected_cases_are_reviewed_training_canonicals(self) -> None:
        cases = select_cases()
        self.assertEqual(len(cases), 15)
        self.assertEqual(len({case["session_id"] for case in cases}), 15)
        self.assertEqual(
            len({(case["scenario"], case["difficulty"]) for case in cases}), 15
        )
        for case in cases:
            self.assertTrue(case["case_id"].endswith(":canonical_execute"))
            self.assertFalse(
                {"registered_decision", "proposed_decision", "variant"}
                & set(case["context"])
            )

    def test_checkpoint_rejects_changed_run_and_duplicates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "results.jsonl"
            row = {"run_hash": "frozen", "case_id": "case-1"}
            path.write_text(json.dumps(row) + "\n", encoding="utf-8")
            self.assertEqual(
                _read_completed(path, "frozen", {"case-1"}), {"case-1"}
            )
            with self.assertRaisesRegex(ValueError, "differs"):
                _read_completed(path, "changed", {"case-1"})
            path.write_text((json.dumps(row) + "\n") * 2, encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "duplicate"):
                _read_completed(path, "frozen", {"case-1"})

    def test_pinned_benchmark_covers_selected_official_commands(self) -> None:
        selected = {case["source_task_id"] for case in select_cases()}
        commands = _official_commands(DEFAULT_BENCHMARK, selected)
        self.assertEqual(set(commands), selected)
        self.assertTrue(all(commands.values()))


if __name__ == "__main__":
    unittest.main()
