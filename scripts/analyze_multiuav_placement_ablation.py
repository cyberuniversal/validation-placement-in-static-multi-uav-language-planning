"""Run the frozen reviewer-requested gate-placement trace replay."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import sys
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from shepherd_ai.multiuav_placement_ablation import (  # noqa: E402
    paired_policy_bootstraps,
    replay_m3_trace,
    summarize_policy_rows,
)


DEFAULT_CHECKPOINTS = (
    ROOT
    / "datasets/multiuav_plat/nautilus/qwen25_3b_accuracy_complete_v1/checkpoint.zip",
    ROOT
    / "datasets/multiuav_plat/nautilus/qwen25_7b_accuracy_complete_v1/checkpoint.zip",
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--protocol",
        type=Path,
        default=ROOT / "datasets/multiuav_plat/placement_ablation_protocol_v1.json",
    )
    parser.add_argument(
        "--scoring-summary",
        type=Path,
        default=ROOT / "outputs/evaluations/multiuav_accuracy_scoring_v1/summary.json",
    )
    parser.add_argument("--checkpoint", type=Path, action="append")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "outputs/evaluations/multiuav_placement_ablation_v1",
    )
    parser.add_argument(
        "--tables-dir",
        type=Path,
        default=ROOT / "outputs/tables",
    )
    args = parser.parse_args()

    protocol = _read_json(args.protocol)
    if protocol.get("status") != "frozen_reviewer_requested_posthoc_addendum":
        raise ValueError("placement-ablation protocol is not frozen")
    scoring = _read_json(args.scoring_summary)
    frozen_models = {
        str(model["model_id"]): model for model in protocol["input_scope"]["models"]
    }
    scored_bindings = {
        str(matrix["model_id"]): matrix for matrix in scoring["matrices"]
    }
    checkpoint_bindings = {
        _checkpoint_identity(path)["model_id"]: path
        for path in tuple(args.checkpoint or DEFAULT_CHECKPOINTS)
    }
    if set(frozen_models) != set(scored_bindings) or set(frozen_models) != set(
        checkpoint_bindings
    ):
        raise ValueError("protocol, scoring, and checkpoint model sets differ")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    args.tables_dir.mkdir(parents=True, exist_ok=True)
    all_rate_rows: list[dict[str, Any]] = []
    all_contrast_rows: list[dict[str, Any]] = []
    model_reports: list[dict[str, Any]] = []
    replay_rows: list[dict[str, Any]] = []
    draw_records: list[dict[str, Any]] = []
    expected_traces = int(protocol["input_scope"]["expected_traces_per_model"])
    statistics = protocol["statistics"]

    for model_id in sorted(frozen_models):
        frozen = frozen_models[model_id]
        checkpoint_path = checkpoint_bindings[model_id]
        matrix = scored_bindings[model_id]
        scored_path = ROOT / str(matrix["scored_rows_archive"]["path"])
        _assert_sha(checkpoint_path, str(frozen["checkpoint_sha256"]))
        _assert_sha(scored_path, str(frozen["scored_rows_sha256"]))
        identity, checkpoint_rows = _load_checkpoint_rows(checkpoint_path)
        if identity["model_revision"] != frozen["model_revision"]:
            raise ValueError(f"{model_id}: checkpoint revision differs from protocol")
        scored_rows = _load_scored_rows(scored_path)
        checkpoint_m3 = {
            str(row["case_id"]): row
            for row in checkpoint_rows
            if row.get("method_id") == "M3_stage_wise"
        }
        scored_m3 = {
            str(row["case_id"]): row
            for row in scored_rows
            if row.get("method_id") == "M3_stage_wise"
        }
        if set(checkpoint_m3) != set(scored_m3) or len(checkpoint_m3) != expected_traces:
            raise ValueError(f"{model_id}: retained M3 trace matrix is incomplete")

        model_rows: list[dict[str, Any]] = []
        for case_id in sorted(checkpoint_m3):
            model_rows.extend(replay_m3_trace(checkpoint_m3[case_id], scored_m3[case_id]))
        model_summary = summarize_policy_rows(model_rows)
        bootstraps = paired_policy_bootstraps(
            model_rows,
            draws=int(statistics["bootstrap_draws"]),
            seed=str(statistics["bootstrap_seed"]),
        )
        for policy_id, policy in model_summary["policies"].items():
            for metric in (
                "unsupported_continuation_nonexecute",
                "false_nonexecution_execute",
                "decision_correct",
                "strict_case_success",
                "static_plan_fidelity_execute",
                "release_authorized",
            ):
                rate = policy[metric]
                all_rate_rows.append(
                    {
                        "model_id": model_id,
                        "policy_id": policy_id,
                        "metric": metric,
                        **rate,
                    }
                )
        compact_bootstraps: dict[str, Any] = {}
        for metric, report in bootstraps.items():
            analysis = report["analysis"]
            compact_bootstraps[metric] = analysis
            all_contrast_rows.append(
                {
                    "model_id": model_id,
                    "metric": metric,
                    "contrast": analysis["contrast"],
                    "point_estimate": analysis["point_estimate"],
                    "ci_lower": analysis["confidence_interval"]["lower"],
                    "ci_upper": analysis["confidence_interval"]["upper"],
                    "cluster_count": analysis["cluster_count"],
                    "bootstrap_draws": analysis["draws"],
                }
            )
            draw_records.append(
                {
                    "model_id": model_id,
                    "metric": metric,
                    "draws": report["raw_bootstrap_draws"],
                }
            )
        model_reports.append(
            {
                "model_id": model_id,
                "model_revision": frozen["model_revision"],
                "checkpoint": _record(checkpoint_path),
                "scored_rows": _record(scored_path),
                "descriptive": model_summary,
                "paired_cluster_bootstraps": compact_bootstraps,
            }
        )
        replay_rows.extend(model_rows)

    rates_path = args.tables_dir / "multiuav_placement_ablation_rates_v1.csv"
    contrasts_path = args.tables_dir / "multiuav_placement_ablation_contrasts_v1.csv"
    rows_path = args.output_dir / "placement_replay_rows.zip"
    draws_path = args.output_dir / "placement_bootstrap_evidence.zip"
    _write_csv(rates_path, all_rate_rows)
    _write_csv(contrasts_path, all_contrast_rows)
    _write_jsonl_zip(rows_path, "placement_replay_rows.jsonl", replay_rows)
    _write_jsonl_zip(draws_path, "placement_bootstrap_draws.jsonl", draw_records)
    summary = {
        "schema_version": 1,
        "status": "reviewer_requested_placement_ablation_complete",
        "registered_study_changed": False,
        "new_model_inference_performed": False,
        "raw_model_output_exposed_in_derivatives": False,
        "protocol": _record(args.protocol),
        "scoring_summary": _record(args.scoring_summary),
        "models": model_reports,
        "artifacts": {
            "rates": _record(rates_path),
            "contrasts": _record(contrasts_path),
            "replay_rows": _record(rows_path),
            "bootstrap_evidence": _record(draws_path),
        },
        "claim_limit": (
            "Paired trace replay isolates deterministic enforcement order on retained "
            "M3 transcripts. It does not estimate operational early-stop compute, test "
            "another model family, or establish simulator or physical mission success."
        ),
    }
    output = args.output_dir / "summary.json"
    output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))


def _checkpoint_identity(path: Path) -> dict[str, str]:
    with ZipFile(path) as archive:
        envelope = json.loads(archive.read("run_config.json"))
    config = envelope["config"]
    return {
        "model_id": str(config["model_id"]),
        "model_revision": str(config["model_revision"]),
    }


def _load_checkpoint_rows(path: Path) -> tuple[dict[str, str], list[dict[str, Any]]]:
    with ZipFile(path) as archive:
        envelope = json.loads(archive.read("run_config.json"))
        identity = envelope["config"]
        rows = [
            json.loads(line)
            for line in archive.read("results.jsonl").decode("utf-8").splitlines()
            if line.strip()
        ]
    return {
        "model_id": str(identity["model_id"]),
        "model_revision": str(identity["model_revision"]),
    }, rows


def _load_scored_rows(path: Path) -> list[dict[str, Any]]:
    with ZipFile(path) as archive:
        return [
            json.loads(line)
            for line in archive.read("scored_rows.jsonl").decode("utf-8").splitlines()
            if line.strip()
        ]


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise ValueError(f"table is empty: {path}")
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _write_jsonl_zip(path: Path, member: str, rows: list[dict[str, Any]]) -> None:
    content = "".join(
        json.dumps(row, separators=(",", ":"), sort_keys=True) + "\n" for row in rows
    ).encode("utf-8")
    manifest = (
        json.dumps(
            {
                "schema_version": 1,
                "member": member,
                "rows": len(rows),
                "content_sha256": hashlib.sha256(content).hexdigest(),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")
    temporary = path.with_suffix(path.suffix + ".tmp")
    with ZipFile(temporary, "w", compression=ZIP_DEFLATED, compresslevel=9) as archive:
        for name, payload in sorted({"manifest.json": manifest, member: content}.items()):
            info = ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, payload)
    temporary.replace(path)


def _assert_sha(path: Path, expected: str) -> None:
    actual = _sha256(path)
    if actual != expected:
        raise ValueError(f"SHA-256 mismatch for {path}: {actual}")


def _record(path: Path) -> dict[str, Any]:
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


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return value


if __name__ == "__main__":
    main()
