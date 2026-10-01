import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from shepherd_ai.multiuav_manuscript_audit import (
    audit_multiuav_manuscript,
    render_manuscript_audit,
)


ROOT = Path(__file__).resolve().parents[1]
MANUSCRIPT = ROOT / "reports/multiuav_validation_placement_manuscript_v1.md"


class MultiUavManuscriptAuditTests(unittest.TestCase):
    def test_current_manuscript_passes_internal_traceability(self) -> None:
        audit = audit_multiuav_manuscript(ROOT)

        self.assertTrue(audit["valid"])
        self.assertEqual(
            audit["status"],
            "manuscript_internal_traceability_passed_final_package_pending",
        )
        self.assertFalse(audit["final_submission_ready"])
        self.assertFalse(audit["raw_model_outputs_accessed"])
        self.assertFalse(audit["hidden_labels_accessed"])
        self.assertGreaterEqual(len(audit["artifact_bindings"]), 22)
        self.assertEqual(audit["failed_checks"], [])
        self.assertTrue(audit["checks"]["abstract_within_250_words"])
        self.assertTrue(audit["checks"]["standalone_references_complete"])
        self.assertTrue(audit["checks"]["embedded_figures_valid"])
        self.assertTrue(audit["mentor_review_ready"])
        self.assertTrue(audit["checks"]["review_resolution_present"])
        self.assertTrue(audit["checks"]["reviewer_analysis_valid"])
        self.assertTrue(audit["checks"]["reviewer_figure_manifest_valid"])
        self.assertTrue(audit["checks"]["reviewer_findings_traced"])
        text_binding = audit["artifact_bindings"]["accuracy_contrast_table"]
        figure_binding = audit["artifact_bindings"]["accuracy_primary_figure"]
        contrast_path = (
            ROOT
            / "outputs"
            / "tables"
            / "multiuav_accuracy_registered_contrasts_v1.csv"
        )
        canonical_contrast = contrast_path.read_text(
            encoding="utf-8-sig"
        ).encode("utf-8")
        self.assertEqual(text_binding["hash_basis"], "utf8_lf_normalized")
        self.assertEqual(
            text_binding["sha256"],
            hashlib.sha256(canonical_contrast).hexdigest(),
        )
        self.assertEqual(figure_binding["hash_basis"], "raw_bytes")
        rendered = render_manuscript_audit(audit)
        self.assertIn("## Manuscript Metrics", rendered)
        self.assertIn("## Artifact Bindings", rendered)
        self.assertIn("`manuscript`", rendered)

    def test_missing_claim_limit_fails_audit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            manuscript = Path(temporary) / "manuscript.md"
            text = MANUSCRIPT.read_text(encoding="utf-8").replace(
                "GPU-board energy is not workstation, simulator, network, or UAV energy.",
                "GPU-board energy was measured.",
            )
            manuscript.write_text(text, encoding="utf-8")

            audit = audit_multiuav_manuscript(ROOT, manuscript_path=manuscript)

        self.assertFalse(audit["valid"])
        self.assertIn("gpu_board_energy_scope_disclosed", audit["failed_checks"])

    def test_resource_manifest_mutation_is_rejected(self) -> None:
        source = ROOT / "outputs/evaluations/multiuav_resource_reporting_v1/manifest.json"
        with tempfile.TemporaryDirectory() as temporary:
            manifest_path = Path(temporary) / "manifest.json"
            manifest = json.loads(source.read_text(encoding="utf-8"))
            manifest["status"] = "mutated"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            audit = audit_multiuav_manuscript(
                ROOT, resource_manifest_path=manifest_path
            )

        self.assertFalse(audit["valid"])
        self.assertIn("resource_reporting_manifest_valid", audit["failed_checks"])

    def test_reviewer_summary_mutation_is_rejected(self) -> None:
        source = (
            ROOT
            / "outputs/evaluations/multiuav_reviewer_analysis_v1/summary.json"
        )
        with tempfile.TemporaryDirectory() as temporary:
            summary_path = Path(temporary) / "summary.json"
            summary = json.loads(source.read_text(encoding="utf-8"))
            summary["always_block_reference"][0]["strict_success_cases"] = 285
            summary_path.write_text(json.dumps(summary), encoding="utf-8")

            audit = audit_multiuav_manuscript(
                ROOT, reviewer_summary_path=summary_path
            )

        self.assertFalse(audit["valid"])
        self.assertIn("reviewer_analysis_valid", audit["failed_checks"])


if __name__ == "__main__":
    unittest.main()
