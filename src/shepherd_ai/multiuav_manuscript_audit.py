"""Internal traceability audit for the active MultiUAV manuscript."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping


AUDIT_VERSION = "multiuav_manuscript_traceability_v1"
TEXT_SUFFIXES = {".csv", ".json", ".md", ".txt"}


def audit_multiuav_manuscript(
    repository_root: Path,
    *,
    manuscript_path: Path | None = None,
    resource_manifest_path: Path | None = None,
    reviewer_summary_path: Path | None = None,
    placement_summary_path: Path | None = None,
) -> dict[str, Any]:
    """Audit aggregate evidence and manuscript claims without raw-row access."""

    root = repository_root.resolve()
    manuscript_path = (
        manuscript_path
        or root / "reports" / "multiuav_validation_placement_manuscript_v1.md"
    ).resolve()
    resource_manifest_path = (
        resource_manifest_path
        or root
        / "outputs"
        / "evaluations"
        / "multiuav_resource_reporting_v1"
        / "manifest.json"
    ).resolve()
    reviewer_summary_path = (
        reviewer_summary_path
        or root
        / "outputs"
        / "evaluations"
        / "multiuav_reviewer_analysis_v1"
        / "summary.json"
    ).resolve()
    placement_summary_path = (
        placement_summary_path
        or root
        / "outputs"
        / "evaluations"
        / "multiuav_placement_ablation_v1"
        / "summary.json"
    ).resolve()
    paths = {
        "accuracy_admission": root
        / "datasets/multiuav_plat/accuracy_matrix_admission_v1.json",
        "accuracy_scoring_summary": root
        / "outputs/evaluations/multiuav_accuracy_scoring_v1/summary.json",
        "accuracy_bootstrap_summary": root
        / "outputs/evaluations/multiuav_accuracy_bootstrap_v1/summary.json",
        "accuracy_figure_manifest": root
        / "outputs/evaluations/multiuav_accuracy_figures_v1/manifest.json",
        "accuracy_rate_table": root
        / "outputs/tables/multiuav_accuracy_primary_rates_v1.csv",
        "accuracy_contrast_table": root
        / "outputs/tables/multiuav_accuracy_registered_contrasts_v1.csv",
        "accuracy_session_table": root
        / "outputs/tables/multiuav_accuracy_session_statistics_v1.csv",
        "accuracy_failure_analysis": root
        / "outputs/evaluations/multiuav_accuracy_failure_analysis_v1.json",
        "accuracy_failure_cases": root
        / "outputs/evaluations/multiuav_accuracy_failure_cases_v1.zip",
        "reviewer_analysis_summary": reviewer_summary_path,
        "placement_ablation_summary": placement_summary_path,
        "placement_ablation_protocol": root
        / "datasets/multiuav_plat/placement_ablation_protocol_v1.json",
        "reviewer_figure_manifest": root
        / "paper/figures/accuracy_refusal_aware_outcomes_v2_manifest.json",
        "reviewer_revision_ledger": root / "docs/corl_reviewer_revision_ledger.md",
        "publication_tex": root / "paper/main.tex",
        "resource_admission": root
        / "datasets/multiuav_plat/resource_campaign_admission_v1.json",
        "resource_analysis_freeze": root
        / "datasets/multiuav_plat/resource_analysis_freeze_v1.json",
        "resource_analysis_deviation": root
        / "datasets/multiuav_plat/resource_analysis_protocol_deviation_v1.json",
        "resource_analysis_summary": root
        / "outputs/evaluations/multiuav_resource_analysis_v1/summary.json",
        "resource_derived_rows": root
        / "outputs/evaluations/multiuav_resource_analysis_v1/derived_resource_rows.zip",
        "resource_bootstrap_evidence": root
        / "outputs/evaluations/multiuav_resource_analysis_v1/bootstrap_evidence.zip",
        "resource_reporting_manifest": resource_manifest_path,
        "resource_descriptive_table": root
        / "outputs/tables/multiuav_resource_descriptive_v1.csv",
        "resource_contrast_table": root
        / "outputs/tables/multiuav_resource_contrasts_v1.csv",
        "manuscript": manuscript_path,
        "bibliography": root / "reports/week9_bibliography.md",
        "final_architecture": root / "docs/final_pipeline_architecture.md",
        "review_resolution": root / "docs/multiuav_review_resolution_final.md",
        "accuracy_primary_figure": root
        / "reports/figures/multiuav_accuracy_primary_outcomes_v1.png",
        "accuracy_contrast_figure": root
        / "reports/figures/multiuav_accuracy_registered_contrasts_v1.png",
        "resource_primary_figure": root
        / "reports/figures/multiuav_resource_m3_minus_m1_v1.png",
        "resource_matched_figure": root
        / "reports/figures/multiuav_resource_m3_minus_m4_v1.png",
    }
    checks: dict[str, bool] = {
        "all_required_artifacts_present": all(path.is_file() for path in paths.values())
    }
    bindings = {
        name: _file_record(root, path)
        for name, path in paths.items()
        if path.is_file()
    }
    if not checks["all_required_artifacts_present"]:
        return _result(checks=checks, bindings=bindings)

    accuracy_admission = _read_object(paths["accuracy_admission"])
    accuracy_scoring = _read_object(paths["accuracy_scoring_summary"])
    accuracy_bootstrap = _read_object(paths["accuracy_bootstrap_summary"])
    accuracy_figures = _read_object(paths["accuracy_figure_manifest"])
    reviewer_analysis = _read_object(paths["reviewer_analysis_summary"])
    placement_analysis = _read_object(paths["placement_ablation_summary"])
    reviewer_figure = _read_object(paths["reviewer_figure_manifest"])
    resource_admission = _read_object(paths["resource_admission"])
    resource_summary = _read_object(paths["resource_analysis_summary"])
    resource_manifest = _read_object(paths["resource_reporting_manifest"])
    manuscript = paths["manuscript"].read_text(encoding="utf-8-sig")
    publication_tex = paths["publication_tex"].read_text(encoding="utf-8-sig")
    bibliography = paths["bibliography"].read_text(encoding="utf-8-sig")
    abstract_words = _abstract_word_count(manuscript)
    citation_ids = _body_citation_ids(manuscript)
    reference_ids = _reference_ids(manuscript)
    embedded_figures = set(
        re.findall(r"!\[[^\]]+\]\(([^)]+)\)", manuscript)
    )
    expected_figures = {
        "figures/multiuav_accuracy_primary_outcomes_v1.png",
        "figures/multiuav_accuracy_registered_contrasts_v1.png",
        "figures/multiuav_resource_m3_minus_m1_v1.png",
        "figures/multiuav_resource_m3_minus_m4_v1.png",
    }

    checks.update(
        {
            "accuracy_admission_valid": (
                accuracy_admission.get("valid") is True
                and accuracy_admission.get("rows_total") == 11_360
            ),
            "accuracy_scoring_valid": (
                accuracy_scoring.get("status")
                == "accuracy_scoring_complete_cluster_analysis_pending"
                and accuracy_scoring.get("rows_total") == 11_360
                and accuracy_scoring.get("models_invoked") is False
            ),
            "accuracy_bootstrap_valid": (
                accuracy_bootstrap.get("status")
                == "accuracy_cluster_bootstrap_complete_figures_pending"
                and accuracy_bootstrap.get("registered_analyses") == 8
                and accuracy_bootstrap.get("null_hypothesis_tests_run") is False
            ),
            "accuracy_figure_manifest_valid": _manifest_valid(
                accuracy_figures,
                root=root,
                status="accuracy_publication_figures_complete",
            ),
            "reviewer_analysis_valid": _reviewer_analysis_valid(
                reviewer_analysis
            ),
            "placement_ablation_valid": _placement_ablation_valid(
                placement_analysis
            ),
            "reviewer_figure_manifest_valid": _manifest_valid(
                reviewer_figure,
                root=root,
                status="reviewer_revised_figure_complete",
            ),
            "reviewer_findings_traced": all(
                value in publication_tex
                for value in (
                    "always-\\textsc{Block}",
                    "43/249",
                    "17.3\\%",
                    "session-clustered sensitivity",
                    "accuracy_refusal_aware_outcomes_v2.pdf",
                )
            ),
            "placement_findings_traced": all(
                value in publication_tex
                for value in (
                    "Placement-Controlled Trace Replay",
                    "0/568 unsupported continuations",
                    "852/852 false non-executions",
                    "0/852",
                    "executable static-plan successes",
                    "-0.1606",
                    "[-0.1697,-0.1507]",
                )
            ),
            "resource_admission_valid": (
                resource_admission.get("valid") is True
                and resource_admission.get("rows_total") == 3_600
                and resource_admission.get("resource_scores_computed") is False
            ),
            "resource_analysis_valid": (
                resource_summary.get("status")
                == "resource_analysis_complete_reporting_pending"
                and resource_summary.get("resource_metric_rows") == 3_600
                and resource_summary.get("paired_contrast_count") == 96
                and resource_summary.get("models_invoked") is False
                and resource_summary.get("hidden_labels_accessed") is False
            ),
            "resource_reporting_manifest_valid": _manifest_valid(
                resource_manifest,
                root=root,
                status="resource_tables_figures_and_report_complete",
            ),
            "accuracy_values_traced": all(
                value in manuscript
                for value in ("-0.7905", "-0.6831", "0.1606", "0.1521")
            ),
            "resource_values_traced": all(
                value in manuscript
                for value in ("3,600", "3,297.68", "3,155.56", "5,669-6,279")
            ),
            "controlled_derivative_limit_disclosed": "controlled derivatives" in manuscript,
            "within_qwen_limit_disclosed": (
                "two scales in one model family" in manuscript
            ),
            "static_fidelity_limit_disclosed": "Plan fidelity is static" in manuscript,
            "zero_executable_static_fidelity_disclosed": (
                "zero static plan fidelity" in manuscript
            ),
            "legacy_components_excluded": all(
                name in manuscript
                for name in ("Whisper", "DistilBERT", "vision")
            ),
            "call_count_match_limit_disclosed": (
                "matched to M3 only by model-call count" in manuscript
            ),
            "resource_secondary_exploratory_disclosed": (
                "### 4.2 Secondary Resource Results" in manuscript
                and "exploratory and carry no confirmatory claim" in manuscript
            ),
            "resource_repetitions_separate_disclosed": (
                "Repetitions are reported separately" in manuscript
            ),
            "gpu_board_energy_scope_disclosed": (
                "GPU-board energy is not workstation, simulator, network, or UAV energy."
                in manuscript
            ),
            "resource_deviation_disclosed": (
                "post-admission diagnostic printed one row's request and raw output"
                in manuscript
            ),
            "negative_result_disclosed": (
                "each achieved zero strict end-to-end success" in manuscript
            ),
            "required_literature_resolves": all(
                identifier in bibliography
                for identifier in (
                    "[L1]",
                    "[L2]",
                    "[L7]",
                    "[L8]",
                    "[E1]",
                    "[E2]",
                    "[E3]",
                    "[E4]",
                )
            ),
            "abstract_within_250_words": 1 <= abstract_words <= 250,
            "standalone_references_complete": (
                citation_ids == reference_ids
                and citation_ids
                == {"L1", "L2", "L7", "L8", "E1", "E2", "E3", "E4"}
            ),
            "embedded_figures_valid": (
                embedded_figures == expected_figures
                and all(
                    (manuscript_path.parent / figure).is_file()
                    for figure in embedded_figures
                )
            ),
            "review_resolution_present": paths[
                "review_resolution"
            ].is_file(),
            "no_unresolved_manuscript_placeholders": not re.search(
                r"\b(?:TODO|TBD|FIXME)\b|\?\?\?|\[citation needed\]",
                manuscript,
                flags=re.IGNORECASE,
            ),
        }
    )
    result = _result(checks=checks, bindings=bindings)
    result["manuscript_metrics"] = {
        "abstract_words": abstract_words,
        "body_citation_ids": sorted(citation_ids),
        "reference_ids": sorted(reference_ids),
        "embedded_figure_count": len(embedded_figures),
    }
    return result


def _reviewer_analysis_valid(summary: Mapping[str, Any]) -> bool:
    if (
        summary.get("analysis_status")
        != "reviewer_requested_post_hoc_diagnostics_complete"
        or summary.get("registered_analysis_changed") is not False
        or summary.get("new_model_inference_performed") is not False
    ):
        return False
    references = summary.get("always_block_reference")
    audits = summary.get("reference_plan_validator_audit")
    sessions = summary.get("session_clustered_sensitivity")
    if not isinstance(references, list) or len(references) != 2:
        return False
    if not all(
        item.get("cases") == 1_420
        and item.get("strict_success_cases") == 284
        and item.get("strict_success_rate") == 0.2
        and item.get("unsupported_continuation_cases") == 0
        and item.get("false_nonexecution_execute") == 852
        for item in references
    ):
        return False
    if not isinstance(audits, list) or len(audits) != 1:
        return False
    audit = audits[0]
    if not (
        audit.get("held_out_source_tasks") == 284
        and audit.get("eligible_fully_instantiated") == 249
        and audit.get("validator_accepted") == 206
        and audit.get("validator_rejected") == 43
    ):
        return False
    return isinstance(sessions, list) and len(sessions) == 8 and all(
        item.get("sessions") == 15 for item in sessions
    )


def _placement_ablation_valid(summary: Mapping[str, Any]) -> bool:
    if (
        summary.get("status")
        != "reviewer_requested_placement_ablation_complete"
        or summary.get("registered_study_changed") is not False
        or summary.get("new_model_inference_performed") is not False
        or summary.get("raw_model_output_exposed_in_derivatives") is not False
    ):
        return False
    models = summary.get("models")
    if not isinstance(models, list) or len(models) != 2:
        return False
    by_id = {str(item.get("model_id")): item for item in models}
    expected = {
        "Qwen/Qwen2.5-3B-Instruct": {"early": 0, "deferred": 0},
        "Qwen/Qwen2.5-7B-Instruct": {"early": 0, "deferred": 228},
    }
    if set(by_id) != set(expected):
        return False
    for model_id, strict in expected.items():
        descriptive = by_id[model_id].get("descriptive")
        if not isinstance(descriptive, Mapping) or descriptive.get("paired_traces") != 1420:
            return False
        policies = descriptive.get("policies")
        if not isinstance(policies, Mapping):
            return False
        for policy_id, label in (
            ("early_preplan_enforcement", "early"),
            ("deferred_release_enforcement", "deferred"),
        ):
            policy = policies.get(policy_id)
            if not isinstance(policy, Mapping):
                return False
            if not (
                policy.get("unsupported_continuation_nonexecute")
                == {"numerator": 0, "denominator": 568, "rate": 0.0}
                and policy.get("false_nonexecution_execute")
                == {"numerator": 852, "denominator": 852, "rate": 1.0}
                and policy.get("static_plan_fidelity_execute")
                == {"numerator": 0, "denominator": 852, "rate": 0.0}
                and policy.get("strict_case_success", {}).get("numerator")
                == strict[label]
            ):
                return False
    return True


def render_manuscript_audit(audit: Mapping[str, Any]) -> str:
    """Render a concise human-readable audit report."""

    lines = [
        "# MultiUAV Manuscript Traceability Audit",
        "",
        f"- Status: `{audit['status']}`",
        f"- Valid: `{str(audit['valid']).lower()}`",
        f"- Final submission ready: `{str(audit['final_submission_ready']).lower()}`",
        f"- Raw model outputs accessed: `{str(audit['raw_model_outputs_accessed']).lower()}`",
        f"- Hidden labels accessed: `{str(audit['hidden_labels_accessed']).lower()}`",
        "",
        "## Checks",
        "",
    ]
    for name, passed in audit["checks"].items():
        lines.append(f"- `{name}`: `{'pass' if passed else 'fail'}`")
    metrics = audit.get("manuscript_metrics")
    if isinstance(metrics, Mapping):
        lines.extend(
            [
                "",
                "## Manuscript Metrics",
                "",
                f"- Abstract words: `{metrics.get('abstract_words')}`",
                "- Body citation identifiers: "
                + ", ".join(
                    f"`{item}`" for item in metrics.get("body_citation_ids", [])
                ),
                "- Reference identifiers: "
                + ", ".join(
                    f"`{item}`" for item in metrics.get("reference_ids", [])
                ),
                "- Embedded figures: "
                + f"`{metrics.get('embedded_figure_count')}`",
            ]
        )
    lines.extend(
        [
            "",
            "## Artifact Bindings",
            "",
            "| Artifact | Path | SHA-256 |",
            "|---|---|---|",
        ]
    )
    for name, record in audit["artifact_bindings"].items():
        lines.append(
            f"| `{name}` | `{record['path']}` | `{record['sha256']}` |"
        )
    lines.extend(["", "## Remaining Gates", ""])
    lines.extend(f"- {item}" for item in audit["remaining_gates"])
    lines.extend(
        [
            "",
            "This is an internal evidence and claim-boundary audit. It is not peer review, venue acceptance, or independent replication.",
            "",
        ]
    )
    return "\n".join(lines)


def _result(
    *, checks: Mapping[str, bool], bindings: Mapping[str, Mapping[str, Any]]
) -> dict[str, Any]:
    failed = sorted(name for name, passed in checks.items() if not passed)
    valid = not failed
    return {
        "schema_version": 1,
        "audit_version": AUDIT_VERSION,
        "status": (
            "manuscript_internal_traceability_passed_final_package_pending"
            if valid
            else "manuscript_internal_traceability_failed"
        ),
        "valid": valid,
        "checks": dict(sorted(checks.items())),
        "failed_checks": failed,
        "artifact_bindings": dict(sorted(bindings.items())),
        "source_code_sha256": {
            "multiuav_manuscript_audit.py": _sha256_file(Path(__file__)),
        },
        "raw_model_outputs_accessed": False,
        "hidden_labels_accessed": False,
        "final_submission_ready": False,
        "mentor_review_ready": valid,
        "remaining_gates": [
            "final package assembly and checksum validation",
            "concluding mentor review",
        ],
        "next_gate": "final_package_assembly_pending",
    }


def _manifest_valid(
    manifest: Mapping[str, Any], *, root: Path, status: str
) -> bool:
    if manifest.get("status") != status:
        return False
    outputs = manifest.get("outputs")
    if not isinstance(outputs, list) or not outputs:
        return False
    for record in outputs:
        if not isinstance(record, Mapping):
            return False
        path = root / str(record.get("path", ""))
        if not path.is_file() or _sha256_file(path) != record.get("sha256"):
            return False
    return True


def _abstract_word_count(manuscript: str) -> int:
    match = re.search(
        r"^## Abstract\s+(.*?)(?=^## \d+\.)",
        manuscript,
        flags=re.DOTALL | re.MULTILINE,
    )
    if match is None:
        return 0
    return len(re.findall(r"\b[\w'-]+\b", match.group(1)))


def _body_citation_ids(manuscript: str) -> set[str]:
    body = manuscript.split("## References", maxsplit=1)[0]
    return set(re.findall(r"\[((?:L|E)\d+)\]", body))


def _reference_ids(manuscript: str) -> set[str]:
    if "## References" not in manuscript:
        return set()
    references = manuscript.split("## References", maxsplit=1)[1]
    return set(
        re.findall(r"^\*\*\[((?:L|E)\d+)\]\*\*", references, flags=re.MULTILINE)
    )


def _read_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"invalid audit input: {path}") from error
    if not isinstance(value, dict):
        raise ValueError(f"audit input is not an object: {path}")
    return value


def _file_record(root: Path, path: Path) -> dict[str, Any]:
    try:
        rendered = path.resolve().relative_to(root).as_posix()
    except ValueError:
        rendered = path.resolve().as_posix()
    data, hash_basis = _binding_bytes(path)
    return {
        "path": rendered,
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "hash_basis": hash_basis,
    }


def _binding_bytes(path: Path) -> tuple[bytes, str]:
    if path.suffix.lower() in TEXT_SUFFIXES:
        text = path.read_text(encoding="utf-8-sig")
        return text.encode("utf-8"), "utf8_lf_normalized"
    return path.read_bytes(), "raw_bytes"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()
