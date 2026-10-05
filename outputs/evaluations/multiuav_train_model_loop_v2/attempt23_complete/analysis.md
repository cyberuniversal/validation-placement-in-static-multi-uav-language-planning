# Attempt a23: captured evidence and derived metrics

The immutable execution configuration is in `run_summary.json`; the submitted
job is `infra/nautilus/train-model-loop-3b-v2-a23-job.yaml`. `job_started.yaml`
and `pod_started.yaml` were captured during startup; `job.yaml` and `pod.yaml`
after completion. `pod.log` is the Kubernetes log capture; `durable_console.log`
is the exact copied PVC log produced by the job's `tee` redirection.

Raw output and journals remain in the ignored directory below. Their hashes
match the preserved run summary. `derived_metrics.json` is calculated from
the AGENT snapshots and executed command records. It records 24 attempted
commands, three takeoffs, 21 rectangle sweep moves, two observed targets,
aggregate progress from 0 to 47, and a false official task check. Acceptance
of all 24 commands comes from the run summary. This is a development retry
of an inspected training case.

Reproduce the derived file from the repository root using PowerShell:

```powershell
$attemptDir = 'outputs/multiuav/train-model-loop-v2/4cea97cd/attempt-23'
$trace = Get-Content "$attemptDir/raw.json" -Raw | ConvertFrom-Json
$targetIds = @(
    $trace.run.snapshots | ForEach-Object {
        $_.nearby_targets_by_drone.PSObject.Properties | ForEach-Object { $_.Value }
    } | ForEach-Object { $_.id } | Sort-Object -Unique
)
$actionCounts = @(
    $trace.run.commands | Group-Object {
        '{0}|{1}' -f $_.action.command, $_.action.source
    } | ForEach-Object {
        [ordered]@{ command_and_source = $_.Name; count = $_.Count }
    }
)
[ordered]@{
    schema_version = 1
    case_id = $trace.configuration.case_id
    raw_sha256 = (Get-FileHash "$attemptDir/raw.json" -Algorithm SHA256).Hash.ToLowerInvariant()
    distinct_agent_observed_target_count = $targetIds.Count
    initial_aggregate_session_progress = $trace.run.snapshots[0].task_progress.progress_percentage
    final_aggregate_session_progress = $trace.run.snapshots[-1].task_progress.progress_percentage
    attempted_commands = $trace.run.commands.Count
    action_counts = $actionCounts
    official_task_check_result = $trace.run.task_check.result
} | ConvertTo-Json -Depth 6 | Set-Content `
    outputs/evaluations/multiuav_train_model_loop_v2/attempt23_complete/derived_metrics.json `
    -Encoding utf8
```
