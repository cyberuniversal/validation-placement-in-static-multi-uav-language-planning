# This is a fixed-policy regression on a previously inspected training mission.
# The manifest pins the same code, checkpoint and decoding as attempt a25.
# Do not reuse an existing attempt directory or overwrite the preserved evidence.
python -m pytest -q
python -m ruff check src scripts tests paper/build_resource_figure.py
kubectl apply -f infra/nautilus/train-model-loop-3b-v2-a26-job.yaml
kubectl get pods -n aiea-interns -l job-name=validation-placement-train-model-loop-3b-v2-a26 -o wide
kubectl logs -n aiea-interns job/validation-placement-train-model-loop-3b-v2-a26

# Exact invocation inside the pinned execution checkout:
# python scripts/run_multiuav_train_model_loop_v2.py `
#   --case-id 519784ca:canonical_execute --max-commands 512 `
#   --cache-audit /workspace/artifacts/qwen25_3b_cache_audit_nautilus_v1.json `
#   --cache-dir /workspace/hf-cache `
#   --raw-output /workspace/results/train-model-loop-v2/519784ca/attempt-26/raw.json `
#   --summary-output /workspace/results/train-model-loop-v2/519784ca/attempt-26/run_summary.json
