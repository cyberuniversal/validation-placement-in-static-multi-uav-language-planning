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

An actual run additionally requires `--cache-audit` pointing to the verified
pinned 3B snapshot audit on the same host. It must run with GPU access and the
`[inference]` dependencies. Preserve raw outputs and failed runs; analyze them
only after the pilot finishes. Do not promote a pilot result into the paper.

Before a claim-bearing follow-up, address the detected generated-label defects
and acquire new independent, adjudicated missions. All 75 benchmark source
sessions were assigned to the original study; neither its calibration nor
inspected test split is a fresh final test for this candidate.
