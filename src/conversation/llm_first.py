"""One semantic interpretation per provider; deterministic checks before commit."""

from dataclasses import replace
import importlib.util
import math
from pathlib import Path
import re
from time import perf_counter
import unicodedata

from pydantic import ValidationError

from common.schemas import PreferenceUpdate
from conversation._utils import normalize_text
from conversation.config import create_provider, create_chain_provider
from conversation.models import ParseResult, ParserMetadata, RuleParseResult
from conversation.normalization import normalize_update
from conversation.providers.base import ProviderError
from conversation.providers.structured import StructuredConversationTurn
from conversation.reference_resolver import merge_references, resolve_llm_references, resolve_message_references
from conversation.safety import allergy_retraction_targets, scope_allergy_removal, validate_candidate, validate_model_delta

CLARIFY = "Mình chưa thể xử lý yêu cầu này một cách chắc chắn. Bạn nói rõ hơn món ăn hoặc điều muốn thay đổi nhé; mình vẫn giữ các lựa chọn trước đó."


def _changed(update):
    return any(update.model_dump().values())


def _has_search_state(state):
    return state is not None and any((state.food, state.cuisine, state.hard_constraints,
        state.soft_preferences, state.semantic_preferences, state.negative_preferences, state.reference_restaurants, state.context))


def _conversational_reply(reply, request):
    if not reply or not reply.strip():
        raise ValueError("A conversational turn needs a reply")
    text = normalize_text(reply)
    from conversation.grounding import quantities
    # No catalog was consulted. Reject observable price/rating/availability
    # claims; do not silently present them as verified restaurant facts.
    if quantities(text, "budget") or quantities(text, "rating") or re.search(r"(?:\d\s*(?:k|sao|stars?|điểm)|\d[\d., ]*\s*(?:vnd|đồng|usd|₫)|[$€₫]|còn bàn|còn món|có bàn trống|đang mở cửa|currently open|available tables|in stock)", text):
        raise ValueError("Conversational reply contains unsupported catalog claims")
    if re.search(r"(?:quán|nhà hàng|restaurant)\s+[^.!?]{0,70}(?:giá|rating|thực đơn|menu|phục vụ|có bán|mở cửa)", text):
        raise ValueError("Conversational reply asserts restaurant facts")
    for previous in request.previous_results:
        if previous.restaurant_name and normalize_text(previous.restaurant_name) in text:
            raise ValueError("Conversational replies cannot assert facts about supplied venues")
    return reply.strip()


def _candidate(update, request, message, retracted, evidence=None):
    # Reuse form priority, schema validation and the established reference/state
    # boundaries; no retrieval, numerical policy or model-generated IDs here.
    from conversation.parser import _apply_form, _validate_llm
    raw = PreferenceUpdate.model_validate(update.model_dump() if isinstance(update, PreferenceUpdate) else update)
    _validate_llm(raw)
    raw = _apply_form(raw, request)
    from conversation.search_contract import normalize_search_delta
    raw = normalize_search_delta(raw, request, message)
    validate_model_delta(raw, request, message, retracted, evidence=evidence)
    raw.references = merge_references(resolve_message_references(message, request.previous_results),
        resolve_llm_references(raw.references, request.previous_results, message))
    if any(ref.get("status") == "unresolved" for ref in raw.references):
        raise ValueError("Reference requires clarification")
    result = normalize_update(scope_allergy_removal(raw, request, retracted), request.current_state)
    validate_candidate(result, request, message, retracted, evidence=evidence)
    return result


def _fallback_search_allowed(message, state):
    """The extraction-only LoRA cannot safely answer/classify arbitrary questions."""
    text = normalize_text(message)
    if re.search(r"\?|khác.*như thế nào|là gì|tại sao|how|what|why|explain|difference|chào|\bhello\b|\bhi\b", text):
        return False
    return bool(re.search(r"\b(?:tìm|muốn ăn|cho mình|đổi|find|want|search|under|within|dưới|cách tôi)\b|\d\s*(?:km|k)\b", text)
                or state and re.search(r"hơn|thay|bỏ|thêm|more|less|change|cheaper|closer", text))


def _local_available(config):
    if not config.local_slm_enabled or config.local_slm_backend != "qwen_lora":
        return False
    path = Path(config.local_slm_fallback_adapter_path).expanduser()
    if not path.is_absolute():
        path = Path(__file__).resolve().parents[2] / path
    return all((path / name).is_file() for name in ("adapter_config.json", "adapter_model.safetensors", "tokenizer_config.json")) and all(
        importlib.util.find_spec(name) is not None for name in ("torch", "transformers", "peft", "bitsandbytes", "accelerate"))


def interpret_request(request, config, *, provider=None, slm_provider=None):
    from conversation.parser import _apply_form, _state_for_inference
    from conversation.state_manager import update_state
    started = perf_counter()
    if request.current_state is not None:
        if request.current_state.session_id != request.session_id:
            raise ValueError("current_state belongs to a different session")
        if request.user_id is not None and request.current_state.user_id not in (None, request.user_id):
            raise ValueError("current_state belongs to a different user")
    message = unicodedata.normalize("NFC", request.message or "").strip()
    metadata = ParserMetadata(original_message=request.message, parsed_message=message,
        input_normalized=message != (request.message or ""), requires_llm=bool(message),
        parser_used="llm" if message else "rule",
        slm_enabled=config.local_slm_enabled, slm_backend=config.local_slm_backend)
    rule = RuleParseResult(update=PreferenceUpdate(), requires_llm=bool(message))

    def finish(update):
        metadata.total_ms = metadata.latency_ms = (perf_counter() - started) * 1000
        return ParseResult(preference_update=update, rule_result=rule, metadata=metadata)

    if not message:
        # Form-only submission/refresh has no language to interpret or classify.
        from conversation.search_contract import normalize_search_delta
        update = normalize_update(normalize_search_delta(_apply_form(PreferenceUpdate(), request), request, ''), request.current_state)
        update_state(request.current_state, update, request.session_id, request.user_id)
        return finish(update)

    costs = []
    for backup in (False, True):
        selected = None
        called = False
        llm_started = perf_counter()
        metadata.provider_models.append(config.openrouter_backup_model if backup else config.openrouter_primary_model)
        try:
            selected = create_chain_provider(config, backup=True) if backup else provider or create_provider(config)
            metadata.provider = "openrouter"
            metadata.llm_called = called = True
            raw = selected.interpret_turn(message=message, current_state=_state_for_inference(request),
                previous_results=[r.model_copy(deep=True) for r in request.previous_results], rule_update=None)
            turn = StructuredConversationTurn.model_validate(raw.model_dump() if isinstance(raw, StructuredConversationTurn) else raw)
            update = turn.preferences.to_update()
            if turn.intent in {"conversation", "informational", "clarification"}:
                if _changed(update):
                    raise ValueError("Non-search turns cannot mutate preferences")
                metadata.assistant_message = _conversational_reply(turn.reply, request)
                metadata.state_preserved = True
                metadata.clarification_required = turn.intent == "clarification"
            else:
                retracted = allergy_retraction_targets(message)
                update = _candidate(update, request, message, retracted, turn.evidence)
                if not _changed(update) and not _has_search_state(request.current_state):
                    raise ValueError("Empty search without prior preferences needs clarification")
            metadata.intent = turn.intent
            metadata.parser_used = "llm"
            metadata.llm_error = None
            return finish(update)
        except Exception as exc:
            code = (exc.code if isinstance(exc, ProviderError) else "timeout" if isinstance(exc, TimeoutError)
                    else "invalid_output" if isinstance(exc, (ValidationError, ValueError, TypeError)) else "provider_error")
            metadata.llm_error = code
            metadata.provider_errors.append(code)
            metadata.fallback_used = True
        finally:
            metadata.llm_ms += (perf_counter() - llm_started) * 1000
            if called:
                for key, value in getattr(selected, "last_usage", {}).items():
                    if key in {"input_tokens", "output_tokens", "total_tokens"} and type(value) is int and value >= 0:
                        metadata.usage[key] = metadata.usage.get(key, 0) + value
                attempts = getattr(selected, "last_attempts", 1)
                metadata.provider_attempts = (metadata.provider_attempts or 0) + (attempts if type(attempts) is int and attempts >= 0 else 1)
                cost = getattr(selected, "last_cost_usd", None)
                costs.append(float(cost) if type(cost) in (float, int) and math.isfinite(cost) and cost >= 0 else None)
                metadata.cost_usd = sum(costs) if costs and all(c is not None for c in costs) else None
            if selected is not None and selected is not provider:
                close = getattr(selected, "close", None)
                if callable(close):
                    try:
                        close()
                    except Exception:
                        pass

    # Local artifacts remain optional and lazy. Never download or train on this path.
    if config.local_slm_enabled and _fallback_search_allowed(message, request.current_state):
        slm_started = perf_counter()
        try:
            if slm_provider is None and not _local_available(config):
                raise ProviderError("Local V4 is unavailable")
            from conversation.slm.base import SLMInput
            from conversation.slm.router import create_slm_provider, parse_local
            local_config = replace(config, local_slm_adapter_path=config.local_slm_fallback_adapter_path,
                                   local_slm_local_files_only=True)
            selected_local = slm_provider if slm_provider is not None else create_slm_provider(local_config)
            metadata.slm_called = True
            metadata.provider_models.append("local/qwen-v4")
            result = parse_local(local_config, SLMInput(message=message, current_state=_state_for_inference(request),
                previous_results=request.previous_results, rule_result=rule), selected_local)
            metadata.slm_confidence = result.confidence
            if result.should_fallback or result.confidence < config.local_slm_min_confidence or result.metadata.get("repair_rejected"):
                raise ValueError("Local result is incomplete or uncertain")
            update = _candidate(result.update, request, message, allergy_retraction_targets(message), [])
            if not _changed(update):
                raise ValueError("Local extraction is empty")
            metadata.parser_used = "slm"
            metadata.intent = "refinement" if request.current_state else "search"
            return finish(update)
        except Exception:
            metadata.slm_error = "local_unavailable_or_invalid"
        finally:
            metadata.slm_ms = (perf_counter() - slm_started) * 1000

    if config.rule_fallback_enabled and _fallback_search_allowed(message, request.current_state):
        from conversation.rule_parser import parse_by_rules_detailed
        rule = parse_by_rules_detailed(message)
        if not rule.requires_llm:
            try:
                update = _candidate(rule.update, request, message, allergy_retraction_targets(message), [])
                if _changed(update):
                    metadata.parser_used = "rule_fallback"
                    metadata.intent = "refinement" if request.current_state else "search"
                    return finish(update)
            except (ValueError, TypeError):
                pass
    metadata.intent = "clarification"
    metadata.assistant_message = CLARIFY
    metadata.state_preserved = metadata.clarification_required = metadata.partial_result = True
    return finish(PreferenceUpdate())
