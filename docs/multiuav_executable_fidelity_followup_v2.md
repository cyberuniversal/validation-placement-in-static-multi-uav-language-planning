# Executable-fidelity follow-up (post-hoc diagnostic)

This work is separate from the frozen M1-M4 paper. It uses previously inspected
held-out outputs and changes no registered result. It does not demonstrate a
working multi-UAV planner or simulator execution.

## Why investigate this

The frozen study reports zero static plan fidelity on 852 executable cases per
model and method. In the 7B M1 executable subset, 578 cases failed at the
endpoint-schema stage, while 7B M3 did not proceed on 637 cases. These are
different failure locations; improving an endpoint parser cannot by itself
repair refusals, command selection, or evidence discrimination.

The upstream MultiUAV-Plat API client issues command URLs with a concrete drone
ID in the path, for example `/drones/drone-1/command/take_off`. The frozen
validator accepts the catalog template `/drones/{id}/command/take_off` and
requires `parameters.id`. This representational mismatch can reject a valid
upstream-style call before its other properties are checked.

## Diagnostic and guardrails

`multiuav_endpoint_resolution_v2.py` maps a concrete command URL to the catalog
template only when the command is in the existing catalog, the drone ID is in
the agent-visible context, and any supplied `parameters.id` agrees with the
path. It supplies a missing `parameters.id` from that visible path. Unknown
drones, commands, query strings, and conflicting IDs are left unchanged for the
frozen validator to reject. No label or official command enters the resolver.

The replay uses only M1's frozen checkpoints and scored rows, bound by the
checksums and model revisions in
`datasets/multiuav_plat/endpoint_resolution_diagnostic_v2.json`. The script
checks all 1,420 case IDs per model, preserves derived per-case rows separately,
and records input and code hashes. It runs no model and inspects no raw model
text in its output.

Run from the repository root:

```powershell
python scripts/analyze_multiuav_endpoint_resolution_v2.py
python -m pytest -q tests/test_multiuav_endpoint_resolution_v2.py
```

## Replay observations

| Model | Executable cases admitted by changed validator | Potential static-fidelity matches | Non-executable cases admitted by changed validator |
|---|---:|---:|---:|
| Qwen2.5-3B-Instruct | 309 / 852 | 49 / 852 | 251 / 568 |
| Qwen2.5-7B-Instruct | 281 / 852 | 158 / 852 | 187 / 568 |

"Potential static-fidelity match" combines the changed validator's acceptance
with the frozen official-command matcher. These are retrospective counterfactual
counts, not newly observed prospective success rates. The source traces were
already used for the study and inspected before this rule was written. The
rightmost column counts unsafe continuation under the registered non-executable
labels. Thus a parser-only change trades some false refusals for substantial
unsafe admission; it cannot be shipped as the fix or used to update the paper's
registered zero-fidelity result.

The machine-readable aggregate is
`outputs/evaluations/multiuav_endpoint_resolution_v2/summary.json`; derived
case rows are adjacent. Original checkpoints and scored archives remain
unchanged.

## What would resolve the central limitation

1. On development data only, establish whether known-valid upstream plans pass
   the corrected interface contract and audit a stratified sample of model
   failures for parsing, command selection, grounding, and over-refusal.
2. Specify a candidate that preserves evidence and resource-conflict checks
   while allowing grounded concrete endpoints. Freeze the candidate, prompts,
   model revisions, decision thresholds, and scoring before evaluation.
3. Evaluate it on genuinely untouched source sessions and report both static
   plan fidelity on executable cases and unsupported continuation on
   non-executable cases, alongside the always-block reference. The existing
   284-source test set is no longer untouched for this change.
4. Keep simulator or physical task success labeled *not evaluated* unless an
   official execution experiment is actually run.

The next experiment must show useful executable planning without obtaining it
by silently relaxing containment. No such result has been established here.
