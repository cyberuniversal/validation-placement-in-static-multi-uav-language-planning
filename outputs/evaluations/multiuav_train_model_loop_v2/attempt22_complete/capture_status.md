# Attempt a22 archival status

The durable summaries were copied with the raw and command/event journals
after completion on 2026-10-04. Their three journal hashes were rechecked on
2026-10-05 and match `run_summary.json`. Raw model output remains in the
ignored local `outputs/multiuav/train-model-loop-v2/4cea97cd/attempt-22/`
directory and the run's PVC directory.

The live pod was observed as `Succeeded` with zero restarts on 2026-10-04.
GPU telemetry then identified an NVIDIA GeForce RTX 2080 Ti (11,264 MiB).
The job was unavailable on 2026-10-05: `kubectl get job` returned `NotFound`.
Live job/pod YAML and full logs could not be recovered. They are not present
in this archive. The submitted job manifest is preserved in
`infra/nautilus/train-model-loop-3b-v2-a22-job.yaml`.

This record distinguishes captured evidence from unavailable metadata; it
does not reconstruct or replace the missing logs.
