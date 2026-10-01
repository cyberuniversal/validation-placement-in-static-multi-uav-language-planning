# Reviewer criticisms: evidence and remaining gates

This is a status ledger, not a rebuttal claiming that every criticism is
resolved. The registered M1--M4 results and `paper/main.tex` remain unchanged.
The follow-up diagnostics below are post-hoc or training-only. They cannot be
promoted into prospective paper performance.

| Reviewer concern | What is already evidenced | Remaining gate |
|---|---|---|
| M3 versus M4 does not isolate validation placement | The manuscript calls M4 *model-call-count-matched*, not placement-matched. A paired M3-trace replay holds the prompt, generations, rules, and calls fixed and varies enforcement timing; it found no executable-fidelity or unsupported-continuation difference. | Prospectively run matched pipelines with identical validation rules and prompt content. The trace replay is conditional on M3 generations and cannot measure compute savings from early stopping. |
| All 852 executable cases fail static plan fidelity | The registered zero is explicit. The inspected-test endpoint-resolution replay found potential command matches but also admitted non-executable cases; the candidate replay is contaminated by prior inspection. | Establish nonzero *prospective* executable fidelity on untouched missions while maintaining containment, or retain the negative result. No such result exists. |
| Planner errors versus validator mismatch | A stage taxonomy is reported. The frozen validator accepted 206 of 249 fully instantiated upstream plans and rejected 43. The 15-case training pilot matched no official command sequences; four sessions had no initially local target observation. | Audit a larger, stratified sample of actual failed model outputs and adjudicate intended commands and validator decisions. A target-observation probe cannot allocate causal blame. |
| Always-block comparison and over-refusal | The post-hoc always-BLOCK reference scores 20.0% overall strict success; 7B M3 scores 16.1%. M3 falsely refuses all 852 executable cases. | Show discrimination between executable and non-executable requests prospectively; perfect containment alone is insufficient. |
| Mixed metric directions in the main figure | The revised figure separates positively oriented containment and strict success. | No new experiment required; verify layout before submission. |
| M3 latency/energy advantage might be early termination | The manuscript reports generated-token and termination differences and disclaims intrinsic efficiency. | Matched-work compute experiment or within-outcome analysis on sufficiently powered new runs. Existing resource contrast is configuration-level only. |
| Only two Qwen2.5 checkpoints | The paper limits the model-family conclusion. | Freeze and run an independent model family on the same controlled protocol, with model revision and decoding recorded. Not done. |
| Constructed variants are not real operator missions | The controlled-derivative design and external-validity limit are explicit. | Obtain genuinely new operator-style mission sessions, audit provenance, and keep them untouched until protocol freeze. Not available. |
| Only a 30-cluster/150-row construction review | The existing expert packet is preserved; it is not a full benchmark-label or model-output audit. | Independent blinded review of a larger stratified packet with disagreement/adjudication records. No independent reviewer is currently available. |
| Source tasks share 15 held-out sessions | Post-hoc session-clustered intervals and session counts are reported separately from source-task-clustered primary intervals. | More independent sessions for stable higher-level uncertainty; the present 15 cannot justify a rich hierarchical model. |
| Resource evidence: one RTX 3090, 30 clusters, three repetitions | Hardware and repetition limits are disclosed; raw resource evidence is preserved. | Replicate on independently controlled hardware and/or more clusters/repetitions after the executable-utility problem is solved. Not done. |

The scripted train-only official-server probe now verifies a bounded AGENT
observation-command-observation cycle on two reviewed cases, but both official
task checks failed. It is not a model-driven planning result. The immediate
technical next gate is a pinned-model run through this loop, followed by
train-only diagnosis of executable utility and unsafe continuation. It must
avoid privileged world fields and preserve every failed attempt. The source sessions in the frozen
study have already been assigned or inspected; a later claim-bearing test
requires new untouched sessions and independent adjudication. Neither is
available at this time. Do not relabel a retrospective replay as that test.
