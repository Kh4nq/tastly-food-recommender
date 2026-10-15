"""Lazy backend selection; cache the local provider across conversation turns."""
from functools import lru_cache
from conversation.slm.base import SLMParseResult, SLMProvider
from conversation.slm.disabled import DisabledSLMProvider
from conversation.slm.partial import split_update


def create_slm_provider(config) -> SLMProvider:
    if not config.local_slm_enabled or config.local_slm_backend == "disabled":
        return DisabledSLMProvider()
    if config.local_slm_backend == "qwen_lora":
        return _qwen_provider(config.local_slm_base_model, config.local_slm_adapter_path,
                              config.local_slm_max_new_tokens, config.local_slm_local_files_only)
    raise ValueError("slm_unavailable")


@lru_cache(maxsize=1)
def _qwen_provider(base_model, adapter_path, max_new_tokens, local_files_only=True):
    from conversation.slm.qwen_lora import QwenLoRAProvider
    return QwenLoRAProvider(base_model, adapter_path, max_new_tokens=max_new_tokens,
                            local_files_only=local_files_only)


def parse_local(config, request, provider=None) -> SLMParseResult:
    selected = provider if provider is not None else create_slm_provider(config)
    raw = selected.parse(request.model_copy(deep=True))
    return validate_local_result(raw)


def validate_local_result(raw) -> SLMParseResult:
    envelope = raw.model_dump() if isinstance(raw, SLMParseResult) else dict(raw)
    update, rejected = split_update(envelope["update"])
    envelope["update"] = update
    result = SLMParseResult.model_validate(envelope)
    if rejected:
        result.metadata["repair_rejected"] = rejected
    if result.metadata.get("repair_rejected") and not any(update.model_dump().values()):
        raise ValueError("No meaningful valid SLM subset")
    return result
