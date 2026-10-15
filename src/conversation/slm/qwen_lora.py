"""Lazy Qwen/PEFT inference for the AI2 SFT contract; no normalization here."""

from collections import Counter
import gc
import json
import logging
from pathlib import Path
from threading import Lock
import traceback

from common.schemas import PreferenceUpdate
from conversation.slm.base import SLMInput, SLMParseResult


logger = logging.getLogger(__name__)


def _placement_summary(model, device, linear4bit, *, require_lora=False):
    """Reject incomplete/implicitly offloaded weights before caching a runtime."""
    if not getattr(model, "is_loaded_in_4bit", False):
        raise RuntimeError("Qwen base model is not loaded in 4-bit")
    quantized = [module for module in model.modules() if isinstance(module, linear4bit)]
    if not quantized or any(
        not getattr(module.weight, "bnb_quantized", False)
        or getattr(module.weight, "quant_state", None) is None
        for module in quantized
    ):
        raise RuntimeError("Qwen 4-bit weights are not materialized/quantized")
    parameters, lora = Counter(), Counter()
    for name, parameter in model.named_parameters():
        placement = str(parameter.device)
        is_lora = "lora_" in name
        if placement == "meta":
            kind = "LoRA parameter" if is_lora else "base parameter"
            raise RuntimeError(f"Unmaterialized {kind} on meta: {name}")
        if placement != device:
            raise RuntimeError(f"Unexpected placement for {name}: {placement}; expected {device}")
        parameters[placement] += 1
        if is_lora:
            lora[placement] += 1
    for name, buffer in model.named_buffers():
        if str(buffer.device) == "meta":
            raise RuntimeError(f"Unmaterialized buffer on meta: {name}")
    if require_lora and not lora:
        raise RuntimeError("No materialized LoRA parameters found")
    return {
        "is_loaded_in_4bit": True,
        "quantized_linear_layers": len(quantized),
        "parameter_devices": dict(parameters),
        "lora_parameter_devices": dict(lora),
        "meta_parameters": 0,
    }


TRAINING_INSTRUCTION = (
    "Trích xuất PreferenceUpdate v0.2 cho AI2 Food Recommender. "
    "Chỉ trả về một JSON object hợp lệ, không giải thích."
)


def build_input_text(request: SLMInput) -> str:
    """Match train_sft.jsonl input_text (instruction + canonical input JSON)."""
    return TRAINING_INSTRUCTION + "\n" + json.dumps(
        request.model_dump(mode="json"), ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False,
    )


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def _invalid_constant(value):
    raise ValueError("Non-finite JSON number")


def parse_response(text: str) -> PreferenceUpdate:
    """Accept one complete SFT target, with no code fences or guessed repairs."""
    return PreferenceUpdate.model_validate(_response_mapping(text))


def _response_mapping(text: str) -> dict:
    payload = json.loads(text, object_pairs_hook=_unique_object,
                         parse_constant=_invalid_constant)
    if not isinstance(payload, dict) or set(payload) != set(PreferenceUpdate.model_fields):
        raise ValueError("Expected the complete PreferenceUpdate v0.2 target")
    return payload


class QwenLoRAProvider:
    """Load on first parse, reuse weights, and serialize load/generation calls.

    Confidence 0.80 is a fixed structural acceptance gate for the existing router,
    NOT a calibrated semantic probability. The parser still validates, resolves
    references, merges rules/forms, normalizes and trial-applies every update.
    Raising the configured minimum above 0.80 forces external fallback.
    """

    def __init__(self, base_model: str, adapter_path: str, *, max_new_tokens: int = 512,
                 local_files_only: bool = True):
        if type(max_new_tokens) is not int or not 1 <= max_new_tokens <= 4096:
            raise ValueError("max_new_tokens must be between 1 and 4096")
        self.base_model = base_model
        self.adapter_path = adapter_path
        self.max_new_tokens = max_new_tokens
        self.local_files_only = local_files_only
        self._model = self._tokenizer = self._torch = None
        self._lock = Lock()
        # Diagnostic text stays on the provider, never in ordinary routing logs.
        self.last_response: str | None = None
        self.last_load_error: str | None = None
        self.last_gpu_load_error: str | None = None
        self.load_summary: dict | None = None

    def _load(self):
        if self._model is not None:
            return
        self.last_load_error = self.last_gpu_load_error = None
        self.load_summary = None
        adapter = Path(self.adapter_path).expanduser()
        if not adapter.is_absolute():
            adapter = Path(__file__).resolve().parents[3] / adapter
        adapter = adapter.resolve()
        if not (adapter / "adapter_config.json").is_file():
            raise ValueError("Local adapter configuration is missing")
        adapter_config = json.loads((adapter / "adapter_config.json").read_text(encoding="utf-8"))
        base_source = self.base_model
        local_base = Path(base_source).expanduser()
        if not local_base.is_absolute() and (Path(__file__).resolve().parents[3] / local_base).is_dir():
            base_source = str(Path(__file__).resolve().parents[3] / local_base)
        base_options = {"local_files_only": self.local_files_only}
        if adapter_config.get("revision") and not Path(base_source).is_dir():
            base_options["revision"] = adapter_config["revision"]
        import torch
        if not torch.cuda.is_available():
            raise RuntimeError("Local Qwen NF4 GPU loading requires torch.cuda.is_available() == True")
        from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
        from bitsandbytes.nn import Linear4bit
        from peft import PeftModel

        tokenizer = AutoTokenizer.from_pretrained(str(adapter), local_files_only=True,
                                                  trust_remote_code=False)
        quantization = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_use_double_quant=True,
            bnb_4bit_compute_dtype=torch.float16,
        )

        def load_on(device):
            # A single explicit device avoids Accelerate's CPU/disk offload hooks
            # and their meta placeholders before PEFT attaches the adapter.
            base = AutoModelForCausalLM.from_pretrained(
                base_source, torch_dtype=torch.float16, device_map={"": device},
                quantization_config=quantization, trust_remote_code=False,
                **base_options,
            )
            _placement_summary(base, device, Linear4bit)
            model = PeftModel.from_pretrained(
                base, str(adapter), is_trainable=False, local_files_only=True,
                low_cpu_mem_usage=False, autocast_adapter_dtype=False,
                torch_device=device, device_map={"": device},
            )
            summary = _placement_summary(model, device, Linear4bit, require_lora=True)
            model.eval()
            return model, summary

        device = f"cuda:{torch.cuda.current_device()}"
        try:
            model, summary = load_on(device)
        except torch.cuda.OutOfMemoryError:
            # Store text, not the traceback object that retains partial GPU weights.
            self.last_gpu_load_error = traceback.format_exc()
        else:
            summary["strategy"] = "cuda_nf4"

        if self.last_gpu_load_error is not None:
            # Leave the except block before collecting its failed model/adapter.
            gc.collect()
            torch.cuda.empty_cache()
            logger.warning("Local Qwen CUDA load ran out of memory; retrying full CPU NF4 (slower).")
            # Modern bitsandbytes supports CPU NF4. Keep *all* weights on CPU,
            # including PEFT's checkpoint load/redispatch: no mixed-device hooks.
            # Unsupported CPU backends fail normally; never accept meta adapters.
            model, summary = load_on("cpu")
            summary["strategy"] = "cpu_nf4_fallback"

        self.load_summary = summary
        logger.info("Local Qwen placement: %s", summary)
        self._torch, self._tokenizer, self._model = torch, tokenizer, model

    def _format_prompt(self, input_text: str) -> str:
        # Final training used one user message; target_text was plain continuation
        # followed by EOS, not a second chat-template message.
        return self._tokenizer.apply_chat_template(
            [{"role": "user", "content": input_text}], tokenize=False,
            add_generation_prompt=True, enable_thinking=False,
        )

    def _generate(self, request: SLMInput) -> str:
        prompt = self._format_prompt(build_input_text(request))
        inputs = self._tokenizer(prompt, return_tensors="pt", add_special_tokens=False)
        inputs = inputs.to(self._model.get_input_embeddings().weight.device)
        prompt_length = inputs["input_ids"].shape[-1]
        with self._torch.inference_mode():
            output = self._model.generate(
                **inputs, max_new_tokens=self.max_new_tokens,
                do_sample=False, num_beams=1, repetition_penalty=1.0,
                pad_token_id=self._tokenizer.eos_token_id,
                eos_token_id=self._tokenizer.eos_token_id,
                return_dict_in_generate=False,
            )
        # Decode only newly generated assistant tokens, never the JSON in input.
        return self._tokenizer.decode(output[0][prompt_length:], skip_special_tokens=True).strip()

    def parse(self, request: SLMInput) -> SLMParseResult:
        with self._lock:
            self.last_response = None
            try:
                self._load()
            except Exception:
                self.last_load_error = traceback.format_exc()
                return self._failure("load_failed")
            try:
                self.last_response = self._generate(request)
            except Exception:
                return self._failure("generation_failed")
            try:
                from conversation.slm.router import validate_local_result
                return validate_local_result({
                    "update": _response_mapping(self.last_response), "confidence": 0.80,
                    "metadata": {"confidence_basis": "structural_validation_only"},
                })
            except (ValueError, TypeError, RecursionError):
                return self._failure("invalid_json_or_schema")

    @staticmethod
    def _failure(code):
        # Keep runtime details out of routing logs; explicit diagnostics can read
        # last_load_error / last_gpu_load_error on the provider.
        return SLMParseResult(update=PreferenceUpdate(), confidence=0.0,
                              should_fallback=True, metadata={"error": code})
