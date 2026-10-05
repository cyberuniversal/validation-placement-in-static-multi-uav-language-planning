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

## Official AGENT observation feasibility probe

The follow-up probed the upstream server on the same 15 reviewed **training**
sessions, with one selected source task per session. It restored the task and
world through the upstream session controller, then used the official HTTP
`GET /drones` and `GET /drones/{id}/nearby/targets` routes with the AGENT role.
The AGENT's `GET /sessions/current/data` returned HTTP 403 in every case. The
controller setup had SYSTEM-level access to the source world, including its
target count; those fields were not supplied to an AGENT model. No model was
loaded, no drone command was issued, and no simulator task was evaluated.

In the 15 distinct sessions, at least one target was locally observed at the
initial drone positions in 11 sessions; no target was locally observed in four.
Each restored source world had targets. These counts establish only that the
official local-perception route works and that initial AGENT observations are
sometimes incomplete. They do not establish target search, closed-loop
planning, static plan fidelity, or a safety improvement. The observed target
IDs and coordinates remain in ignored raw output, separate from the sanitized
aggregate. No held-out session was used for this probe.

The upstream HTTP `POST /sessions` setup route hung in this local harness,
including for a name-only session. Both attempted processes were terminated;
no conclusion about its behavior in a deployed server follows. The successful
probe used `session_controller.create_session_from_dict` and
`set_current_session` for SYSTEM setup while retaining official AGENT HTTP
observation and role checks. This is a feasibility probe, not an end-to-end
official-server execution result.

The isolated environment used Python 3.12, the upstream server requirements,
and locally installed `shapely==2.1.2` and `numpy==2.5.3`; the upstream
requirements omitted Shapely. Raw files are ignored under
`outputs/multiuav/train-observation-probe-v2/<source-task-id>/`. Each summary
records source and upstream hashes and the raw-file SHA-256. The aggregate
validator checks all 15 selected cases, distinct sessions, checksums, role
denial, no-model/no-command flags, and counts before writing a sanitized
summary. Reproduce with the isolated environment, using a case ID from the
reviewed training selection:

```powershell
.venv-multiuav-server/Scripts/python scripts/probe_multiuav_train_observations_v2.py --case-id 4c8040f9:canonical_execute --raw-output outputs/multiuav/train-observation-probe-v2/4c8040f9/raw_agent_observations.json --summary-output outputs/multiuav/train-observation-probe-v2/4c8040f9/summary.json
python scripts/analyze_multiuav_train_observations_v2.py --root outputs/multiuav/train-observation-probe-v2 --output outputs/evaluations/multiuav_train_observation_probe_v2/summary.json
```

The next gate is a train-only, AGENT-role observation/replanning pilot that
actually moves or searches, with strict separation between SYSTEM setup and
AGENT evidence. This probe does not clear that gate. Prospective paper claims
additionally require independent missions and adjudication; neither is
currently available.

## Bounded official-server closed-loop development probe

`scripts/probe_multiuav_train_closed_loop_v2.py` adds a deliberately scripted
AGENT loop for infrastructure testing. Each step reads `/drones`, each drone's
`/nearby/targets`, and AGENT task progress. It issues only `take_off` or
`move_to`, then observes again. It chooses a locally visible named target when
available; otherwise it takes a one-perceived-radius cardinal search step
inside the public canvas. There is no model in these two runs, no hidden target
position supplied to the policy, and no claim of instruction fidelity. The
official server can still reject a command for collision or other reasons;
such a rejection stops the loop. An AGENT request to the privileged session
data endpoint returned 403 before either loop.

Two reviewed training cases were run with four-command budgets:

| Case | Initial/final locally visible targets | Command outcomes | Official task check |
|---|---:|---|---|
| `14fd1139:canonical_execute` | 0 / 0 | 4/4 succeeded; one takeoff and three search moves | false |
| `91130026:canonical_execute` | 4 / 3 | 4/4 succeeded; one takeoff, one move toward a locally observed target, two search moves | false |

The second case's AGENT task-progress readout rose from 0% to 9%; this is not
task completion. Both runs are negative on the official task check. Their raw
AGENT responses, commands, and server replies remain in ignored local
`outputs/multiuav/train-closed-loop-v2/<source-task-id>/raw.json`. Hash-linked
sanitized summaries are kept separately. The raw responses must not be
confused with model-generated actions or with the frozen static study.

```powershell
.venv-multiuav-server/Scripts/python scripts/probe_multiuav_train_closed_loop_v2.py --case-id 14fd1139:canonical_execute --max-commands 4 --raw-output outputs/multiuav/train-closed-loop-v2/14fd1139/raw.json --summary-output outputs/multiuav/train-closed-loop-v2/14fd1139/summary.json
.venv-multiuav-server/Scripts/python scripts/probe_multiuav_train_closed_loop_v2.py --case-id 91130026:canonical_execute --max-commands 4 --raw-output outputs/multiuav/train-closed-loop-v2/91130026/raw.json --summary-output outputs/multiuav/train-closed-loop-v2/91130026/summary.json
```

`scripts/run_multiuav_train_model_loop_v2.py` is a separate, bounded 3B
follow-up. It prompts the same pinned Qwen2.5-3B-Instruct revision for one of
four high-level choices: take off, move to a target presently observed by the
chosen drone, search one cardinal direction, or stop. Deterministic code
resolves target positions only from fresh AGENT observations and search steps
only from current drone position and perceived radius. It rejects ambiguous
JSON, unknown IDs, out-of-bounds or repeated destinations, and unsupported
commands. This does **not** make the resulting flight collision-safe or
mission-correct; the official server still decides whether each command
succeeds. The model is never given reference commands or target records from
SYSTEM setup. Its raw prompts/generations and server exchanges must be retained
separately from summaries, including on failure. No model-driven result is
claimed until a GPU execution and the resulting task check are verified.

The first Nautilus model-loop job
`validation-placement-train-model-loop-3b-v2` reached an NVIDIA A10 node but
never started its container: repeated pulls of the pinned PyTorch image failed
with `context canceled` and `ImagePullBackOff`. No preflight, model load, or
UAV command occurred. Its job/pod YAML and scheduler/pull events are preserved
under the local ignored
`outputs/multiuav/train-model-loop-v2/91130026/attempt-1-local-evidence/`.
After capturing that evidence, the non-running job was removed. Attempt 2
retains the same model, source case, and command budget while excluding the
image-pull-failing node. Do not count attempt 1 as an experiment result.

Attempt 2 (`validation-placement-train-model-loop-3b-v2-a2`) completed on an
NVIDIA A10. The no-model preflight passed, the pinned 3B checkpoint loaded on
`cuda:0`, and one generation returned the high-level action `SEARCH` for a
drone still at altitude zero. The deterministic resolver rejected it with
`drone_not_airborne`; therefore **zero commands** were issued. The AGENT
privileged-data request returned 403, and the official task check was false.
This is a train-only negative model result, not a paper improvement. The raw
request, generation, and AGENT/server responses remain on the Nautilus PVC at
`/workspace/results/train-model-loop-v2/91130026/attempt-2/` and in the local
ignored matching directory. The copied raw file matches the run-summary
SHA-256. The preflight and run summaries, job/pod YAML, and logs are preserved
separately. No unexecuted model action is counted as a simulated move.

The next attempt clarifies the prompt's action availability from the current
AGENT-visible drone altitude: a grounded drone may only `TAKE_OFF` or `STOP`.
The deterministic gate remains unchanged. This is iterative development on
the same reviewed training task and must not be presented as an untouched
evaluation or a causal comparison with M1--M4.

Attempt 3 (`validation-placement-train-model-loop-3b-v2-a3`) also completed
with the pinned 3B checkpoint, but the model again chose `SEARCH` for a grounded
drone. The unchanged resolver rejected it as `drone_not_airborne`; zero
commands were issued and the task check was false. Prompting alone did not
repair this training case. The raw request/generation and complete run evidence
are retained on the PVC and locally under the attempt-3 directory, with
matching raw SHA-256. This second negative result must remain visible.

A subsequent **development** probe uses an instruction that explicitly says
"take off" (`14fd1139:canonical_execute`). A deterministic, AGENT-visible
takeoff prelude is separated in the raw trace from model calls. After the
server confirms takeoff, the model receives fresh AGENT observations and
selects the next high-level action. Any command count or task result must
separately identify that deterministic prelude; it is not an M1--M4 result,
and a model-driven planning success has not yet been shown.
Each actual command response in this probe is also appended and fsynced to a
separate `.commands.jsonl` journal before the next observation. The journal
is raw evidence and stays beside the raw model trace on the PVC; the run
summary records its SHA-256 when present.

Attempt 4 (`validation-placement-train-model-loop-3b-v2-a4`) completed on an
NVIDIA L4 for `14fd1139:canonical_execute`. Preflight passed and the pinned
3B model loaded. One deterministic takeoff prelude succeeded and was recorded
in the command journal. After fresh AGENT observation, the model made one call
and returned `STOP` with extra parameters. The strict action resolver rejected
it as `stop_has_parameters`; **no model-selected command** was issued. The
official task check was false. The run summary binds both the copied raw
model trace and the command journal by SHA-256; both hashes were verified.
Raw files remain on the PVC and in the local ignored attempt-4 directory, with
job/pod YAML and logs preserved separately. The one successful command must
not be reported as model planning success.

Across these two model-action variants on one reviewed training case plus the
explicit-takeoff probe on another, the system has not shown model-driven
search or task completion. Repeated prompt edits against these inspected
cases would be training-set tuning. The next research gate is a redesigned,
frozen action interface or constrained output mechanism tested first on
training cases and then on genuinely untouched, independently adjudicated
missions. Those missions and reviewer are not currently available. The
frozen paper's zero executable static plan-fidelity result is unchanged.

## Agent-visible option-menu follow-up

The next train-only interface replaces free-form action JSON with a fresh menu
of one-step commands derived from the current AGENT drone list, nearby-target
observations, canvas, and previously attempted destinations. Grounded drones
have only bounded takeoff options; airborne drones have bounded cardinal search
and locally observed target-move options. The model returns an `option_id` or
`STOP`; only a listed ID can resolve to a command. A missing local target alone
is not treated as insufficient mission evidence, because searching can reveal
it. `STOP` remains available for genuinely insufficient or contradictory
instructions. No hidden target coordinates, official command, or expected
decision enters the menu or prompt.

This changes the development action interface, not the registered M1--M4
study. It removes the deterministic takeoff prelude: a takeoff now counts as
model-selected only if the model selects its offered ID. The menu limits action
syntax and geometry but does not prove collision safety, instruction fidelity,
or task completion. The official server must still accept commands, and a
successful task check is required before describing mission completion.

This interface has focused unit tests. A GPU/official-server outcome is **not
evaluated** until a new immutable run records its model selection, command
journal, task check, and failed attempts. Repeated tuning on reviewed training
cases is development, not independent evaluation; the frozen paper result
remains unchanged.

The first option-menu Kubernetes attempt (`a5`) remained Pending for about ten
minutes. Its pod had no assigned node, no restarts, and no model or command
output. The scheduler reported insufficient GPU plus node affinity, taint,
CPU, and memory constraints. Job/pod YAML, pod description, and empty log are
preserved under `outputs/evaluations/multiuav_train_model_loop_v2/attempt5_pending/`.
The pending job was removed before an otherwise identical `a6` request widened
the compatible GPU allowlist to L40, L40S, and RTX A6000. This is an
infrastructure retry, not a second model observation or performance result.

Attempt `a6` never obtained a pod on an eligible GPU. Kubernetes marked the
job `Failed` with `DeadlineExceeded` after its 5,400-second active deadline;
the pod had been removed by the time of inspection. The final job YAML/JSON,
job events, and empty remaining-pod listing are preserved under
`outputs/evaluations/multiuav_train_model_loop_v2/attempt6_deadline_exceeded/`.
No model selection or server task check is available from `a6`. The option-menu
interface therefore has unit-test evidence only, not a demonstrated reduction
in false refusal or an improvement to the paper's executable-case result.

Attempt `a7` also remained Pending with no assigned node, no restarts, and no
model output. The scheduler reported insufficient GPUs and other placement
constraints; its job/pod YAML and pod description are preserved under
`outputs/evaluations/multiuav_train_model_loop_v2/attempt7_pending/`.
It was removed while still Pending before submitting `a8`, which adds compatible
RTX 4090 and V100 GPU types to the existing pool. These are scheduling retries
of the same train-only option-menu experiment, not additional model results.
Attempt `a8` likewise remained Pending without a node or model output; its
placement evidence is preserved under `attempt8_pending/`. It was retired
before `a9` added T4 and RTX 2080 Ti GPUs, which have sufficient nominal VRAM
for the pinned 3B half-precision weights but still require an actual runtime
load check. Neither pending attempt is evidence of model behavior.

The separate `cpu1` job is a one-command development smoke for the same pinned
3B model and reviewed training task. It requests no GPU. A first submission
was rejected by the admission webhook because it explicitly set
`CUDA_VISIBLE_DEVICES`; that setting was removed before a pod was created.
The existing backend still requests float16 weights, so CPU
performance and even load feasibility are unverified until the job runs. Its
distinct PVC output directory must preserve any preflight, failure, model
generation, and official-server response. It is not a paper resource condition
or an independent accuracy experiment.
The CPU pod started and installed dependencies but was stopped before preflight
or model load: the GPU `a9` pod obtained a V100 node, and the PVC could not be
mounted by both pods on different nodes. The CPU output directory was empty.
Its job/pod YAML and log are preserved under `cpu_smoke_preempted_by_gpu/`.
This is an infrastructure interruption, not a CPU inference result.

GPU attempt `a9` completed on a Tesla V100-SXM2-32GB using the pinned 3B
checkpoint and option-menu code commit `0f68a5efce8aff66be8cc711f85680a16cb51c08`.
On reviewed training case `14fd1139:canonical_execute`, the model made 12
choices; all 12 resolved to offered options and all 12 commands were accepted
by the official server (four takeoffs and eight bounded search moves). There
was no deterministic prelude. The AGENT's privileged-data request returned
403 as intended. Local target observations remained empty, task progress stayed
at 0%, and the official task check was false when the 12-command budget ended.
This shows model-driven command execution, not instruction fidelity or mission
completion. The raw generation and command journal remain in the ignored PVC
and local `outputs/multiuav/train-model-loop-v2/14fd1139/attempt-9/` paths;
both copied files match the SHA-256 values in `run_summary.json`. Job/pod YAML
and the log are preserved separately under `attempt9_complete/`.

The next train-only probe uses reviewed case `91130026:canonical_execute`,
whose initial local observations include targets. Attempt `a10` remained Pending
with no node or model output and was retired; its placement evidence is under
`attempt10_pending/`. Attempt `a11` widens the hardware allowlist to additional
compatible CUDA GPUs without changing the pinned model, option-menu policy,
decoding, or per-run output directory. No `a11` outcome is claimed here.
Attempt `a11` also remained Pending without model output; its job/pod evidence
is retained under `attempt11_pending/`. The `a12` request replaces GPU product
names with Nautilus's numeric hardware labels: more than 10,240 MiB VRAM and
CUDA compute major version 7 through 10, while keeping the known-bad host
excluded. This is a scheduling change only, and runtime compatibility remains
subject to actual model-load evidence.

Attempt `a12` completed on an NVIDIA RTX A4000 (16,376 MiB) with the same v3
option menu and pinned 3B checkpoint. On reviewed training case
`91130026:canonical_execute`, 12 model-selected commands were accepted (five
takeoffs, seven moves). Official task progress rose from 0% to 11%, but the
task check was false against the instruction's 95% coverage requirement. The
model saw nearby targets, yet v3 only offered a target-center move and cardinal
search, not a coverage path derived from the target's visible shape. Its raw
generation and command journal remain in the ignored PVC and local
`outputs/multiuav/train-model-loop-v2/91130026/attempt-12/` paths and match
the hashes in `run_summary.json`. Job/pod YAML and log are preserved under
`attempt12_complete/`. This is partial training progress, not mission success.

Option-menu v4 adds one bounded circle-sweep option only when an airborne
drone's AGENT-visible `task_radius` and a locally observed circle's center and
radius are finite and wholly within the public canvas. The model must select
the offered ID. The command uses the official `move_along_path` route with
`allow_partial_move=false`; the official server retains collision and battery
checks. No unseen target geometry, hidden reference plan, or task label is
used. Polygon coverage and discovery of non-visible targets are not solved by
this option. A later run is required before claiming any outcome for v4.

Attempt `a13` was assigned an NVIDIA A10 but stalled in the container's
HTTP Ubuntu package-index update before model preflight or inference. Its
job/pod manifests and log are retained under `attempt13_setup_blocked/`;
there is no model result from that attempt. Attempt `a14` keeps the same
reviewed training case, pinned model, code revision, and v4 option menu,
but switches Ubuntu package sources to HTTPS during startup. It uses a new
output directory so setup attempts and model results cannot be conflated.

Attempt `a14` ran v4 on a Tesla V100-SXM2-16GB. Preflight passed and the
3B model completed nine calls, with eight accepted commands. Official task
progress stayed at 0% and the task check was false. The last move conflicted
with an obstacle. Circle Target 2 was visible to an idle drone, but the model
took off other drones and chose generic search moves; no circle sweep was
offered because its observing drone never took off. The local ignored raw
files match the summary hashes; job/pod YAML and logs are preserved under
`attempt14_complete/`. This is a negative training result, not a paper result.

The v5 menu prioritizes an explicitly named target only when it appears in
the current AGENT-visible nearby-target observations. While such a target is
visible, it offers takeoff or target actions only for drones that observed it;
it does not infer unseen targets or bypass official movement checks. The
model still selects an option, and mission success remains untested for v5.

Attempt `a15` reached model execution with v5 and wrote one accepted takeoff
for the drone observing Circle Target 2. The Kubernetes job and pod were gone
when checked later, and the durable summary still says `running`; no final
raw trace or official task check was written. Its partial preflight, summary,
and command journal remain under the ignored `attempt-15/` directory. This
is an interrupted attempt, not evidence of task success. Attempt `a16`
repeats the same pinned model and v5 code in a distinct output directory.

Attempt `a16` reproduced a stall after one accepted takeoff on an RTX A4000.
Its durable summary remained `running`, the command journal had one row,
and the process showed no CPU or GPU work for over five minutes. Job/pod YAML
and logs were preserved under `attempt16_hung_after_first/`; the job was
stopped without a task-check result. A diagnostic-only follow-up writes
durable phase events before and after model selection, official command
execution, and AGENT re-observation. These events contain no model text or
hidden labels and do not alter the action policy.

Attempt `a17` reproduced the stall. Its event journal shows the first
takeoff, subsequent AGENT observation, and second model selection all
completed; the selected action was an observed-circle `move_along_path`.
No `after_command` event appeared. This localizes the stall to that official
path command in this simulator/session, not to model generation. The partial
journals and job/pod evidence were retained under `attempt-17/` and
`attempt17_path_endpoint_hung/` before stopping the job. No task-check
result exists.

The v6 train-only policy offers one circle-sweep waypoint at a time via the
official `move_to` route, retaining the same AGENT-visible geometry checks,
model-selected option ID, and bounded command budget. Earlier pilots showed
`move_to` can return in this session; whether v6 completes coverage or the
mission remains not evaluated until a separate run finishes.

Attempt `a18` completed on an RTX A4000 with v6: eight accepted official
commands (one takeoff, six observed-circle sweep steps, one target-center
move), no path-endpoint stall, and AGENT-visible task progress from 0% to
20%. The official task check was false, and the loop stopped with
`no_bounded_action`. The second named area was still not observed. Raw and
event journals were copied to the ignored `attempt-18/` directory and match
the summary SHA-256 hashes; job/pod YAML and log are in `attempt18_complete/`.
This is partial training progress, not a valid executable plan or a revised
paper result.

The v7 train-only follow-up returns to bounded search options after actions
for a visible named target are exhausted. It raises the per-case budget from
12 to 24 commands so discovery and coverage of a second area can be tested;
therefore any v7 outcome is not a like-for-like policy-only comparison with
v6. No hidden target position is used.

Attempt `a19` completed on an RTX 2080 Ti with v7. Twenty of 21 official
commands succeeded, AGENT-visible task progress rose from 0% to 30%, and
Polygon Target 3 became locally visible at step 12. The model moved to that
target's center but had no offered polygon-coverage action; later generic
search ended in an obstacle rejection. The official task check was false.
Raw and event journals in ignored `attempt-19/` match their summary hashes;
job/pod YAML and log are under `attempt19_complete/`.

The v8 train-only follow-up offers bounded individual `move_to` sweep steps
for an AGENT-observed axis-aligned rectangular polygon, using only its visible
four vertices and the observing drone's task radius. It rejects rotated,
out-of-canvas, malformed, or too-large geometry rather than guessing. The
24-command budget remains unchanged. General polygon coverage is not
implemented, and no v8 mission outcome is claimed before evaluation.

Attempt `a20` completed on node `ry-gpu-15.sdsc.optiputer.net` with the
pinned Qwen2.5-3B-Instruct revision and v8 code commit
`a405b5d16577cd0703ae83fa9c967c413000ce0a`.
All 24 model-selected official commands succeeded: two takeoffs, six
observed-circle sweep steps, eight observed-rectangle sweep steps, six
bounded searches, and two observed-target moves. The AGENT-visible aggregate
session progress ended at 41%; this is not the task-specific success metric.
The official task check returned true. A post-run audit of the reviewed
training task's source checker confirmed a four-leaf AND: each of Polygon
Target 3 and Circle Target 2 must be reached and searched to at least 95%.
The AGENT response masks this checker as null, so its masked field must not
be interpreted as an absent check. None of the 24 model user messages
contained `execution_check_apis`, `coverage_threshold`, or `related_apis`.
The raw generation, command, event, and preflight files are retained in the
ignored `outputs/multiuav/train-model-loop-v2/91130026/attempt-20/`
directory and on the PVC; the copied raw, command, and event files match the
SHA-256 hashes in `run_summary.json`. Job/pod YAML and logs are preserved
under `attempt20_complete/`.

This confirms one model-driven mission completion on a repeatedly inspected
training task. It is not independent evidence of generalization, does not
revise the frozen 0/852 static-fidelity result, and does not establish
reliability on unseen tasks or nonrectangular polygons.

The next v8 robustness probe is registered as attempt `a21` before execution:
reviewed training case `519784ca:canonical_execute`, the protocol-selected
intermediate area-search case from session `0f23ff1e`. It requires 95% search
coverage of Circle Target 2 and Circle Target 1. The run uses the same pinned
model, upstream simulator revision, v8 code commit, and 24-command limit as
`a20`, with a separate output directory. We will record the official task
check, command acceptance, AGENT-visible progress, and any failure or stall.
Only an official true task check counts as task completion; aggregate session
progress is descriptive. This train-only probe will not alter the frozen
paper results or be treated as independent held-out validation.

Attempt `a21` completed on an NVIDIA RTX A4000 with the registered v8
configuration. The official task check returned false. Of 19 model-selected
commands, 18 succeeded (two takeoffs and 16 `move_to` searches); the final
search move was rejected for a circle-obstacle conflict. All 20 AGENT
snapshots had no nearby target observations, and aggregate session progress
remained 0%. The model used one drone for a northward step followed by 16
eastward steps at one latitude; the other launched drone was not used after
takeoff. The stop reason was `command_rejected_or_failed`. This shows that
the v8 bounded local-search menu can permit ineffective, repetitive
exploration. It does not diagnose the later sweep policy, because neither
named target was discovered. The local ignored raw, command, event, and
preflight files are in `outputs/multiuav/train-model-loop-v2/519784ca/attempt-21/`;
the copied journals match the SHA-256 values in `run_summary.json`.
Job/pod YAML and logs are preserved under `attempt21_complete/`. No hidden
checker or target coordinate was used to alter this run.

The v9 train-only option menu addresses the observed straight-line search
failure by offering bounded search moves only for airborne drones with the
fewest previously selected search moves. Takeoff choices remain available,
and a named locally observed target still takes priority. The model selects
every offered action; the official server retains movement and obstacle
checks. This is a changed policy, not a controlled measurement of a single
causal factor, and it does not modify M1-M4.

Attempt `a22` is registered before execution on reviewed training case
`4cea97cd:canonical_execute`, the protocol-selected easy area-search case
from session `bad1e9e5`. It uses the same 3B checkpoint and upstream simulator
revision as `a21`, v9 code, and a 24-command budget. We will preserve the
official task check, command acceptance, aggregate session progress, and
count of distinct AGENT-observed target IDs. An official true task check is
required for task completion. The result is a train-only development probe,
not held-out evidence or an update to the frozen paper.

Attempt `a22` completed on an NVIDIA GeForce RTX 2080 Ti with v9 code
`a9aba854843e2f74fd1e27b329a612c81db5cc69`. Its only model-selected command
was rejected: the menu offered an observed-target move for Drone 3 because
its reported altitude was 76, although its AGENT-visible status was `idle`.
The official controller accepts movement only from `hovering`, `flying`, or
`moving`. Polygon Target 1 was already locally observed. Zero commands
succeeded and the official task check was false, so this attempt does not
measure search balancing. The copied raw and command/event journals match
their summary hashes and remain under ignored `attempt-22/`. The job and pod
were observed as succeeded with zero restarts on October 4, but were absent
when archival capture resumed on October 5; live YAML and full logs are
unavailable. The submitted manifest and durable summaries remain preserved.

The v10 correction makes command eligibility follow the official controller's
status rules: `idle` and `ready` offer takeoff; `hovering`, `flying`, and
`moving` offer movement; other or missing statuses offer no command. Altitude
still must be finite. The v9 search balance, geometry checks, decoding,
checkpoint, and 24-command limit remain unchanged. Regression tests cover
idle/ready with positive altitude, supported movement states at zero altitude,
unsupported statuses, and the takeoff-to-hovering observation transition.

Attempt `a23` is registered as a development retry of the same reviewed
training case `4cea97cd:canonical_execute` after the status correction. Its
completion criterion and process metrics remain those registered for `a22`.
It is not a fresh independent evaluation because the `a22` failure has been
inspected. Both attempts will be retained regardless of outcome.

Attempt `a23` completed on a Tesla V100-SXM2-16GB with v10 code
`067c229fccdbffb96d0e7d60da0b868160361266`. All 24 model-selected official
commands succeeded: three takeoffs and 21 observed-rectangle sweep steps.
Aggregate session progress rose from 0% to 47%, and two distinct polygon
targets appeared in AGENT observations. The official task check was false
when the 24-command budget ended. The positive-altitude idle drone could
take off and subsequently move, confirming the status correction on this
inspected training case. Search balancing was not exercised because no
bounded-search move was selected. Mission completion remains unestablished
on this case; a larger budget or more complete discovery policy has not been
evaluated here.

Raw output, command/event journals, preflight, summary, and durable console
log remain in ignored `outputs/multiuav/train-model-loop-v2/4cea97cd/attempt-23/`
and on the PVC. The three journal hashes match `run_summary.json`. The
`attempt23_complete/` archive preserves initial and final job/pod YAML,
console logs, summaries, and separately derived metrics with reproduction
commands. The full documented checks passed: 296 pytest tests, 17 subtests,
and Ruff. Frozen publication results remain unchanged.
