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
