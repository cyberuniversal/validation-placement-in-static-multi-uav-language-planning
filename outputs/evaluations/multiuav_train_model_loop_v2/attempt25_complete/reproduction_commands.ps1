# Run from the publication repository, using its existing Nautilus credentials.
# This manifest pins code, upstream simulator, model revision, seed and decoding.
# Do not overwrite an existing attempt directory or resubmit a completed run.
python -m pytest -q
python -m ruff check src scripts tests paper/build_resource_figure.py
kubectl apply -f infra/nautilus/train-model-loop-3b-v2-a25-job.yaml
kubectl get pods -n aiea-interns -l job-name=validation-placement-train-model-loop-3b-v2-a25 -o wide
kubectl logs -n aiea-interns job/validation-placement-train-model-loop-3b-v2-a25

# The exact model invocation, executed inside the manifest's pinned checkout:
# python scripts/run_multiuav_train_model_loop_v2.py `
#   --case-id 4cea97cd:canonical_execute --max-commands 512 `
#   --cache-audit /workspace/artifacts/qwen25_3b_cache_audit_nautilus_v1.json `
#   --cache-dir /workspace/hf-cache `
#   --raw-output /workspace/results/train-model-loop-v2/4cea97cd/attempt-25/raw.json `
#   --summary-output /workspace/results/train-model-loop-v2/4cea97cd/attempt-25/run_summary.json

# navigation_diagnostics.json is derived from two separate scripted integration
# traces. Their backend always returned {"option_id":"O1"}; no LLM was loaded.
# Both used reviewed case 4cea97cd, official session restoration through
# session_payload(), and run_case(..., max_commands=512,
# choose_action=ModelActionSelector(FirstOption()),
# on_observation=selector.observe). They are not Qwen evaluation results.
# The first diagnostic used the uncommitted pre-ellipse implementation;
# it is retained as debugging evidence, not an immutable research experiment.
