# Planner-competence training pilot v2

This pilot diagnoses wrong-command behavior on training data. It is not
fine-tuning, a test-set evaluation, or evidence of generalization. It does not
change the frozen M1-M4 study or the manuscript.

The selection script verifies the reviewed pilot dataset and CSV checksums,
requires each selected case to appear in the 150-case approved review packet,
and chooses the lexicographically first canonical EXECUTE cluster within each
of the 15 scenario/difficulty strata. This yields 15 cases from 15 training
sessions. The CSV's reviewer identity is not independently machine-verifiable;
the structural review validation states this limitation.

Inference uses the frozen M1 first-call prompt and pinned
`Qwen/Qwen2.5-3B-Instruct` revision
`aa8e72537993ba99e69dfaafa59ed015b17504d1`. Decoding is greedy,
`max_new_tokens=512`, with seed 17. The run binds the Git commit, dataset and
review hashes, exact case IDs, prompt-source hash, model ID/revision, and
decoding to a run hash. It refuses a dirty checkout. Each raw prompt/generation
row is flushed and fsynced; reruns resume only matching case IDs and run hash.
The durable raw JSONL belongs under `/workspace/results/train-pilot-v2/` on the
Nautilus PVC, not in the tracked analysis tables.

The script supports a no-model preflight:

```powershell
python scripts/run_multiuav_train_pilot_v2.py --results outputs/multiuav/train-pilot-v2/results.jsonl --summary outputs/multiuav/train-pilot-v2/run_summary.json --preflight-only
```

The Nautilus run is specified by
`infra/nautilus/train-pilot-3b-v2-job.yaml` and uses code commit
`81542027268e54358f9deabe0b932e5ed0b4cd73`. Once the raw summary is
complete, retrieve the raw JSONL and summary from the PVC without modifying
them and run:

```powershell
python scripts/analyze_multiuav_train_pilot_v2.py --results <raw-results.jsonl> --run-summary <run-summary.json> --benchmark external/MultiUAV-Plat/benchmark/benchmark.zip --output-dir outputs/evaluations/multiuav_train_pilot_v2
```

The analysis checks input hashes and completeness, then writes only sanitized
case-level failure categories, planned command names, official command names,
and an aggregate summary. The raw prompt and generation remain separate.

Attempt 1 (`validation-placement-train-pilot-3b-v2`) failed before model load:
the Linux clone checked out the reviewed pilot dataset and review CSV with LF,
while their registered SHA-256 values bind CRLF bytes. There are zero raw
generation rows from this attempt. Its job YAML, pod YAML, and log are preserved
under `outputs/evaluations/multiuav_train_pilot_v2/failed_attempt_1/`.
Attempt 2 (`validation-placement-train-pilot-3b-v2-a2`) also failed before
model load because its persistent Git clone had retained the LF checkout from
attempt 1; changing `.gitattributes` did not rewrite those existing files.
Its job YAML, pod YAML, and log are preserved separately under
`failed_attempt_2/`. The runner now canonicalizes line endings only for the
two review-bound text files before comparing them with their registered CRLF
hashes. It rejects lone CR bytes and records both registered and checkout
hashes in the run configuration. This does not alter the review data or its
registered hashes. Any retry must use a new job name and immutable code commit.

Attempt 3 (`validation-placement-train-pilot-3b-v2-a3`) completed on an
NVIDIA A10 with 15/15 durable raw rows. The raw file is retained on the
Nautilus PVC at `/workspace/results/train-pilot-v2/3b/` and in the local
ignored `outputs/multiuav/train-pilot-v2/3b/` directory. Its SHA-256 is
`f2eddf1ad51629b33449ed4011e183372d0a8c14d3f8550413d4b4c84359b9f6`;
the copied file matches the run summary. Job/pod YAML and logs are preserved
under `outputs/evaluations/multiuav_train_pilot_v2/completed_attempt_3/`.
The Linux checkout used LF bytes for the reviewed text files while the local
Windows checkout uses CRLF. Both normalize to the registered review hashes;
the analyzer accepts either recorded checkout representation while checking
the exact raw-results hash.

The 15-case training diagnostic found 0 official command-sequence matches:
7 strict model-output parse failures (4 invalid JSON, 3 invalid endpoint),
3 endpoint-schema rejections, 2 parameter-grounding rejections, and 3 plans
that passed local release checks but did not match the official command
sequence. Three invalid-JSON outputs hit the 512-token cap; this is a
diagnostic association, not proof that a higher cap fixes them. The 3 released
wrong-command cases show that passing the present local safety checks is not
equivalent to task fidelity. No simulator execution was performed. These are
reviewed training cases only, not held-out evidence of improvement.

A separate inspection of these 15 supplied agent-visible contexts found that
only 2 instructions contain an explicit `(x, y, z)` coordinate triple; none
contains a `targets` collection or observation results. The prompt advertises
permitted observation endpoints, but this pilot's single model call does not
execute an observation tool. This does not prove that every task is impossible
to plan, but it is a concrete mismatch to investigate before tuning prompts
against official full-plan fidelity. A follow-up should first establish which
required endpoint parameters are actually recoverable from visible evidence
and which require a real observation round trip. It must not fill unavailable
coordinates from the official reference plan.

An actual run additionally requires `--cache-audit` pointing to the verified
pinned 3B snapshot audit on the same host. It must run with GPU access and the
`[inference]` dependencies. Preserve raw outputs and failed runs; analyze them
only after the pilot finishes. Do not promote a pilot result into the paper.

Before a claim-bearing follow-up, address the detected generated-label defects
and acquire new independent, adjudicated missions. All 75 benchmark source
sessions were assigned to the original study; neither its calibration nor
inspected test split is a fresh final test for this candidate.
