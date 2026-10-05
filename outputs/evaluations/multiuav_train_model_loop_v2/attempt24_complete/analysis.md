# Attempt a24: budget diagnostic

`run_summary.json` binds the model, source case, policy, seed, code revision,
and 64-command allowance. Initial and final live job/pod YAML were captured.
`pod.log` is the Kubernetes stream capture; `durable_console.log` is copied
from the PVC log. Raw generations and journals remain in the ignored local
attempt directory and the PVC. Their hashes match the summary.

The official check is false. Fifty-one of 52 commands succeeded, aggregate
session progress reached 65%, and only two targets were observed. The final
path was rejected for an obstacle intersection. The first 24 selected actions
match a23 exactly; hardware differs (a23 V100, a24 RTX A4000), so this is a
functional development diagnostic rather than a hardware/resource comparison.
Selected search attempts were distributed 7, 7, and 6 across the three drones.

Reproduce `derived_metrics.json` from the repository root using PowerShell:

```powershell
$attemptDir = 'outputs/multiuav/train-model-loop-v2/4cea97cd/attempt-24'
$referencePath = 'outputs/multiuav/train-model-loop-v2/4cea97cd/attempt-23/raw.json'
$trace = Get-Content "$attemptDir/raw.json" -Raw | ConvertFrom-Json
$reference = Get-Content $referencePath -Raw | ConvertFrom-Json
$matched = 0
for ($i = 0; $i -lt [Math]::Min($reference.run.commands.Count, $trace.run.commands.Count); $i++) {
    if (($reference.run.commands[$i].action | ConvertTo-Json -Compress) -cne
        ($trace.run.commands[$i].action | ConvertTo-Json -Compress)) { break }
    $matched++
}
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
$searchCounts = @(
    $trace.run.commands | Where-Object { $_.action.source -eq 'bounded_local_search' } |
    Group-Object { $_.action.drone_id } | ForEach-Object {
        [ordered]@{ drone_id = $_.Name; selected_search_commands = $_.Count }
    }
)
[ordered]@{
    schema_version = 1
    case_id = $trace.configuration.case_id
    raw_sha256 = (Get-FileHash "$attemptDir/raw.json" -Algorithm SHA256).Hash.ToLowerInvariant()
    reference_raw_sha256 = (Get-FileHash $referencePath -Algorithm SHA256).Hash.ToLowerInvariant()
    matching_action_prefix = $matched
    distinct_agent_observed_target_count = $targetIds.Count
    initial_aggregate_session_progress = $trace.run.snapshots[0].task_progress.progress_percentage
    final_aggregate_session_progress = $trace.run.snapshots[-1].task_progress.progress_percentage
    attempted_commands = $trace.run.commands.Count
    action_counts = $actionCounts
    search_commands_by_drone = $searchCounts
    official_task_check_result = $trace.run.task_check.result
} | ConvertTo-Json -Depth 6 | Set-Content `
    outputs/evaluations/multiuav_train_model_loop_v2/attempt24_complete/derived_metrics.json `
    -Encoding utf8
```
