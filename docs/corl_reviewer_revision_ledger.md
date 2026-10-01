# CoRL Reviewer Revision Ledger

This ledger records how the three external reviews were addressed. The frozen
registered analysis was not replaced or reinterpreted as confirmatory. New
diagnostics are explicitly labeled post-hoc and preserve their own artifacts.

## Completed Revisions

| Reviewer concern | Revision | Evidence |
| --- | --- | --- |
| M3 versus M4 does not isolate validation placement | Renamed the paper around pipeline configurations; strengthened the non-causal wording in the abstract, methods, discussion, limitations, and conclusion. | `paper/main.tex` |
| An always-refuse policy may outperform M3 | Added a zero-call always-BLOCK deterministic reference. It obtains 100% containment, 20.0% strict success, 100% false non-execution, and 0% executable static plan fidelity. | `outputs/tables/multiuav_accuracy_always_block_reference_v1.csv` |
| All 852 executable cases fail and need diagnosis | Added a mutually exclusive failure-location taxonomy for every model-method executable row. | `outputs/tables/multiuav_accuracy_executable_failure_taxonomy_v1.csv` |
| Validator mismatch remains plausible | Audited fully instantiated upstream reference plans against the frozen validator. Of 249 eligible plans, 206 were accepted and 43 rejected; 35 unresolved or missing templates were excluded without imputation. | `outputs/tables/multiuav_reference_plan_validator_audit_v1.csv` |
| Source tasks are nested in 15 sessions | Added a paired 10,000-draw session-clustered bootstrap sensitivity analysis and retained the registered source-task-cluster analysis. | `outputs/tables/multiuav_accuracy_session_sensitivity_v1.csv` |
| Figure 1 mixes opposite directions | Replaced it with separate containment and strict-success panels, both higher-is-better, and included the labeled always-BLOCK reference. | `paper/figures/accuracy_refusal_aware_outcomes_v2.pdf` |
| M3 resource savings may reflect early termination | The manuscript now states that termination behavior and generated-token count confound the 7B latency and energy differences; they are not intrinsic efficiency estimates. | `paper/main.tex` |

## New Findings Added to the Paper

- The always-BLOCK reference scores 284/1,420 (20.0%) strict success, exceeding
  Qwen2.5-7B M3 at 228/1,420 (16.1%). This demonstrates that the aggregate
  success metric does not establish useful executable/non-executable
  discrimination.
- Qwen2.5-3B M3 executable failures partition into 544 pre-plan containments
  and 308 output-parse errors.
- Qwen2.5-7B M3 executable failures partition into 637 model non-execution
  decisions, 187 output-parse errors, and 28 pre-plan containments.
- The frozen validator rejects 43/249 (17.3%) fully instantiated upstream
  reference plans: one at endpoint schema, three at parameter grounding, and
  39 at safety bounds.
- Session-clustered sensitivity intervals preserve the registered directional
  findings, but 15 sessions remain too few for a rich hierarchical analysis.

## Not Claimed as Resolved

The following comments require new evidence and were not fabricated or
presented as completed:

- a placement-only ablation that holds prompts, validation rules, generated
  content, and other configuration details fixed;
- evaluation on another model family;
- a larger independent human audit of labels, outputs, and validator decisions;
- additional hardware or more resource repetitions; and
- official simulator or physical execution.

These omissions are now explicit limitations. The revised paper should be
submitted as a negative systems-and-measurement result, not as evidence that
M3 is a practically successful multi-UAV planner.

## Reproduction

Run from the repository root:

```powershell
python scripts/analyze_multiuav_reviewer_feedback.py
python scripts/build_multiuav_reviewer_figure.py
Set-Location paper
pdflatex -interaction=nonstopmode -halt-on-error main.tex
pdflatex -interaction=nonstopmode -halt-on-error main.tex
```

The post-hoc analysis performs no model inference and does not read or expose
raw model text.
