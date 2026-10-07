from contextlib import nullcontext
import json
from pathlib import Path
import socket
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from shepherd_ai.multiuav_model_revisions import (  # noqa: E402
    REGISTERED_MODEL_REVISIONS,
)
from shepherd_ai.multiuav_context import (  # noqa: E402
    project_agent_visible_context,
)
from shepherd_ai.multiuav_offline_runtime import (  # noqa: E402
    NetworkIsolationError,
)
from shepherd_ai.multiuav_prompts import (  # noqa: E402
    build_first_call_request,
)
from shepherd_ai.multiuav_qwen_backend import (  # noqa: E402
    LocalQwenBackend,
    QwenBackendConfig,
)
from shepherd_ai.multiuav_runner import run_method_case  # noqa: E402
from scripts.run_multiuav_train_model_loop_v2 import BoundedLocalQwenBackend  # noqa: E402


class _FakeTensor:
    def __init__(self, values):
        self.values = list(values)
        self.shape = (1, len(self.values))
        self.device = None

    def to(self, device):
        self.device = device
        return self


class _FakeTokenizer:
    eos_token_id = 2
    pad_token_id = None

    def __init__(self) -> None:
        self.messages = None
        self.template_kwargs = None

    def apply_chat_template(self, messages, **kwargs):
        self.messages = messages
        self.template_kwargs = kwargs
        self.input_ids = _FakeTensor([10, 11, 12])
        return {"input_ids": self.input_ids}

    def decode(self, tokens, **kwargs):
        self.decoded_tokens = list(tokens)
        self.decode_kwargs = kwargs
        return json.dumps(
            {
                "decision": "BLOCK",
                "reason": "Synthetic fixture output.",
                "clarification_question": None,
                "api_plan": [],
            }
        )


class _FakeModel:
    device = "cuda:0"

    def __init__(self) -> None:
        self.eval_called = False
        self.generate_kwargs = None

    def eval(self):
        self.eval_called = True
        return self

    def generate(self, **kwargs):
        self.generate_kwargs = kwargs
        with self.assert_isolated():
            pass
        return [[10, 11, 12, 90, 91]]

    @staticmethod
    def assert_isolated():
        class _IsolationCheck:
            def __enter__(self):
                try:
                    socket.getaddrinfo("example.com", 443)
                except NetworkIsolationError:
                    return self
                raise AssertionError("generation was not network isolated")

            def __exit__(self, exc_type, exc, traceback):
                return False

        return _IsolationCheck()


class _FakeCuda:
    def __init__(self) -> None:
        self.synchronize_calls = 0

    def is_available(self):
        return True

    def synchronize(self):
        self.synchronize_calls += 1


class _FakeTorch:
    __version__ = "2.fake"
    float16 = "float16"
    bfloat16 = "bfloat16"
    float32 = "float32"

    def __init__(self) -> None:
        self.cuda = _FakeCuda()

    @staticmethod
    def inference_mode():
        return nullcontext()


class _Loader:
    def __init__(self, value) -> None:
        self.value = value
        self.calls = []

    def from_pretrained(self, model_id, **kwargs):
        try:
            socket.getaddrinfo("example.com", 443)
        except NetworkIsolationError:
            isolated = True
        else:
            isolated = False
        self.calls.append((model_id, dict(kwargs), isolated))
        return self.value


class _FakeTransformers:
    __version__ = "4.fake"

    def __init__(self, tokenizer, model) -> None:
        self.AutoTokenizer = _Loader(tokenizer)
        self.AutoModelForCausalLM = _Loader(model)


def _context():
    return project_agent_visible_context(
        {
            "id": "session-1",
            "task_type": "return",
            "canvas_width": 100,
            "canvas_height": 100,
            "is_distance_3d": True,
            "status": "active",
            "drones": [
                {
                    "id": "drone-1",
                    "name": "Drone 1",
                    "status": "idle",
                    "position": {"x": 0, "y": 0, "z": 0},
                    "heading": 0,
                    "max_altitude": 50,
                }
            ],
            "environment": {},
        },
        task_id="synthetic-task",
        instruction="Return safely.",
    )


def _request():
    return build_first_call_request("M1_monolithic", _context())


class MultiUavQwenBackendTests(unittest.TestCase):
    def test_input_budget_rejects_before_device_transfer_or_generation(self) -> None:
        registered = REGISTERED_MODEL_REVISIONS[0]
        tokenizer, model = _FakeTokenizer(), _FakeModel()
        backend = BoundedLocalQwenBackend(
            config=QwenBackendConfig(model_id=registered.model_id,
                                    revision=registered.revision, max_new_tokens=16,
                                    dtype="float16"),
            tokenizer=tokenizer, model=model,
            transformers_module=_FakeTransformers(tokenizer, model),
            torch_module=_FakeTorch(), max_input_tokens=2,
        )
        with self.assertRaisesRegex(ValueError, "input token budget"):
            backend.generate(_request())
        self.assertIsNone(model.generate_kwargs)
        self.assertIsNone(backend._tokenizer.input_ids.device)

    def test_input_budget_allows_boundary_and_records_limit(self) -> None:
        registered = REGISTERED_MODEL_REVISIONS[0]
        backend = BoundedLocalQwenBackend(
            config=QwenBackendConfig(model_id=registered.model_id,
                                    revision=registered.revision, max_new_tokens=16,
                                    dtype="float16"),
            tokenizer=_FakeTokenizer(), model=_FakeModel(), max_input_tokens=3,
            transformers_module=_FakeTransformers(_FakeTokenizer(), _FakeModel()),
            torch_module=_FakeTorch(),
        )
        self.assertEqual(backend.generate(_request()).metadata["max_input_tokens"], 3)
        self.assertNotIn("max_input_tokens", backend._model.generate_kwargs)

    def test_input_budget_rejects_invalid_limits(self) -> None:
        registered = REGISTERED_MODEL_REVISIONS[0]
        for limit in (0, -1, True, 2.5):
            with self.subTest(limit=limit), self.assertRaises(ValueError):
                BoundedLocalQwenBackend(
                    config=QwenBackendConfig(model_id=registered.model_id,
                                            revision=registered.revision, max_new_tokens=16,
                                            dtype="float16"),
                    tokenizer=_FakeTokenizer(), model=_FakeModel(),
                    transformers_module=_FakeTransformers(_FakeTokenizer(), _FakeModel()),
                    torch_module=_FakeTorch(), max_input_tokens=limit,
                )

    def test_cached_loader_can_use_verified_local_snapshot_path(self) -> None:
        model_revision = REGISTERED_MODEL_REVISIONS[0]
        with tempfile.TemporaryDirectory() as temp_dir:
            cache = Path(temp_dir) / "cache"
            snapshot = cache / "snapshots" / model_revision.revision
            snapshot.mkdir(parents=True)
            fake_torch = _FakeTorch()
            fake_transformers = _FakeTransformers(
                _FakeTokenizer(),
                _FakeModel(),
            )
            config = QwenBackendConfig(
                model_id=model_revision.model_id,
                revision=model_revision.revision,
                max_new_tokens=16,
                dtype="float16",
                cache_dir=str(cache),
                snapshot_dir=str(snapshot),
            )

            LocalQwenBackend.from_cached(
                config,
                transformers_module=fake_transformers,
                torch_module=fake_torch,
            )

            tokenizer_call = fake_transformers.AutoTokenizer.calls[0]
            model_call = fake_transformers.AutoModelForCausalLM.calls[0]
            self.assertEqual(Path(tokenizer_call[0]), snapshot.resolve())
            self.assertEqual(Path(model_call[0]), snapshot.resolve())
            self.assertNotIn("revision", tokenizer_call[1])
            self.assertTrue(tokenizer_call[1]["local_files_only"])

    def test_cached_loader_records_external_disk_offload_configuration(self) -> None:
        model_revision = REGISTERED_MODEL_REVISIONS[1]
        with tempfile.TemporaryDirectory() as temp_dir:
            cache = Path(temp_dir) / "cache"
            snapshot = cache / "snapshots" / model_revision.revision
            snapshot.mkdir(parents=True)
            offload_folder = Path(temp_dir) / "offload"
            offload_folder.mkdir()
            transformers = _FakeTransformers(_FakeTokenizer(), _FakeModel())
            config = QwenBackendConfig(
                model_id=model_revision.model_id,
                revision=model_revision.revision,
                max_new_tokens=1,
                dtype="float16",
                cache_dir=str(cache),
                snapshot_dir=str(snapshot),
                offload_folder=str(offload_folder),
            )

            backend = LocalQwenBackend.from_cached(
                config,
                transformers_module=transformers,
                torch_module=_FakeTorch(),
            )

            model_kwargs = transformers.AutoModelForCausalLM.calls[0][1]
            self.assertEqual(model_kwargs["offload_folder"], str(offload_folder))
            self.assertTrue(model_kwargs["offload_state_dict"])
            result = backend.generate(_request())
            self.assertEqual(
                result.metadata["offload_folder"],
                str(offload_folder),
            )

    def test_config_rejects_missing_offload_folder(self) -> None:
        registered = REGISTERED_MODEL_REVISIONS[0]
        with tempfile.TemporaryDirectory() as temp_dir:
            missing = Path(temp_dir) / "missing"
            with self.assertRaisesRegex(ValueError, "existing directory"):
                QwenBackendConfig(
                    model_id=registered.model_id,
                    revision=registered.revision,
                    max_new_tokens=1,
                    dtype="float16",
                    offload_folder=str(missing),
                ).validate()

    def test_config_rejects_unregistered_revision(self) -> None:
        registered = REGISTERED_MODEL_REVISIONS[0]

        with self.assertRaisesRegex(ValueError, "frozen registry"):
            QwenBackendConfig(
                model_id=registered.model_id,
                revision="0" * 40,
                max_new_tokens=128,
                dtype="float16",
            ).validate()

    def test_cached_loader_forces_pinned_local_only_configuration(self) -> None:
        registered = REGISTERED_MODEL_REVISIONS[0]
        tokenizer = _FakeTokenizer()
        model = _FakeModel()
        transformers = _FakeTransformers(tokenizer, model)
        torch = _FakeTorch()
        config = QwenBackendConfig(
            model_id=registered.model_id,
            revision=registered.revision,
            max_new_tokens=128,
            dtype="float16",
            cache_dir="C:/synthetic-cache",
        )

        backend = LocalQwenBackend.from_cached(
            config,
            transformers_module=transformers,
            torch_module=torch,
        )

        self.assertTrue(model.eval_called)
        for loader in (
            transformers.AutoTokenizer,
            transformers.AutoModelForCausalLM,
        ):
            self.assertEqual(len(loader.calls), 1)
            model_id, kwargs, isolated = loader.calls[0]
            self.assertEqual(model_id, registered.model_id)
            self.assertEqual(kwargs["revision"], registered.revision)
            self.assertTrue(kwargs["local_files_only"])
            self.assertFalse(kwargs["trust_remote_code"])
            self.assertTrue(isolated)
        self.assertEqual(
            transformers.AutoModelForCausalLM.calls[0][1]["dtype"],
            torch.float16,
        )
        self.assertTrue(
            transformers.AutoModelForCausalLM.calls[0][1]["use_safetensors"]
        )
        self.assertEqual(backend.config, config)

    def test_generation_is_greedy_isolated_and_records_metadata(self) -> None:
        registered = REGISTERED_MODEL_REVISIONS[0]
        tokenizer = _FakeTokenizer()
        model = _FakeModel()
        transformers = _FakeTransformers(tokenizer, model)
        torch = _FakeTorch()
        backend = LocalQwenBackend.from_cached(
            QwenBackendConfig(
                model_id=registered.model_id,
                revision=registered.revision,
                max_new_tokens=128,
                dtype="float16",
            ),
            transformers_module=transformers,
            torch_module=torch,
        )

        result = backend.generate(_request())

        self.assertEqual(result.generation_status, "GENERATED")
        self.assertEqual(result.input_tokens, 3)
        self.assertEqual(result.output_tokens, 2)
        self.assertEqual(tokenizer.decoded_tokens, [90, 91])
        self.assertTrue(tokenizer.template_kwargs["tokenize"])
        self.assertTrue(tokenizer.template_kwargs["add_generation_prompt"])
        self.assertTrue(tokenizer.template_kwargs["return_dict"])
        self.assertEqual(tokenizer.template_kwargs["return_tensors"], "pt")
        self.assertFalse(model.generate_kwargs["do_sample"])
        self.assertEqual(model.generate_kwargs["num_beams"], 1)
        self.assertEqual(model.generate_kwargs["max_new_tokens"], 128)
        self.assertEqual(model.generate_kwargs["pad_token_id"], 2)
        self.assertEqual(result.metadata["model_id"], registered.model_id)
        self.assertEqual(result.metadata["model_revision"], registered.revision)
        self.assertTrue(result.metadata["local_files_only"])
        self.assertTrue(result.metadata["non_loopback_sockets_blocked"])
        self.assertEqual(result.metadata["transformers_version"], "4.fake")
        self.assertEqual(result.metadata["torch_version"], "2.fake")
        self.assertGreaterEqual(result.latency_ms, 0)
        self.assertEqual(torch.cuda.synchronize_calls, 2)

    def test_backend_runs_through_provider_independent_method_runner(self) -> None:
        registered = REGISTERED_MODEL_REVISIONS[0]
        backend = LocalQwenBackend.from_cached(
            QwenBackendConfig(
                model_id=registered.model_id,
                revision=registered.revision,
                max_new_tokens=128,
                dtype="float16",
            ),
            transformers_module=_FakeTransformers(
                _FakeTokenizer(),
                _FakeModel(),
            ),
            torch_module=_FakeTorch(),
        )

        result = run_method_case(
            case_id="synthetic-case",
            case_status="synthetic_unit_fixture",
            method_id="M1_monolithic",
            context=_context(),
            backend=backend,
        )

        self.assertEqual(result.actual_model_call_count, 1)
        self.assertEqual(result.final_parse["parse_status"], "PARSED")
        self.assertEqual(result.final_parse["parsed"]["decision"], "BLOCK")


if __name__ == "__main__":
    unittest.main()
