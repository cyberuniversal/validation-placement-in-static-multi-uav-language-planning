import unittest


from shepherd_ai.multiuav_placement_ablation import (
    paired_policy_bootstraps,
    replay_m3_trace,
    summarize_policy_rows,
)


def _checkpoint_row(
    *,
    preplan_valid: bool,
    provisional_decision: str,
    raw_decision: str,
    final_parse_error: bool = False,
) -> dict:
    parsed = None if final_parse_error else {"decision": raw_decision}
    return {
        "case_id": "case-1",
        "method_id": "M3_stage_wise",
        "model_id": "model-1",
        "result": {
            "actual_model_call_count": 2,
            "calls": [
                {"generation": {"generation_status": "GENERATED"}},
                {"generation": {"generation_status": "GENERATED"}},
            ],
            "intermediate_ledger": {
                "parse_status": "PARSED",
                "parsed": {"provisional_decision": provisional_decision},
            },
            "preplan_report": {
                "valid": preplan_valid,
                "containment_stage": (
                    "pre_plan_accepted"
                    if preplan_valid
                    else "pre_plan_decision_consistency"
                ),
            },
            "final_parse": {
                "parse_status": "PARSE_ERROR" if final_parse_error else "PARSED",
                "parsed": parsed,
            },
            "deterministic_postplan_report": {
                "valid": True,
                "containment_stage": "accepted",
            }
            if not final_parse_error
            else None,
        },
    }


def _scored_row(*, raw_decision: str, registered_decision: str) -> dict:
    return {
        "case_id": "case-1",
        "method_id": "M3_stage_wise",
        "cluster_id": "cluster-1",
        "source_task_id": "source-1",
        "variant": "variant-1",
        "registered_decision": registered_decision,
        "raw_model_decision": raw_decision,
        "static_plan_fidelity": False if registered_decision == "EXECUTE" else None,
    }


class MultiUavPlacementAblationTests(unittest.TestCase):
    def test_early_gate_contains_before_a_correct_final_clarification(self) -> None:
        checkpoint = _checkpoint_row(
            preplan_valid=False,
            provisional_decision="CLARIFY",
            raw_decision="CLARIFY",
        )
        scored = _scored_row(
            raw_decision="CLARIFY",
            registered_decision="CLARIFY",
        )

        rows = replay_m3_trace(checkpoint, scored)

        early, deferred = rows
        self.assertEqual(early["policy_id"], "early_preplan_enforcement")
        self.assertEqual(early["system_disposition"], "CONTAINED")
        self.assertFalse(early["decision_correct"])
        self.assertEqual(deferred["policy_id"], "deferred_release_enforcement")
        self.assertEqual(deferred["system_disposition"], "CLARIFY")
        self.assertTrue(deferred["decision_correct"])
        self.assertEqual(early["trace_sha256"], deferred["trace_sha256"])

    def test_both_policies_prevent_release_for_invalid_execute_trace(self) -> None:
        checkpoint = _checkpoint_row(
            preplan_valid=False,
            provisional_decision="BLOCK",
            raw_decision="EXECUTE",
        )
        scored = _scored_row(
            raw_decision="EXECUTE",
            registered_decision="BLOCK",
        )

        early, deferred = replay_m3_trace(checkpoint, scored)

        self.assertFalse(early["release_authorized"])
        self.assertFalse(deferred["release_authorized"])
        self.assertFalse(early["unsupported_continuation"])
        self.assertFalse(deferred["unsupported_continuation"])

    def test_valid_ledger_defers_to_identical_final_release_result(self) -> None:
        checkpoint = _checkpoint_row(
            preplan_valid=True,
            provisional_decision="EXECUTE",
            raw_decision="EXECUTE",
        )
        scored = _scored_row(
            raw_decision="EXECUTE",
            registered_decision="EXECUTE",
        )

        early, deferred = replay_m3_trace(checkpoint, scored)

        self.assertEqual(early["system_disposition"], "EXECUTE")
        self.assertEqual(deferred["system_disposition"], "EXECUTE")
        self.assertTrue(early["release_authorized"])
        self.assertTrue(deferred["release_authorized"])
        self.assertFalse(early["static_plan_fidelity"])
        self.assertFalse(deferred["static_plan_fidelity"])

    def test_rejects_non_m3_or_mismatched_rows(self) -> None:
        checkpoint = _checkpoint_row(
            preplan_valid=True,
            provisional_decision="EXECUTE",
            raw_decision="EXECUTE",
        )
        scored = _scored_row(
            raw_decision="EXECUTE",
            registered_decision="EXECUTE",
        )
        checkpoint["method_id"] = "M4_post_plan_compute_matched"

        with self.assertRaisesRegex(ValueError, "M3"):
            replay_m3_trace(checkpoint, scored)

    def test_summary_and_bootstrap_keep_policies_paired(self) -> None:
        rows = []
        for cluster_index in range(2):
            for variant_index, registered in enumerate(
                ("EXECUTE", "EXECUTE", "EXECUTE", "CLARIFY", "BLOCK")
            ):
                for policy in (
                    "early_preplan_enforcement",
                    "deferred_release_enforcement",
                ):
                    rows.append(
                        {
                            "model_id": "model-1",
                            "cluster_id": f"cluster-{cluster_index}",
                            "variant": f"variant-{variant_index}",
                            "policy_id": policy,
                            "registered_decision": registered,
                            "release_authorized": False,
                            "unsupported_continuation": False,
                            "false_nonexecution": registered == "EXECUTE",
                            "decision_correct": (
                                policy == "deferred_release_enforcement"
                                and registered != "EXECUTE"
                            ),
                            "static_plan_fidelity": (
                                False if registered == "EXECUTE" else None
                            ),
                            "strict_case_success": (
                                policy == "deferred_release_enforcement"
                                and registered != "EXECUTE"
                            ),
                            "containment_stage": "fixture",
                        }
                    )

        summary = summarize_policy_rows(rows)
        analyses = paired_policy_bootstraps(rows, draws=100, seed="fixture")

        self.assertEqual(summary["policies"]["early_preplan_enforcement"]["rows"], 10)
        self.assertEqual(
            summary["policies"]["deferred_release_enforcement"]
            ["strict_case_success"]["numerator"],
            4,
        )
        self.assertEqual(analyses["strict_case_success"]["analysis"]["cluster_count"], 2)
        self.assertEqual(
            analyses["false_nonexecution_execute"]["analysis"]
            ["cases_per_method_per_cluster"],
            3,
        )


if __name__ == "__main__":
    unittest.main()
