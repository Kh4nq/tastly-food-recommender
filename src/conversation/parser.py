"""Orchestrate forms, rules, references and validated provider selection."""

from copy import deepcopy
import re
from time import perf_counter

from pydantic import ValidationError

from common.schemas import PreferenceUpdate, UserFormInput, UserRequest
from conversation._utils import ABSOLUTE_DIMENSIONS, normalize_text, unique
from conversation.config import ConversationConfig, create_provider, create_chain_provider
from conversation.evidence import AllergyEvidenceError, ground_model_evidence, has_explicit_allergy, validate_explicit_evidence
from conversation.models import ParseResult, ParserMetadata
from conversation.normalization import normalize_update
from conversation.preprocessing import Translator, prepare_input
from conversation.providers.base import LLMProvider, ProviderError
from conversation.reference_resolver import (
    merge_references, resolve_llm_references, resolve_message_references,
)
from conversation.rule_parser import parse_by_rules_detailed
from conversation.state_manager import update_state


def parse_user_input(request: UserRequest, provider: LLMProvider | None = None, *,
                     config: ConversationConfig | None = None, translator: Translator | None = None) -> PreferenceUpdate:
    """Parse one turn with explicit non-None form values taking precedence."""
    return parse_user_input_detailed(request, provider, config=config, translator=translator).preference_update


def _apply_form(update: PreferenceUpdate, request: UserRequest) -> PreferenceUpdate:
    form = request.form
    if form.location is not None:
        update.set_values["location"] = form.location.model_dump(mode="json")
    for field in ("food", "cuisine"):
        value = getattr(form, field)
        if value is not None:
            update.set_values[field] = unique([value] if isinstance(value, str) else value)
            update.remove_preferences = [key for key in update.remove_preferences if key != field]
    for field, dimension in ABSOLUTE_DIMENSIONS:
        value = getattr(form, field)
        if value is not None:
            update.add_hard_constraints[field] = value
            update.relative_updates.pop(dimension, None)
            # Form priority includes NLP removal of the same absolute setting.
            update.remove_preferences = [key for key in update.remove_preferences if key not in (field, "hard_constraints." + field)]
    for field in ('item_kind', 'serving_style'):
        value = getattr(form, field)
        if value is not None:
            update.add_hard_constraints[field] = value
            update.remove_preferences = [key for key in update.remove_preferences if key not in (field, 'hard_constraints.' + field)]
    if form.item_kind == 'beverage' and form.serving_style is None:
        update.add_hard_constraints.pop('serving_style', None)
        update.remove_preferences.append('hard_constraints.serving_style')
    return update


def _has_later_correction(message: str, field: str) -> bool:
    """Allow a model to interpret an explicit, still-unparsed correction only.

    A contrast about a different attribute is not permission to change a known
    value. If rules already understand the correction, their final value wins.
    """
    cues = {
        "budget_max": r"ngân sách|budget|giá|nghìn|ngàn|\d+\s*k\b",
        "max_distance_km": r"khoảng cách|\bkm\b|cây số",
        "max_travel_time_min": r"phút|thời gian",
        "parking": r"parking|gửi xe|đậu xe|đỗ xe|bắt buộc|phải có",
        "air_conditioning": r"điều hòa|máy lạnh",
        "transport_mode": r"xe|taxi|grab|đi bộ|metro|bus",
        "meal_time": r"sáng|trưa|tối|khuya|breakfast|lunch|dinner",
        "occasion": r"date|hẹn hò|gia đình|công việc|sinh nhật",
        "party_size": r"người",
        "companions": r"với|bạn|gia đình|trẻ em|đồng nghiệp",
    }
    pattern = cues.get(field)
    if pattern is None:
        return False
    matches = list(re.finditer(r"\b(?:thực ra|thật ra|đổi sang|đổi thành|chuyển sang|thôi để)\b", normalize_text(message)))
    if field == "transport_mode":
        matches.extend(re.finditer(r"\bchuyển từ[^.!?;]*?sang\b", normalize_text(message)))
        matches.sort(key=lambda m: m.end())
    if not matches:
        return False
    tail = normalize_text(message)[matches[-1].end():]
    if not re.search(pattern, tail):
        return False
    parsed = parse_by_rules_detailed(tail).update
    return not any(field in values for values in (
        parsed.add_hard_constraints, parsed.add_soft_preferences, parsed.context_updates))


def _merge(rule: PreferenceUpdate, llm: PreferenceUpdate, message: str = "") -> PreferenceUpdate:
    merged = rule.model_dump()
    for field, value in llm.model_dump().items():
        if isinstance(value, list):
            merged[field] = unique([*merged[field], *deepcopy(value)])
        elif field == "set_values":
            for key, item in value.items():
                if key in ("hard_constraints", "soft_preferences") and isinstance(item, dict):
                    # Legacy model projections are per-key deltas, not permission
                    # to clear unrelated persistent constraints.
                    merged[f"add_{key}"].update(deepcopy(item))
                    continue
                if isinstance(item, dict) and isinstance(merged[field].get(key), dict):
                    merged[field][key].update(deepcopy(item))
                else:
                    merged[field][key] = deepcopy(item)
        else:
            merged[field].update(deepcopy(value))
    if rule.add_hard_constraints.get("vegetarian") is True and rule.set_values.get("food"):
        foods = merged["set_values"].get("food", [])
        if foods and all(any(normalize_text(f) in normalize_text(r) for r in rule.set_values["food"]) for f in foods):
            merged["set_values"]["food"] = deepcopy(rule.set_values["food"])
    for key, value in rule.context_updates.items():
        if not _has_later_correction(message, key):
            merged["context_updates"][key] = deepcopy(value)
    for key, value in rule.add_hard_constraints.items():
        if key not in ("parking", "allergens_excluded") and not _has_later_correction(message, key):
            merged["add_hard_constraints"][key] = deepcopy(value)
            replacement = merged["set_values"].get("hard_constraints")
            if isinstance(replacement, dict):
                replacement.pop(key, None)
    for key in ("allergens_excluded",):
        if key in rule.add_hard_constraints:
            inferred = merged["add_hard_constraints"].get(key, [])
            merged["add_hard_constraints"][key] = unique([
                *deepcopy(rule.add_hard_constraints[key]),
                *(inferred if isinstance(inferred, list) else []),
            ])
    # A model removal cannot undo a positive constraint already understood by
    # rules. Explicit removals understood by rules have already cleared it.
    for key in rule.add_hard_constraints:
        if not _has_later_correction(message, key):
            merged["remove_preferences"] = [path for path in merged["remove_preferences"]
                if path not in (key, "hard_constraints." + key)]
    for field in ("add_soft_preferences", "add_hard_constraints"):
        for key in ("parking", "air_conditioning"):
            if key in getattr(rule, field) and not _has_later_correction(message, key):
                merged["add_hard_constraints"].pop(key, None)
                merged["add_soft_preferences"].pop(key, None)
                for container in ("hard_constraints", "soft_preferences"):
                    if isinstance(merged["set_values"].get(container), dict):
                        merged["set_values"][container].pop(key, None)
                merged[field][key] = getattr(rule, field)[key]
    # Parking needs explicit textual evidence, including on fully model-parsed turns.
    if not re.search(r"\bpark(?:ing)?\b|gửi xe|đậu xe|đỗ xe|bãi xe", normalize_text(message)):
        merged["add_hard_constraints"].pop("parking", None)
        merged["add_soft_preferences"].pop("parking", None)
        for container in ("hard_constraints", "soft_preferences"):
            if isinstance(merged["set_values"].get(container), dict):
                merged["set_values"][container].pop("parking", None)
    return PreferenceUpdate.model_validate(merged)


def _validate_llm(update: PreferenceUpdate) -> None:
    # IDs and reference context can only enter through the resolver.
    if any(key in update.set_values for key in ("reference_restaurants", "context")):
        raise ProviderError("Provider attempted to bypass reference resolution")
    soft = update.set_values.get("soft_preferences", {})
    if ("allergens_excluded" in update.add_soft_preferences
            or isinstance(soft, dict) and "allergens_excluded" in soft):
        raise ProviderError("Allergy exclusions must be hard constraints", code="invalid_output")
    hard = update.set_values.get("hard_constraints", {})
    if not isinstance(hard, dict):
        raise ProviderError("Invalid hard constraints")
    hard = {**hard, **update.add_hard_constraints}
    UserFormInput.model_validate({key: hard[key] for key, _ in ABSOLUTE_DIMENSIONS if key in hard})
    update_state(None, update, "validation")


def _state_for_inference(request: UserRequest):
    """Do not replay events from a legacy snapshot into a new model turn."""
    state = request.current_state.model_copy(deep=True) if request.current_state else None
    if state is not None:
        state.context.pop("relative_updates", None)
    return state


def parse_user_input_detailed(
    request: UserRequest, provider: LLMProvider | None = None,
    *, config: ConversationConfig | None = None, slm_provider=None, translator: Translator | None = None,
) -> ParseResult:
    """Return partial confident data on configuration, API or validation failure."""
    started = perf_counter()
    config = config or ConversationConfig.from_env()
    if config.llm_provider == "openrouter_chain" and config.llm_first_enabled:
        from conversation.llm_first import interpret_request
        return interpret_request(request, config, provider=provider, slm_provider=slm_provider)
    prepared = prepare_input(request, config, translator)
    message = prepared.message
    rule = parse_by_rules_detailed(message)
    references = resolve_message_references(message, request.previous_results)
    metadata = ParserMetadata(requires_llm=rule.requires_llm,
                              original_message=prepared.original_message, parsed_message=message,
                              input_normalized=prepared.input_normalized,
                              translation_attempted=prepared.translation_attempted,
                              translation_succeeded=prepared.translation_succeeded,
                              translation_error=prepared.translation_error,
                              rule_parse_ms=(perf_counter() - started) * 1000)
    # A standalone reference needs only caller context, not semantic inference.
    if len(references) == 1 and references[0].get("status") == "resolved":
        mention = normalize_text(str(references[0].get("mention", "")))
        if normalize_text(message).strip(".!? ") == mention:
            metadata.requires_llm = False
    metadata.slm_enabled = config.local_slm_enabled
    metadata.slm_backend = config.local_slm_backend
    update = rule.update.model_copy(deep=True)
    slm_accepted = False
    repair_rejected = None
    allergy_rejected = False
    chain = config.llm_provider == "openrouter_chain"
    retracted = set()
    if chain:
        from conversation.safety import is_noop, allergy_retraction_targets
        metadata.slm_enabled = False  # Cloud primary; local remains available through legacy opt-in modes.
        if is_noop(message):
            metadata.requires_llm = False
            update = PreferenceUpdate()
        try:
            retracted = allergy_retraction_targets(message)
        except AllergyEvidenceError:
            metadata.requires_llm = False
            metadata.clarification_required = metadata.state_preserved = True
            update = PreferenceUpdate()
    if metadata.requires_llm and config.local_slm_enabled and not chain:
        slm_started = perf_counter()
        try:
            from conversation.slm.base import SLMInput
            from conversation.slm.router import create_slm_provider, parse_local
            selected_slm = slm_provider if slm_provider is not None else create_slm_provider(config)
            metadata.slm_called = True
            result = parse_local(config, SLMInput(message=message,
                current_state=_state_for_inference(request), rule_result=rule,
                previous_results=request.previous_results), selected_slm)
            metadata.slm_confidence = result.confidence
            if result.should_fallback or result.confidence < config.local_slm_min_confidence:
                metadata.slm_error = "disabled_backend" if result.metadata.get("error") == "disabled_backend" else "uncertain"
            else:
                result.update = ground_model_evidence(result.update, message, form=request.form)
                _validate_llm(result.update)
                result.update.references = resolve_llm_references(result.update.references, request.previous_results, message)
                rejected = result.metadata.get("repair_rejected")
                if rejected:
                    from conversation.slm.partial import merge_preserving, unresolved_fields
                    subset = normalize_update(_merge(PreferenceUpdate(), result.update, message), request.current_state)
                    if not any(subset.model_dump().values()):
                        raise ValueError("No meaningful valid SLM subset")
                    candidate = merge_preserving(_apply_form(update.model_copy(deep=True), request),
                                                 subset, state=request.current_state)
                    candidate = _merge(PreferenceUpdate(), candidate, message)
                    rejected = unresolved_fields(candidate, rejected, state=request.current_state)
                else:
                    candidate = _merge(update, result.update, message)
                candidate = normalize_update(_apply_form(candidate, request), request.current_state)
                validate_explicit_evidence(candidate, message, form=request.form)
                update_state(request.current_state, candidate, request.session_id, request.user_id)
                update = candidate
                metadata.parser_used = "hybrid_slm"
                repair_rejected = rejected
                slm_accepted = not repair_rejected
                if repair_rejected:
                    metadata.slm_error = "partial_repair"
                elif result.metadata.get("repair_rejected"):
                    metadata.slm_error = "partial_validation"
        except Exception as exc:
            allergy_rejected = isinstance(exc, AllergyEvidenceError)
            metadata.slm_error = "slm_unavailable" if config.local_slm_backend != "disabled" and slm_provider is None else "invalid_output_or_failure"
        finally:
            metadata.slm_fallback = not slm_accepted
            metadata.slm_ms = (perf_counter() - slm_started) * 1000
    if metadata.requires_llm and not slm_accepted:
        llm_started = perf_counter()
        collected_usage, collected_costs, attempts_total = {}, [], 0
        accepted = False
        for position in range(2 if chain else 1):
            selected = None
            called = False
            try:
                selected = (create_chain_provider(config, backup=True) if position else
                            provider if provider is not None else create_provider(config))
                metadata.provider = selected.name if selected.name in ("mock", "openai", "gemini", "openrouter") else "custom"
                metadata.llm_called = called = True
                if chain:
                    metadata.provider_models.append(config.openrouter_backup_model if position else config.openrouter_primary_model)
                if repair_rejected:
                    from conversation.slm.partial import repair_message
                raw = selected.parse_preference(
                    message=repair_message(repair_rejected) if repair_rejected else message,
                    current_state=_state_for_inference(request),
                    previous_results=[result.model_copy(deep=True) for result in request.previous_results],
                    rule_update=(update if repair_rejected else rule.update).model_copy(deep=True),
                )
                # Round-trip also validates model instances constructed without validation.
                if repair_rejected:
                    from conversation.slm.partial import merge_preserving, split_update
                    llm, invalid_repair = split_update(raw)
                    metadata.partial_result = bool(invalid_repair)
                else:
                    llm = PreferenceUpdate.model_validate(raw.model_dump() if isinstance(raw, PreferenceUpdate) else raw)
                if chain:
                    from conversation.safety import validate_model_delta
                    validate_model_delta(llm, request, message, retracted)
                llm = ground_model_evidence(llm, message, form=request.form)
                _validate_llm(llm)
                llm.references = resolve_llm_references(llm.references, request.previous_results, message)
                if repair_rejected:
                    candidate = merge_preserving(update, llm, rejected=repair_rejected, state=request.current_state)
                    if candidate == update:
                        raise ProviderError("Repair supplied no usable additions", code="invalid_output")
                    candidate = _merge(PreferenceUpdate(), candidate, message)
                else:
                    candidate = _merge(update, llm, message)
                if chain:
                    from conversation.safety import scope_allergy_removal
                    candidate = scope_allergy_removal(candidate, request, retracted)
                    candidate.references = merge_references(references, candidate.references)
                candidate = normalize_update(_apply_form(candidate, request), request.current_state)
                if chain:
                    from conversation.safety import validate_candidate
                    validate_candidate(candidate, request, message, retracted)
                else:
                    validate_explicit_evidence(candidate, message, form=request.form)
                    update_state(request.current_state, candidate, request.session_id, request.user_id)

                update = candidate
                metadata.parser_used = "hybrid_llm"
                metadata.llm_error = None
                allergy_rejected = False
                accepted = True
                if chain:
                    metadata.partial_result = False
            except Exception as exc:
                allergy_rejected = allergy_rejected or isinstance(exc, AllergyEvidenceError)
                # Never copy exception text, response bodies or credentials.
                metadata.llm_error = (exc.code if isinstance(exc, ProviderError) and called
                    else "invalid_output" if isinstance(exc, (ValidationError, TypeError, ValueError))
                    else "timeout" if isinstance(exc, TimeoutError)
                    else "provider_error" if called else "provider_unavailable")
                if chain:
                    metadata.provider_errors.append(metadata.llm_error)
                metadata.partial_result = True
                metadata.parser_used = "hybrid_slm" if repair_rejected else "rule_fallback"
            finally:
                if called:
                    usage = getattr(selected, "last_usage", {})
                    if isinstance(usage, dict):
                        for key, value in usage.items():
                            if key in {"input_tokens", "output_tokens", "total_tokens"} and type(value) is int and value >= 0:
                                collected_usage[key] = collected_usage.get(key, 0) + value
                    import math
                    cost = getattr(selected, "last_cost_usd", None)
                    collected_costs.append(float(cost) if type(cost) in (int, float) and math.isfinite(cost) and cost >= 0 else None)
                    attempts = getattr(selected, "last_attempts", None)
                    if type(attempts) is int and attempts >= 0:
                        attempts_total += attempts
                        metadata.provider_attempts = attempts_total
                    elif chain:
                        attempts_total += 1
                        metadata.provider_attempts = attempts_total
                if selected is not None and provider is not selected:
                    close = getattr(selected, "close", None)
                    if callable(close):
                        try:
                            close()
                        except Exception:
                            pass
            if accepted:
                break
            if chain and position == 0:
                metadata.fallback_used = True
        metadata.llm_ms = (perf_counter() - llm_started) * 1000
        metadata.usage = collected_usage
        if collected_costs and all(cost is not None for cost in collected_costs):
            metadata.cost_usd = sum(collected_costs)
        if chain and not accepted:
            metadata.state_preserved = metadata.clarification_required = True
            update = PreferenceUpdate()
    update.references = merge_references(references, update.references)
    metadata.clarification_required = metadata.clarification_required or allergy_rejected or any(ref.get("status") == "unresolved" for ref in update.references)
    hard = update.set_values.get("hard_constraints", {})
    if not retracted and has_explicit_allergy(message) and not {**hard, **update.add_hard_constraints}.get("allergens_excluded"):
        metadata.clarification_required = True
    metadata.partial_result = metadata.partial_result or metadata.clarification_required
    update = normalize_update(_apply_form(update, request), request.current_state)
    if chain:
        try:
            from conversation.safety import scope_allergy_removal, validate_candidate
            if metadata.state_preserved:
                update = PreferenceUpdate()
            else:
                update = normalize_update(scope_allergy_removal(update, request, retracted), request.current_state)
                validate_candidate(update, request, message, retracted)
        except (ValueError, TypeError, ValidationError):
            update = PreferenceUpdate()
            metadata.state_preserved = metadata.clarification_required = metadata.partial_result = True
    metadata.total_ms = metadata.latency_ms = (perf_counter() - started) * 1000
    return ParseResult(preference_update=update, rule_result=rule, metadata=metadata)
