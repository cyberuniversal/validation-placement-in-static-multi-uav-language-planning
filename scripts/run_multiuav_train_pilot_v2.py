"""Run a bounded, checkpointed 3B inference pilot on reviewed training cases."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from shepherd_ai.multiuav_interventions import materialize_case_context  # noqa: E402
from shepherd_ai.multiuav_model_cache import verify_cached_snapshot  # noqa: E402
from shepherd_ai.multiuav_model_revisions import REGISTERED_MODEL_REVISIONS  # noqa: E402
from shepherd_ai.multiuav_prompts import build_first_call_request  # noqa: E402
from shepherd_ai.multiuav_qwen_backend import (  # noqa: E402
    LocalQwenBackend,
    QwenBackendConfig,
)

DATASET = ROOT / "datasets/multiuav_plat/intervention_pilot_v2.json"
REVIEW = ROOT / "reports/multiuav_intervention_pilot_review_completed_v2.csv"
REVIEW_VALIDATION = (
    ROOT / "datasets/multiuav_plat/intervention_pilot_review_validation_v2.json"
)
MODEL_ID = "Qwen/Qwen2.5-3B-Instruct"
MODEL_REVISION = next(
    item.revision for item in REGISTERED_MODEL_REVISIONS if item.model_id == MODEL_ID
)
SEED = 17


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _registered_crlf_sha256(path: Path) -> str:
    """Hash review-bound text using the CRLF bytes registered by validation."""

    raw = path.read_bytes()
    lf = raw.replace(b"\r\n", b"\n")
    if b"\r" in lf:
        raise ValueError(f"unsupported line endings in review-bound file: {path}")
    return hashlib.sha256(lf.replace(b"\n", b"\r\n")).hexdigest()


def select_cases() -> list[dict[str, Any]]:
    """Select one reviewed canonical case per training scenario/difficulty."""

    validation = json.loads(REVIEW_VALIDATION.read_text(encoding="utf-8"))
    if validation.get("valid") is not True:
        raise ValueError("training pilot review validation is not valid")
    if _registered_crlf_sha256(DATASET) != validation["dataset_sha256"]:
        raise ValueError("training pilot dataset hash differs from review validation")
    if _registered_crlf_sha256(REVIEW) != validation["review_packet_sha256"]:
        raise ValueError("training pilot review packet hash differs from validation")
    with REVIEW.open("r", encoding="utf-8-sig", newline="") as stream:
        approved = {
            row["case_id"]
            for row in csv.DictReader(stream)
            if row["review_status"] == "approved" and row["case_valid"] == "yes"
        }
    clusters = json.loads(DATASET.read_text(encoding="utf-8"))["clusters"]
    strata: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for cluster in clusters:
        if cluster["split"] != "train":
            raise ValueError("pilot contains a non-training cluster")
        if any(case["case_id"] not in approved for case in cluster["cases"]):
            raise ValueError("pilot contains a case absent from approved review")
        strata.setdefault((cluster["scenario"], cluster["difficulty"]), []).append(
            cluster
        )
    if len(strata) != 15 or any(len(items) != 2 for items in strata.values()):
        raise ValueError("expected two reviewed clusters in each of 15 strata")
    selected: list[dict[str, Any]] = []
    for stratum in sorted(strata):
        cluster = min(strata[stratum], key=lambda row: row["source_task_id"])
        case = next(
            item for item in cluster["cases"]
            if item["variant"] == "canonical_execute"
        )
        selected.append({
            "case_id": case["case_id"],
            "source_task_id": cluster["source_task_id"],
            "session_id": cluster["session_id"],
            "scenario": cluster["scenario"],
            "difficulty": cluster["difficulty"],
            "context": materialize_case_context(cluster, case),
        })
    return selected


def _read_completed(path: Path, run_hash: str, expected: set[str]) -> set[str]:
    if not path.exists():
        return set()
    completed: set[str] = set()
    with path.open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            row = json.loads(line)
            case_id = row["case_id"]
            if row["run_hash"] != run_hash or case_id not in expected:
                raise ValueError(f"checkpoint row {line_number} differs from pilot")
            if case_id in completed:
                raise ValueError(f"duplicate checkpoint case: {case_id}")
            completed.add(case_id)
    return completed


def _write_summary(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--cache-audit", type=Path)
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args()
    cases = select_cases()
    commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    if subprocess.check_output(
        ["git", "status", "--porcelain"], cwd=ROOT, text=True
    ).strip():
        raise ValueError("pilot requires a clean, committed checkout")
    configuration = {
        "study": "multiuav_executable_fidelity_followup_v2_train_pilot",
        "code_commit": commit,
        "model_id": MODEL_ID,
        "model_revision": MODEL_REVISION,
        "method": "M1_first_call_unmodified",
        "case_ids": [case["case_id"] for case in cases],
        "dataset_sha256": _registered_crlf_sha256(DATASET),
        "dataset_checkout_sha256": _sha256(DATASET),
        "review_sha256": _registered_crlf_sha256(REVIEW),
        "review_checkout_sha256": _sha256(REVIEW),
        "prompt_source_sha256": _sha256(
            ROOT / "src/shepherd_ai/multiuav_prompts.py"
        ),
        "decoding": {"do_sample": False, "num_beams": 1, "max_new_tokens": 512},
        "seed": SEED,
    }
    run_hash = hashlib.sha256(
        json.dumps(configuration, sort_keys=True).encode("utf-8")
    ).hexdigest()
    completed = _read_completed(args.results, run_hash, set(configuration["case_ids"]))
    summary = {
        "status": "preflight_only" if args.preflight_only else "running",
        "configuration": configuration,
        "run_hash": run_hash,
        "expected_rows": len(cases),
        "durable_rows": len(completed),
        "raw_results_path": str(args.results),
        "model_loaded": False,
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    if args.preflight_only:
        _write_summary(args.summary, summary)
        print(json.dumps({"status": summary["status"], "expected_rows": len(cases)}))
        return
    if args.cache_audit is None:
        raise ValueError("model inference requires --cache-audit")
    audit = json.loads(args.cache_audit.read_text(encoding="utf-8"))
    if audit.get("model_id") != MODEL_ID or audit.get("revision") != MODEL_REVISION:
        raise ValueError("cache audit model identity differs from pilot")
    verify_cached_snapshot(audit)
    import torch  # noqa: PLC0415

    torch.manual_seed(SEED)
    config = QwenBackendConfig(
        model_id=MODEL_ID, revision=MODEL_REVISION, max_new_tokens=512,
        dtype="float16", cache_dir="/workspace/hf-cache",
    )
    backend = LocalQwenBackend.from_cached(config)
    summary["model_loaded"] = True
    _write_summary(args.summary, summary)
    args.results.parent.mkdir(parents=True, exist_ok=True)
    try:
        with args.results.open("a", encoding="utf-8") as stream:
            for case in cases:
                if case["case_id"] in completed:
                    continue
                request = build_first_call_request("M1_monolithic", case["context"])
                generation = backend.generate(request)
                if generation.generation_status != "GENERATED":
                    raise RuntimeError("model generation did not complete")
                row = {
                    "run_hash": run_hash,
                    "case_id": case["case_id"],
                    "source_task_id": case["source_task_id"],
                    "session_id": case["session_id"],
                    "scenario": case["scenario"],
                    "difficulty": case["difficulty"],
                    "request": request.to_dict(),
                    "generation": generation.to_dict(),
                }
                stream.write(json.dumps(row, sort_keys=True) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
                completed.add(case["case_id"])
                summary["durable_rows"] = len(completed)
                _write_summary(args.summary, summary)
                print(json.dumps({"status": "pilot_progress", "durable_rows": len(completed)}), flush=True)
    except BaseException:
        summary["status"] = "failed_preserved"
        _write_summary(args.summary, summary)
        raise
    summary["status"] = "complete_raw_unscored"
    summary["raw_results_sha256"] = _sha256(args.results)
    summary["completed_at_utc"] = datetime.now(timezone.utc).isoformat()
    _write_summary(args.summary, summary)
    print(json.dumps({"status": summary["status"], "durable_rows": len(completed)}))


if __name__ == "__main__":
    main()
