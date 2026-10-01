# Final Reproduction Commands

Run commands from the repository root. The final package records Windows
PowerShell commands for deterministic local processing and the exact Kubernetes
manifests used for GPU inference.

## Environment And Checks

```powershell
python -m pip install -r requirements.txt
python -m pytest -q
python -m ruff check src scripts tests paper/build_resource_figure.py
```

## Dataset And Contract Reconstruction

These commands use each script's committed defaults and do not invoke a model:

```powershell
python scripts/audit_multiuav_plat_source.py
python scripts/build_multiuav_session_split.py
python scripts/build_multiuav_task_eligibility.py
python scripts/build_multiuav_intervention_pilot.py
python scripts/validate_multiuav_intervention_pilot.py
python scripts/validate_multiuav_intervention_review.py --review-packet reports/multiuav_intervention_pilot_review_completed_v2.csv --output datasets/multiuav_plat/intervention_pilot_review_validation_v2.json
python scripts/build_multiuav_intervention_dataset.py
python scripts/validate_multiuav_intervention_dataset.py
python scripts/audit_multiuav_expert_qc.py
python scripts/build_multiuav_accuracy_manifest.py
python scripts/audit_multiuav_scoring_contract.py
python scripts/audit_multiuav_study_wiring.py --output outputs/multiuav/study_wiring.json
```

The upstream MultiUAV-Plat checkout is pinned by the source audit and is not
redistributed as Shepherd-AI source. See `docs/multiuav_source_acquisition.md`
for acquisition and revision details.

## Accuracy Inference

The exact container image, environment, commit binding, resource request, model
ID, cache audit, smoke audit, output path, and runner arguments are preserved in
the manifests:

```powershell
kubectl apply -f infra/nautilus/accuracy-3b-job.yaml
kubectl apply -f infra/nautilus/accuracy-7b-job.yaml
```

Inside the containers, the manifests invoke `scripts/run_multiuav_accuracy.py`
with the pinned 3B or 7B model ID, offline cache/smoke audits, durable JSONL,
`checkpoint.zip`, `run_summary.json`, progress every 10 rows, and compaction
every 250 rows. Completed checkpoints and run summaries are already preserved;
rerunning inference is not required to inspect or regenerate analysis outputs.

## Accuracy Admission, Scoring, And Analysis

```powershell
python scripts/admit_multiuav_accuracy_matrices.py
python scripts/score_multiuav_accuracy_matrices.py
python scripts/analyze_multiuav_accuracy.py
python scripts/build_multiuav_accuracy_figures.py
python scripts/analyze_multiuav_reviewer_feedback.py
python scripts/build_multiuav_reviewer_figure.py
```

The analysis command performs the registered 10,000-draw source-cluster
bootstrap and writes the post-hoc session table and failure artifacts. It does
not load a model or read raw model text.

The reviewer-feedback command leaves the registered analysis unchanged and
writes a deterministic always-BLOCK reference, a 10,000-draw session-clustered
sensitivity analysis, mutually exclusive executable-failure locations, and an
audit of fully instantiated upstream reference plans against the frozen
validator. The reviewer-figure command plots positively oriented containment
and strict-success outcomes and labels the always-BLOCK result as post-hoc.
Neither command invokes a model.

## Resource Campaign

```powershell
kubectl apply -f infra/nautilus/resource-preflight-job.yaml
kubectl apply -f infra/nautilus/resource-job.yaml
python scripts/admit_multiuav_resource_campaign.py
python scripts/analyze_multiuav_resources.py
python scripts/build_multiuav_resource_report.py
```

The preflight and campaign containers check out orchestration commit
`abb9a46afed2131e18911aa88ed252747ebb9011`. The frozen per-condition run
configurations bind execution code commit
`6d0030094956626b17a9506d018e0fc077ca0ffd`. Both bindings, the offline pinned
models, one RTX 3090, and the 24-condition schedule are preserved in the raw
campaign evidence.

## Manuscript And Final Audit

```powershell
python scripts/audit_multiuav_manuscript.py
python scripts/analyze_multiuav_reviewer_feedback.py
python scripts/build_multiuav_reviewer_figure.py
python -m pytest -q
python -m ruff check src scripts tests paper/build_resource_figure.py
Set-Location paper
python build_resource_figure.py
pdflatex -interaction=nonstopmode -halt-on-error main.tex
pdflatex -interaction=nonstopmode -halt-on-error main.tex
```

The final IEEE conference manuscript is `paper/main.tex`; the compiled copy is
`paper/main.pdf`. The compact resource figure is regenerated from the frozen
CSV under `paper/data/`. A TeX distribution providing `IEEEtran` is required.
Build the anonymous CoRL 2026 SPAIS workshop version separately:

```powershell
Set-Location paper/corl_2026_spais_anonymous
pdflatex -interaction=nonstopmode -halt-on-error main.tex
bibtex main
pdflatex -interaction=nonstopmode -halt-on-error main.tex
pdflatex -interaction=nonstopmode -halt-on-error main.tex
```

The resulting `main.pdf` is four pages total, with three content pages and one
references page. The package uses the official anonymous CoRL 2026 style.

The editable deck is generated with the bundled `@oai/artifact-tool` runtime:

```powershell
node scripts/build_final_presentation.mjs
```

The script writes the committed presentation, preview images, inspection
record, and montage under `presentation/`.
