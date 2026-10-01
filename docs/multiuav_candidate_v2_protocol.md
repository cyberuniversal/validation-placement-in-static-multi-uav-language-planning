# Follow-up candidate v2: endpoint contract plus visible-request screen

This candidate is exploratory and separate from the frozen M1-M4 study. It does
not revise the paper's zero static plan-fidelity result.

## Candidate

1. Screen only the agent-visible instruction and fleet. An absent explicitly
   named drone or insufficient requested fleet yields BLOCK. An unresolved
   `assigned UAV` reference or benchmark-style threshold placeholder yields
   CLARIFY. Other requests may proceed to plan checking.
2. If the model supplies a nonempty EXECUTE plan, resolve only catalogued
   concrete drone URLs whose drone ID is visible and internally consistent.
3. Release only if the existing parameter-grounding and safety-bounds validator
   accepts the resolved plan. The frozen M1-M4 runner is not modified.

The screen does not read case variants, expected decisions, official commands,
or source-task IDs. However, its ambiguity patterns are recognizable products
of the intervention generator. Perfect agreement with generated labels is not
an independent safety result and may not transfer to natural operator language.

## Development audit

Run `python scripts/audit_multiuav_candidate_v2.py --split train` from the
repository root. The 899 training clusters yielded 4,495 cases. The screen
agreed with all 899 generated BLOCK labels, all 899 CLARIFY labels, and all
2,697 EXECUTE labels. This measures conformity to the constructed variants,
not plan fidelity, simulator execution, or independently verified correctness.

The audit also found 20 training missing-information instructions containing
the exact value recorded as removed by the generator. These labels require
manual semantic review. A rule that clarifies on the remaining placeholder may
be over-conservative when the value is stated elsewhere in the instruction.
Do not use these generated labels alone to establish false-refusal or
unsupported-continuation performance.

The aggregate and sanitized per-case records are in
`outputs/evaluations/multiuav_candidate_v2/`. Raw model outputs are not copied
there. The script records dataset, candidate, and row hashes.

## Evaluation boundary

The calibration sessions can check whether this *frozen* rule also conforms to
the same generator on different sessions. They were part of the original study
development, so that check is neither a new independent benchmark nor a model
planning result. All 75 existing source sessions were assigned to the original
train/calibration/test split, and the original test outputs informed the URL
diagnostic. There is no genuinely untouched source-session test set in this
repository for the follow-up.

Before a revised paper claim, obtain and audit independent new mission cases,
freeze the entire candidate and scoring protocol, run new model inference, and
report executable static plan fidelity, false refusal, and unsupported
continuation together. Official simulator and physical outcomes remain not
evaluated until actually executed.
