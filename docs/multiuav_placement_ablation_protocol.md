# Reviewer-requested placement ablation

## Why this addendum exists

The registered M3-versus-M4 comparison is model-call-count-matched, but it is
not a placement-only comparison. Its prompts, generated content, and validation
behavior differ. Therefore, that comparison cannot by itself identify the
causal effect of validation placement.

This addendum answers that criticism with a paired trace replay. It does not
change the registered study or overwrite its evidence.

## Experimental unit and inputs

The unit is one retained M3 case trace. Each trace contains the two model calls,
the parsed evidence ledger, the deterministic pre-plan report, the final strict
output parse, and the deterministic post-plan report. All 1,420 M3 traces from
each immutable Qwen2.5 checkpoint are included.

The machine-readable freeze is
`datasets/multiuav_plat/placement_ablation_protocol_v1.json`. It binds the exact
checkpoint and scored-row SHA-256 values, model revisions, expected matrix
dimensions, outcomes, bootstrap settings, and interpretation limits.

## Conditions

`early_preplan_enforcement` applies the retained ledger validator result before
the final generation can authorize release. The recorded second call is kept as
a shadow call so both conditions use the same transcript. This must not be
interpreted as a compute-saving early stop.

`deferred_release_enforcement` interprets the identical final generation first.
When that generation requests execution, the identical ledger result and
post-plan validator are enforced at the release boundary. A final model refusal
or clarification is preserved.

Only enforcement order changes. Model identity, prompts, contexts, decoding,
both generated outputs, model-call count, validators, and labels are identical.

## Outcomes and analysis

The primary outcomes are unsupported continuation on registered non-executable
cases and false non-execution on registered executable cases. Secondary outcomes
are exact decision correctness, strict case success, and static plan fidelity on
executable cases.

Differences are early minus deferred. Confidence intervals use 10,000 paired
bootstrap resamples of the 284 source-task clusters. The two non-executable
variants, three executable variants, or all five variants are retained as
appropriate for each outcome.

## Claim boundary

This experiment can support a claim about deterministic enforcement order on
the retained M3 traces. It cannot support a claim about prompt decomposition,
model-family generality, operational compute savings, simulator execution, or
physical mission success. A null result remains informative: it would show that
the original M3-versus-M4 difference should not be attributed to placement
alone.
