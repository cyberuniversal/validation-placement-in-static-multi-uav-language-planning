"""Run reviewer-requested post-hoc diagnostics without changing frozen scores."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import sys
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from shepherd_ai.multiuav_interventions import materialize_case_context  # noqa: E402
from shepherd_ai.multiuav_reviewer_analysis import (  # noqa: E402
    audit_reference_plan,
    classify_executable_failures,
    session_clustered_sensitivity,
    summarize_always_block_reference,
)
from shepherd_ai.multiuav_source import audit_benchmark_archive  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scoring-summary",
        type=Path,
        default=ROOT / "outputs/evaluations/multiuav_accuracy_scoring_v1/summary.json",
    )
    parser.add_argument(
        "--protocol",
        type=Path,
        default=ROOT / "datasets/multiuav_plat/accuracy_protocol_freeze_v1.json",
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=ROOT / "datasets/multiuav_plat/intervention_dataset_v1.json",
    )
    parser.add_argument(
        "--benchmark-archive",
        type=Path,
        default=ROOT / "external/MultiUAV-Plat/benchmark/benchmark.zip",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "outputs/evaluations/multiuav_reviewer_analysis_v1",
    )
    parser.add_argument(
        "--tables-dir",
        type=Path,
        default=ROOT / "outputs/tables",
    )
    args = parser.parse_args()

    scoring = _read_json(args.scoring_summary)
    protocol = _read_json(args.protocol)
    dataset = _read_json(args.dataset)
    archive_audit = audit_benchmark_archive(args.benchmark_archive)
    sessions = {
        str(cluster["cluster_id"]): str(cluster["session_id"])
        for cluster in dataset["clusters"]
        if cluster.get("split") == "test"
    }
    contrasts = {
        name: (
            str(protocol[name]["method_a"]),
            str(protocol[name]["method_b"]),
        )
        for name in ("primary_contrast", "confirmatory_contrast")
    }
    draws = int(protocol["statistics"]["bootstrap_draws"])
    seed = f"{protocol['statistics']['bootstrap_seed']}:session_sensitivity_v1"

    refusal_rows: list[dict] = []
    sensitivity_rows: list[dict] = []
    sensitivity_draws: dict[str, list[float]] = {}
    failure_rows: list[dict] = []
    failure_cases: list[dict] = []
    archive_bindings: list[dict] = []
    for matrix in scoring["matrices"]:
        model_id = str(matrix["model_id"])
        binding = matrix["scored_rows_archive"]
        archive_path = ROOT / str(binding["path"])
        if _sha256(archive_path) != binding["sha256"]:
            raise ValueError(f"scored archive SHA-256 mismatch: {archive_path}")
        rows = _load_scored_rows(archive_path)
        if len(rows) != int(binding["row_count"]):
            raise ValueError(f"scored archive row count mismatch: {archive_path}")
        refusal_rows.append(summarize_always_block_reference(rows, model_id=model_id))
        reports, raw_draws = session_clustered_sensitivity(
            rows,
            session_by_cluster=sessions,
            contrasts=contrasts,
            draws=draws,
            seed=seed,
            model_id=model_id,
        )
        sensitivity_rows.extend(reports)
        sensitivity_draws.update(raw_draws)
        model_failures, model_cases = classify_executable_failures(
            rows, model_id=model_id
        )
        failure_rows.extend(model_failures)
        failure_cases.extend(model_cases)
        archive_bindings.append(
            {
                "model_id": model_id,
                "path": str(binding["path"]),
                "sha256": str(binding["sha256"]),
                "rows": len(rows),
            }
        )

    reference_rows = _audit_upstream_reference_plans(
        dataset=dataset,
        benchmark_archive=args.benchmark_archive,
    )
    reference_summary = _summarize_reference_audit(reference_rows)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    args.tables_dir.mkdir(parents=True, exist_ok=True)
    refusal_path = args.tables_dir / "multiuav_accuracy_always_block_reference_v1.csv"
    sensitivity_path = args.tables_dir / "multiuav_accuracy_session_sensitivity_v1.csv"
    failure_path = args.tables_dir / "multiuav_accuracy_executable_failure_taxonomy_v1.csv"
    reference_path = args.tables_dir / "multiuav_reference_plan_validator_audit_v1.csv"
    failure_cases_path = args.output_dir / "executable_failure_locations.jsonl"
    reference_rows_path = args.output_dir / "reference_plan_validator_rows.jsonl"
    evidence_path = args.output_dir / "session_bootstrap_evidence.zip"
    _write_csv(refusal_path, refusal_rows)
    _write_csv(sensitivity_path, sensitivity_rows)
    _write_failure_csv(failure_path, failure_rows)
    _write_reference_csv(reference_path, reference_summary)
    _write_jsonl(failure_cases_path, failure_cases)
    _write_jsonl(reference_rows_path, reference_rows)
    _write_draw_archive(
        evidence_path,
        sensitivity_draws,
        metadata={
            "analysis_status": "reviewer_requested_post_hoc_sensitivity",
            "bootstrap_unit": "held_out_session",
            "draws": draws,
            "seed": seed,
        },
    )
    summary = {
        "schema_version": 1,
        "analysis_status": "reviewer_requested_post_hoc_diagnostics_complete",
        "registered_analysis_changed": False,
        "new_model_inference_performed": False,
        "scored_archive_bindings": archive_bindings,
        "input_bindings": {
            "scoring_summary": _record(args.scoring_summary),
            "protocol": _record(args.protocol),
            "dataset": _record(args.dataset),
            "benchmark_archive": {
                **_record(args.benchmark_archive),
                "pinned_archive_audit": archive_audit["archive"],
            },
        },
        "always_block_reference": refusal_rows,
        "session_clustered_sensitivity": sensitivity_rows,
        "executable_failure_taxonomy": failure_rows,
        "reference_plan_validator_audit": reference_summary,
        "artifacts": {
            "always_block_table": _record(refusal_path),
            "session_sensitivity_table": _record(sensitivity_path),
            "failure_taxonomy_table": _record(failure_path),
            "reference_validator_table": _record(reference_path),
            "failure_location_rows": _record(failure_cases_path),
            "reference_validator_rows": _record(reference_rows_path),
            "session_bootstrap_evidence": _record(evidence_path),
        },
        "claim_limit": (
            "These diagnostics are post-hoc. The always-BLOCK policy is a deterministic "
            "reference, not a registered model baseline; the reference-plan audit tests "
            "validator compatibility, not simulator execution or mission success."
        ),
    }
    output = args.output_dir / "summary.json"
    output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))


def _audit_upstream_reference_plans(*, dataset: dict, benchmark_archive: Path) -> list[dict]:
    clusters = {
        str(cluster["source_task_id"]): cluster
        for cluster in dataset["clusters"]
        if cluster.get("split") == "test"
    }
    tasks = _load_upstream_tasks(benchmark_archive, set(clusters))
    rows = []
    for source_task_id, cluster in sorted(clusters.items()):
        canonical = next(
            case for case in cluster["cases"] if case["variant"] == "canonical_execute"
        )
        context = materialize_case_context(cluster, canonical)
        task = tasks[source_task_id]
        row = audit_reference_plan(
            source_task_id=source_task_id,
            context=context,
            related_apis=task.get("related_apis"),
        )
        row["session_id"] = str(cluster["session_id"])
        row["official_command_count"] = len(task.get("commands", []))
        rows.append(row)
    return rows


def _load_upstream_tasks(path: Path, selected: set[str]) -> dict[str, dict]:
    tasks = {}
    with ZipFile(path) as archive:
        for member in archive.namelist():
            if not member.lower().endswith(".json"):
                continue
            session = json.loads(archive.read(member))
            for task in session.get("tasks", []):
                task_id = str(task.get("id", ""))
                if task_id in selected:
                    tasks[task_id] = task
    if set(tasks) != selected:
        raise ValueError("pinned benchmark does not cover all held-out source tasks")
    return tasks


def _summarize_reference_audit(rows: list[dict]) -> list[dict]:
    eligible = [row for row in rows if row["eligibility"] == "eligible_fully_instantiated"]
    excluded = len(rows) - len(eligible)
    stages: dict[str, int] = {}
    for row in eligible:
        stage = str(row["containment_stage"])
        stages[stage] = stages.get(stage, 0) + 1
    return [
        {
            "held_out_source_tasks": len(rows),
            "eligible_fully_instantiated": len(eligible),
            "excluded_unresolved_or_missing": excluded,
            "validator_accepted": sum(row["validator_accepted"] is True for row in eligible),
            "validator_rejected": sum(row["validator_accepted"] is False for row in eligible),
            "acceptance_rate": (
                sum(row["validator_accepted"] is True for row in eligible) / len(eligible)
                if eligible
                else None
            ),
            "containment_stage_counts": json.dumps(stages, sort_keys=True),
        }
    ]


def _load_scored_rows(path: Path) -> list[dict]:
    with ZipFile(path) as archive:
        return [
            json.loads(line)
            for line in archive.read("scored_rows.jsonl").decode("utf-8").splitlines()
            if line.strip()
        ]


def _write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        raise ValueError(f"table is empty: {path}")
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _write_failure_csv(path: Path, rows: list[dict]) -> None:
    categories = sorted(
        {category for row in rows for category in row["category_counts"]}
    )
    flattened = [
        {
            "model_id": row["model_id"],
            "method_id": row["method_id"],
            "executable_cases": row["executable_cases"],
            **{category: row["category_counts"].get(category, 0) for category in categories},
        }
        for row in rows
    ]
    _write_csv(path, flattened)


def _write_reference_csv(path: Path, rows: list[dict]) -> None:
    _write_csv(path, rows)


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def _write_draw_archive(path: Path, draws: dict[str, list[float]], metadata: dict) -> None:
    records = "".join(
        json.dumps({"analysis_id": key, "draws": values}, separators=(",", ":"), sort_keys=True)
        + "\n"
        for key, values in sorted(draws.items())
    ).encode("utf-8")
    metadata_bytes = (json.dumps(metadata, indent=2, sort_keys=True) + "\n").encode("utf-8")
    manifest_bytes = (
        json.dumps(
            {
                "schema_version": 1,
                "analyses": len(draws),
                "files": {
                    "session_bootstrap_draws.jsonl": _content_record(records),
                    "metadata.json": _content_record(metadata_bytes),
                },
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")
    temporary = path.with_suffix(path.suffix + ".tmp")
    with ZipFile(temporary, "w", compression=ZIP_DEFLATED, compresslevel=9) as archive:
        for name, content in sorted(
            {
                "manifest.json": manifest_bytes,
                "metadata.json": metadata_bytes,
                "session_bootstrap_draws.jsonl": records,
            }.items()
        ):
            info = ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, content)
    temporary.replace(path)


def _content_record(content: bytes) -> dict:
    return {"bytes": len(content), "sha256": hashlib.sha256(content).hexdigest()}


def _record(path: Path) -> dict:
    resolved = path.resolve()
    try:
        rendered = resolved.relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        rendered = resolved.as_posix()
    return {"path": rendered, "bytes": path.stat().st_size, "sha256": _sha256(path)}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_json(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return payload


if __name__ == "__main__":
    main()
