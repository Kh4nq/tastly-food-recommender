"""Local inference contract tests: fake SDKs only, no weights or network."""
from contextlib import nullcontext
import json
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from common.schemas import PreferenceUpdate, UserRequest
from conversation.config import ConversationConfig
from conversation.providers.mock import MockProvider
from conversation.rule_parser import parse_by_rules_detailed
from conversation.service import process_user_request
from conversation.slm.base import SLMInput
from conversation.slm.qwen_lora import QwenLoRAProvider, TRAINING_INSTRUCTION, build_input_text, parse_response
from conversation.slm.router import _qwen_provider, create_slm_provider


def request():
    return SLMInput(message="view đẹp", rule_result=parse_by_rules_detailed("view đẹp"))


@pytest.fixture
def runtime(monkeypatch, tmp_path):
    adapter = tmp_path / "adapter"
    adapter.mkdir()
    (adapter / "adapter_config.json").write_text("{}")
    update = PreferenceUpdate(add_semantic_preferences=["quán đẹp"])
    tokenizer = Mock()
    tokenizer.eos_token_id = 99
    tokenizer.decode.return_value = update.model_dump_json()
    tokenizer.apply_chat_template.return_value = "formatted prompt"

    class Inputs(dict):
        def to(self, device):
            assert str(device) in {"cuda:0", "cpu"}
            return self

    tokenizer.return_value = Inputs(input_ids=SimpleNamespace(shape=(1, 3)), attention_mask=[1, 1, 1])
    model = Mock()
    model.get_input_embeddings.return_value = SimpleNamespace(weight=SimpleNamespace(device="cuda:0"))
    model.generate.return_value = [[10, 20, 30, 40, 50, 99]]
    base = Mock()

    class Linear4bit:
        def __init__(self):
            self.weight = SimpleNamespace(bnb_quantized=True, quant_state=object())

    def place(target, device, *, adapter=False):
        target.is_loaded_in_4bit = True
        target.modules.return_value = [Linear4bit()]
        target.named_parameters.return_value = [("model.weight", SimpleNamespace(device=device))]
        if adapter:
            target.named_parameters.return_value.append(("model.lora_A.default.weight", SimpleNamespace(device=device)))
        target.named_buffers.return_value = []
        target.get_input_embeddings.return_value = SimpleNamespace(weight=SimpleNamespace(device=device))

    place(base, "cuda:0")
    place(model, "cuda:0", adapter=True)
    loader, token_loader, peft_loader = Mock(return_value=base), Mock(return_value=tokenizer), Mock(return_value=model)
    class OutOfMemoryError(RuntimeError):
        pass

    torch = SimpleNamespace(inference_mode=nullcontext, float16="float16", cuda=SimpleNamespace(
        is_available=Mock(return_value=True), current_device=Mock(return_value=0),
        empty_cache=Mock(), OutOfMemoryError=OutOfMemoryError))
    quant_config = Mock(side_effect=lambda **kwargs: SimpleNamespace(**kwargs))
    monkeypatch.setitem(sys.modules, "torch", torch)
    monkeypatch.setitem(sys.modules, "bitsandbytes.nn", SimpleNamespace(Linear4bit=Linear4bit))
    monkeypatch.setitem(sys.modules, "transformers", SimpleNamespace(
        AutoModelForCausalLM=SimpleNamespace(from_pretrained=loader),
        AutoTokenizer=SimpleNamespace(from_pretrained=token_loader), BitsAndBytesConfig=quant_config))
    monkeypatch.setitem(sys.modules, "peft", SimpleNamespace(PeftModel=SimpleNamespace(from_pretrained=peft_loader)))
    _qwen_provider.cache_clear()
    yield SimpleNamespace(adapter=str(adapter), tokenizer=tokenizer, model=model,
                          loader=loader, token_loader=token_loader, peft_loader=peft_loader,
                          base=base, torch=torch, quant_config=quant_config, place=place)
    _qwen_provider.cache_clear()


def config(runtime, **kwargs):
    return ConversationConfig(local_slm_enabled=True, local_slm_adapter_path=runtime.adapter, **kwargs)


def test_training_input_format():
    data = request()
    expected = json.dumps(data.model_dump(mode="json"), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    assert build_input_text(data) == TRAINING_INSTRUCTION + "\n" + expected
    assert list(json.loads(expected)) == ["current_state", "message", "previous_results", "rule_result"]
    assert "view đẹp" in build_input_text(data)
    assert TRAINING_INSTRUCTION == "Trích xuất PreferenceUpdate v0.2 cho AI2 Food Recommender. Chỉ trả về một JSON object hợp lệ, không giải thích."


def test_valid_json_lazy_loading_reuse_and_generated_tokens_only(runtime):
    provider = create_slm_provider(config(runtime))
    runtime.loader.assert_not_called()
    runtime.token_loader.assert_not_called()
    runtime.quant_config.assert_not_called()
    runtime.peft_loader.assert_not_called()
    assert create_slm_provider(config(runtime)) is provider
    for _ in range(2):
        result = provider.parse(request())
        assert not result.should_fallback
        assert result.update.add_semantic_preferences == ["quán đẹp"]  # normalization belongs to parser
        assert result.metadata["confidence_basis"] == "structural_validation_only"
    runtime.loader.assert_called_once()
    runtime.token_loader.assert_called_once()
    runtime.peft_loader.assert_called_once()
    runtime.model.eval.assert_called_once()
    runtime.tokenizer.apply_chat_template.assert_called_with(
        [{"role": "user", "content": build_input_text(request())}], tokenize=False,
        add_generation_prompt=True, enable_thinking=False,
    )
    runtime.tokenizer.assert_called_with("formatted prompt", return_tensors="pt", add_special_tokens=False)
    runtime.tokenizer.decode.assert_called_with([40, 50, 99], skip_special_tokens=True)
    options = runtime.model.generate.call_args.kwargs
    assert options["do_sample"] is False and options["num_beams"] == 1
    assert options["max_new_tokens"] == 512
    assert runtime.token_loader.call_args.kwargs["local_files_only"] is True
    assert runtime.peft_loader.call_args.kwargs["is_trainable"] is False


def test_nf4_config_explicit_gpu_placement_and_materialization_order(runtime):
    provider = create_slm_provider(config(runtime))

    def attach(base, path, **kwargs):
        assert base is runtime.base
        runtime.base.named_parameters.assert_called_once()
        assert kwargs["low_cpu_mem_usage"] is False
        assert kwargs["autocast_adapter_dtype"] is False
        assert kwargs["device_map"] == {"": "cuda:0"}
        assert kwargs["torch_device"] == "cuda:0"
        return runtime.model

    runtime.peft_loader.side_effect = attach
    assert not provider.parse(request()).should_fallback
    runtime.quant_config.assert_called_once_with(
        load_in_4bit=True, bnb_4bit_quant_type="nf4",
        bnb_4bit_use_double_quant=True, bnb_4bit_compute_dtype=runtime.torch.float16)
    options = runtime.loader.call_args.kwargs
    assert options["device_map"] == {"": "cuda:0"}
    assert options["torch_dtype"] == runtime.torch.float16
    assert options["quantization_config"].bnb_4bit_quant_type == "nf4"
    assert options["local_files_only"] is True
    assert provider.load_summary == {
        "strategy": "cuda_nf4", "is_loaded_in_4bit": True,
        "quantized_linear_layers": 1, "parameter_devices": {"cuda:0": 2},
        "lora_parameter_devices": {"cuda:0": 1}, "meta_parameters": 0,
    }


def test_cuda_required_before_loading(runtime):
    runtime.torch.cuda.is_available.return_value = False
    provider = create_slm_provider(config(runtime))
    assert provider.parse(request()).metadata["error"] == "load_failed"
    assert "torch.cuda.is_available()" in provider.last_load_error
    runtime.loader.assert_not_called()
    runtime.peft_loader.assert_not_called()


def test_pinned_adapter_revision_and_explicit_download_flag(runtime):
    from pathlib import Path
    (Path(runtime.adapter) / "adapter_config.json").write_text('{"revision":"pinned-commit"}')
    provider = create_slm_provider(config(runtime, local_slm_local_files_only=False))
    assert not provider.parse(request()).should_fallback
    assert runtime.loader.call_args.kwargs["revision"] == "pinned-commit"
    assert runtime.loader.call_args.kwargs["local_files_only"] is False


@pytest.mark.parametrize("stage", ["base", "adapter"])
def test_meta_weights_rejected_without_caching_or_generation(runtime, stage):
    target = runtime.base if stage == "base" else runtime.model
    name = "model.weight" if stage == "base" else "model.lora_A.default.weight"
    target.named_parameters.return_value = [(name, SimpleNamespace(device="meta"))]
    provider = create_slm_provider(config(runtime))
    result = provider.parse(request())
    assert result.should_fallback and result.metadata["error"] == "load_failed"
    assert name in provider.last_load_error and "on meta" in provider.last_load_error
    assert provider._model is provider._tokenizer is None
    assert provider.load_summary is None
    runtime.model.generate.assert_not_called()
    assert runtime.loader.call_count == 1  # Only OOM permits CPU retry.
    if stage == "base":
        runtime.peft_loader.assert_not_called()


@pytest.mark.parametrize("defect", ["flag", "no_linear", "unquantized", "no_quant_state", "cpu", "buffer"])
def test_invalid_base_rejected_before_adapter(runtime, defect):
    if defect == "flag":
        runtime.base.is_loaded_in_4bit = False
    elif defect == "no_linear":
        runtime.base.modules.return_value = []
    elif defect == "unquantized":
        runtime.base.modules.return_value[0].weight.bnb_quantized = False
    elif defect == "no_quant_state":
        runtime.base.modules.return_value[0].weight.quant_state = None
    elif defect == "cpu":
        runtime.base.named_parameters.return_value[0][1].device = "cpu"
    else:
        runtime.base.named_buffers.return_value = [("buffer", SimpleNamespace(device="meta"))]
    provider = create_slm_provider(config(runtime))
    assert provider.parse(request()).metadata["error"] == "load_failed"
    runtime.peft_loader.assert_not_called()


def test_missing_lora_rejected(runtime):
    runtime.model.named_parameters.return_value = runtime.base.named_parameters.return_value
    provider = create_slm_provider(config(runtime))
    assert provider.parse(request()).should_fallback
    assert "No materialized LoRA" in provider.last_load_error


@pytest.mark.parametrize("stage", ["base", "adapter"])
def test_cuda_oom_retries_materialized_cpu_nf4_and_reuses_model(runtime, stage, caplog):
    events = []
    oom = runtime.torch.cuda.OutOfMemoryError

    def load(*args, **kwargs):
        device = kwargs["device_map"][""]
        events.append(("base", device))
        if stage == "base" and device == "cuda:0":
            raise oom("GPU exhausted during base load")
        runtime.place(runtime.base, device)
        return runtime.base

    def attach(*args, **kwargs):
        device = kwargs["torch_device"]
        assert kwargs["device_map"] == {"": device}
        assert kwargs["low_cpu_mem_usage"] is False
        events.append(("adapter", device))
        if stage == "adapter" and device == "cuda:0":
            raise oom("GPU exhausted during adapter load")
        runtime.place(runtime.model, device, adapter=True)
        return runtime.model

    runtime.loader.side_effect = load
    runtime.peft_loader.side_effect = attach
    provider = create_slm_provider(config(runtime))
    for _ in range(2):
        assert not provider.parse(request()).should_fallback
    assert events[-2:] == [("base", "cpu"), ("adapter", "cpu")]
    assert runtime.loader.call_count == 2
    assert runtime.peft_loader.call_count == (1 if stage == "base" else 2)
    runtime.token_loader.assert_called_once()
    runtime.torch.cuda.empty_cache.assert_called_once()
    assert "retrying full CPU NF4" in caplog.text
    assert provider.load_summary["strategy"] == "cpu_nf4_fallback"
    assert provider.load_summary["lora_parameter_devices"] == {"cpu": 1}
    assert provider.last_load_error is None
    assert "GPU exhausted" in provider.last_gpu_load_error
    assert all(c.kwargs["quantization_config"].load_in_4bit for c in runtime.loader.call_args_list)


@pytest.mark.parametrize("failure", ["backend", "meta"])
def test_cpu_retry_failure_preserves_diagnostics_and_external_fallback(runtime, failure):
    oom = runtime.torch.cuda.OutOfMemoryError("GPU exhausted")
    if failure == "backend":
        runtime.loader.side_effect = [oom, RuntimeError("CPU NF4 backend unavailable")]
    else:
        runtime.place(runtime.base, "cpu")
        runtime.place(runtime.model, "cpu", adapter=True)
        runtime.model.named_parameters.return_value[-1][1].device = "meta"
        runtime.loader.side_effect = [oom, runtime.base]
    provider = create_slm_provider(config(runtime))
    external = MockProvider()
    result = process_user_request(UserRequest(session_id="S", message="view đẹp"),
                                  external, config=config(runtime), slm_provider=provider)
    assert result.metadata.slm_fallback and external.call_count == 1
    assert "GPU exhausted" in provider.last_gpu_load_error
    assert ("CPU NF4 backend unavailable" if failure == "backend" else "LoRA parameter on meta") in provider.last_load_error
    assert provider._model is None
    runtime.model.generate.assert_not_called()


def test_load_error_chain_is_available_only_in_explicit_diagnostics(runtime):
    def fail(*args, **kwargs):
        try:
            raise ValueError("internal cause")
        except ValueError as error:
            raise RuntimeError("private load detail") from error

    runtime.loader.side_effect = fail
    provider = create_slm_provider(config(runtime))
    result = provider.parse(request())
    assert result.metadata == {"error": "load_failed"}
    assert "ValueError: internal cause" in provider.last_load_error
    assert "RuntimeError: private load detail" in provider.last_load_error
    assert "private load detail" not in result.model_dump_json()
    assert runtime.loader.call_count == 1
    runtime.loader.side_effect = None
    assert not provider.parse(request()).should_fallback
    assert provider.last_load_error is None


@pytest.mark.parametrize("text", ["broken", "{}", "[]", "{} {}", "```json\n{}\n```",
    '{"set_values":{},"set_values":{}}', '{"add_hard_constraints":{"budget_max":NaN}}'])
def test_malformed_json_fallback(runtime, text):
    runtime.tokenizer.decode.return_value = text
    result = create_slm_provider(config(runtime)).parse(request())
    assert result.should_fallback and result.confidence == 0
    assert result.metadata["error"] == "invalid_json_or_schema"


@pytest.mark.parametrize("stage", ["load", "generate"])
def test_runtime_exception_fallback(runtime, stage):
    target = runtime.loader if stage == "load" else runtime.model.generate
    target.side_effect = RuntimeError("private exception")
    result = create_slm_provider(config(runtime)).parse(request())
    assert result.should_fallback and result.confidence == 0
    assert "private" not in result.model_dump_json()


def test_disabled_slm_never_loads(runtime):
    disabled = ConversationConfig(local_slm_adapter_path=runtime.adapter)
    assert create_slm_provider(disabled).parse(request()).should_fallback
    result = process_user_request(UserRequest(session_id="S", message="view đẹp"),
                                  MockProvider(), config=disabled)
    assert not result.metadata.slm_called
    runtime.loader.assert_not_called()


def test_rule_bypass(runtime):
    result = process_user_request(UserRequest(session_id="S", message="ramen"),
                                  config=config(runtime))
    assert result.metadata.parser_used == "rule"
    runtime.loader.assert_not_called()


@pytest.mark.parametrize("injected", [False, True])
def test_unresolved_routes_and_normalizes(runtime, injected):
    settings = config(runtime)
    provider = create_slm_provider(settings) if injected else None
    external = MockProvider()
    result = process_user_request(UserRequest(session_id="S", message="view đẹp dưới 50k"),
                                  external, config=settings, slm_provider=provider)
    assert result.metadata.parser_used == "hybrid_slm"
    assert result.state.semantic_preferences == ["beautiful ambience"]
    assert result.state.hard_constraints["budget_max"] == 50000
    assert external.call_count == 0


def test_invalid_output_retains_external_fallback(runtime):
    runtime.tokenizer.decode.return_value = "not JSON"
    external = MockProvider(callback=lambda **_: PreferenceUpdate(add_semantic_preferences=["quiet"]))
    result = process_user_request(UserRequest(session_id="S", message="view đẹp"),
                                  external, config=config(runtime))
    assert result.metadata.slm_fallback and external.call_count == 1
    assert result.state.semantic_preferences == ["quiet"]


def test_trial_state_validation_retains_fallback(runtime):
    payload = PreferenceUpdate().model_dump()
    payload["set_values"] = {"food": 123}
    runtime.tokenizer.decode.return_value = json.dumps(payload)
    external = MockProvider()
    result = process_user_request(UserRequest(session_id="S", message="view đẹp"),
                                  external, config=config(runtime))
    assert result.metadata.slm_fallback and external.call_count == 1
    assert result.state.food == []


def test_stricter_confidence_threshold_routes_externally(runtime):
    external = MockProvider()
    result = process_user_request(UserRequest(session_id="S", message="view đẹp"),
        external, config=config(runtime, local_slm_min_confidence=0.9))
    assert result.metadata.slm_fallback and external.call_count == 1


@pytest.mark.parametrize("replacement", ['"budget_max":NaN', '"budget_max":100,"budget_max":200'])
def test_json_rejects_ambiguous_or_nonfinite_values(replacement):
    text = PreferenceUpdate(add_hard_constraints={"budget_max": 100}).model_dump_json()
    with pytest.raises(ValueError):
        parse_response(text.replace('"budget_max":100', replacement))


def test_dry_run_forces_slm_off(runtime, monkeypatch):
    from pathlib import Path
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    from ai2_tools import run_case
    monkeypatch.setattr("conversation.slm.router.create_slm_provider", Mock(side_effect=AssertionError))
    sample = {"id": "local", "category": "semantic", "message": "view đẹp", "expected": {},
              "current_state": {}, "previous_results": []}
    result = run_case(sample, None, config(runtime), dry_run=True)
    assert not result["result"]["metadata"]["slm_called"]
    runtime.loader.assert_not_called()


def test_config_environment(monkeypatch):
    monkeypatch.setenv("LOCAL_SLM_BASE_MODEL", "local/base")
    monkeypatch.setenv("LOCAL_SLM_ADAPTER_PATH", "local/adapter")
    monkeypatch.setenv("LOCAL_SLM_MAX_NEW_TOKENS", "256")
    settings = ConversationConfig.from_env()
    assert settings.local_slm_base_model == "local/base"
    assert settings.local_slm_adapter_path == "local/adapter"
    assert settings.local_slm_max_new_tokens == 256


def test_smoke_opt_in_and_mocked_output(runtime, monkeypatch, capsys):
    from pathlib import Path
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    import local_slm_smoke_test as smoke
    with pytest.raises(SystemExit) as error:
        smoke.main([])
    assert error.value.code == 2
    runtime.loader.assert_not_called()
    assert smoke.main(["--run", "--case", "semantic", "--adapter-path", runtime.adapter]) == 0
    output = capsys.readouterr().out
    for label in ("INPUT", "STATE", "PREVIOUS RESULTS", "RAW SLM UPDATE",
                  "NORMALIZED UPDATE", "UPDATED STATE", "SLM LOAD PLACEMENT", "cuda_nf4"):
        assert label in output


def test_smoke_prints_real_load_failure(runtime, monkeypatch, capsys):
    from pathlib import Path
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    import local_slm_smoke_test as smoke
    runtime.loader.side_effect = RuntimeError("diagnostic detail")
    assert smoke.main(["--run", "--case", "food", "--adapter-path", runtime.adapter]) == 1
    output = capsys.readouterr().out
    assert "SLM LOAD ERROR" in output and "RuntimeError: diagnostic detail" in output
    assert "load_failed" in output and "<no generated response>" in output


@pytest.mark.parametrize("limit", [0, -1, 4097, True])
def test_generation_limit_validation(limit):
    with pytest.raises(ValueError):
        ConversationConfig(local_slm_max_new_tokens=limit)
    with pytest.raises(ValueError):
        QwenLoRAProvider("base", "adapter", max_new_tokens=limit)
