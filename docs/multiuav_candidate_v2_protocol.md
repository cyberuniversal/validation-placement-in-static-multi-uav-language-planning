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

`run_candidate(context, backend)` is the provider-independent, single-attempt
entry point for this exploratory candidate. It screens the agent-visible request
before calling the backend, uses the existing M1 first-call prompt for a plan,
retains the prompt and raw generation in its return value, parses strict JSON,
then applies endpoint resolution and the frozen grounding validator. It never
executes a command. An absent drone, malformed generation, backend failure,
model refusal, or rejected plan cannot be released. This is not an M3 repair:
the published M1--M4 outputs and scores are unchanged.

Run the synthetic interface tests with
`python -m pytest -q tests/test_multiuav_candidate_v2.py`. They demonstrate
code behavior only. No new model inference or prospective mission outcome has
been obtained from this entry point, and the retrospective replay below cannot
establish that the system now distinguishes executable requests in operation.

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

After commit `fa84f1c4937281840d9be4f5d4475e6c9d5dbc53`, the unmodified
candidate was audited on calibration with
`python scripts/audit_multiuav_candidate_v2.py --split calibration`.
Among 1,450 generated cases, it agreed with 1,443 proposed decisions. Two
CLARIFY and five EXECUTE cases were screened as BLOCK. All seven belong to
source tasks `664cc6ac` and `e23fd2a2`, whose instructions ask four drones to
act while the visible fleet has three and the named drones repeat. These cases
need human adjudication before calling the candidate wrong or the generated
labels correct. Seven additional missing-information instructions still contain
the value recorded as removed. The calibration audit remains a generator-label
check, not a planning result.

## Inspected-test replay (contaminated)

`python scripts/analyze_multiuav_candidate_replay_v2.py` replays the frozen
M1 outputs through this already frozen candidate. The original test outputs
were inspected before candidate design, and the screen recognizes phrases
introduced by the case generator. Thus this replay is an engineering
counterfactual, **not** prospective held-out evidence for the manuscript.

| Model | Released on 852 labeled executable cases | Official-command matches among released | Released on 568 labeled non-executable cases |
|---|---:|---:|---:|
| Qwen2.5-3B-Instruct | 309 | 49 | 0 |
| Qwen2.5-7B-Instruct | 281 | 158 | 0 |

The official-command match uses the existing scorer. A static match is not
simulator or physical execution. The zero in the rightmost column is partly a
generator-template result and does not establish safety for natural language
outside these controlled variants. Original checkpoints and registered tables
remain unchanged. Aggregate and sanitized per-case records are preserved beside
the train/calibration audits.

Before a revised paper claim, obtain and audit independent new mission cases,
freeze the entire candidate and scoring protocol, run new model inference, and
report executable static plan fidelity, false refusal, and unsupported
continuation together. Official simulator and physical outcomes remain not
evaluated until actually executed.
