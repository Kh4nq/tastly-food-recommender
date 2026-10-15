"""Reject a few observable model contradictions, without claiming semantic QA."""

from decimal import Decimal
import re

from common.schemas import PreferenceUpdate, UserFormInput
from conversation._utils import normalize_text
from conversation.normalization import canonical_constraints, CONSTRAINT_VALUE_ALIASES


class AllergyEvidenceError(ValueError):
    """A provider allergy delta is not safe to accept without clarification."""


def _literal_allergy_targets(text: str) -> set[str]:
    """Ground extensible literal targets without guessing a canonical synonym."""
    from conversation.rule_parser import _is_negated
    aliases = CONSTRAINT_VALUE_ALIASES["allergens_excluded"]
    targets = set()
    for match in re.finditer(r"\b(?:bị )?dị ứng ([^.!?;]+)|\bi(?:'m| am) allergic to ([^.!?;]+)", text):
        prefix = re.split(r"[,.!?;]", text[:match.start()])[-1]
        if _is_negated(text, match.start()) or re.search(r"\b(?:nếu|có thể|có lẽ|chưa rõ|if|might|maybe)\b", prefix):
            continue
        clause = re.split(r"\b(?:nhưng|but|chỉ|và (?:muốn|tìm|cần)|and (?:want|need))\b", match[1] or match[2])[0]
        for target in re.split(r"\s*(?:,|\bvà\b|\band\b|&)\s*", clause):
            target = target.strip()
            if target:
                targets.add(aliases.get(target, target))
    return targets


def _bounded_evidence_scope(message: str) -> tuple[bool, bool, bool]:
    text = normalize_text(message)
    aliases = CONSTRAINT_VALUE_ALIASES["allergens_excluded"]
    target = "(?:" + "|".join(re.escape(a) for a in sorted(aliases, key=len, reverse=True)) + ")"
    allergy_only = bool(re.fullmatch(
        r"(?:(?:tôi|mình|em|i)(?: am|'m)? )?(?:(?:không|chẳng) )?(?:còn |bị |còn bị )?"
        rf"(?:dị ứng|allergic to) {target}(?:\s*(?:,|và|and|&)\s*{target})*[.!? ]*", text))
    temporal_only = bool(re.fullmatch(
        r"(?:(?:sáng|trưa|tối) (?:nay|mai)|bữa (?:sáng|trưa|tối))"
        r"(?:[, ]+(?:à )?(?:thực ra|thật ra) [, ]*(?:(?:sáng|trưa|tối) (?:nay|mai)|bữa (?:sáng|trưa|tối)))+[.!? ]*", text))
    from conversation.reference_resolver import REFERENCE_PATTERN
    residue = REFERENCE_PATTERN.sub(" ", text)
    reference_only = bool(REFERENCE_PATTERN.search(text) and re.fullmatch(
        r"\s*(?:(?:chọn|lấy|mình chọn|tôi chọn)\s*)?(?:nhé|nha)?[.!? ]*", residue))
    return allergy_only, temporal_only, reference_only


def ground_model_evidence(update: PreferenceUpdate, message: str, *, form: UserFormInput | None = None) -> PreferenceUpdate:
    """Remove unsupported additions in three bounded, attribute-free scopes.

    Preserve supported context corrections/references. Attribute-free selection
    cannot generate relative events or remove existing constraints either.
    Open-ended context outside these scopes still uses model interpretation.
    """
    result = update.model_copy(deep=True)
    # This concerns conversational context only. Whether selection implies
    # reference sentiment remains a separate human-review policy.
    if "sentiment" in result.context_updates and not re.search(
        r"\b(?:thích|ghét|vui|buồn|hài lòng|thất vọng|không hợp|happy|sad|disappointed|like|dislike|love|hate)\b",
        normalize_text(message),
    ):
        result.context_updates.pop("sentiment")
    allergy_only, temporal_only, reference_only = _bounded_evidence_scope(message)
    if allergy_only and (form is None or form.food is None):
        result.set_values.pop("food", None)
    if temporal_only:
        result.context_updates = {key: value for key, value in result.context_updates.items() if key == "meal_time"}
    if reference_only:
        result.set_values.clear()
        result.add_hard_constraints.clear()
        result.add_soft_preferences.clear()
        result.context_updates.clear()
        result.add_semantic_preferences.clear()
        result.add_negative_preferences.clear()
        result.remove_preferences.clear()
        result.relative_updates.clear()
    return result


def has_explicit_allergy(message: str) -> bool:
    """Recognize a positive allergy cue; do not guess its target or scope."""
    from conversation.rule_parser import _is_negated, explicit_allergy_matches
    text = normalize_text(message).replace("’", "'")
    # Mentioning a retained, already-confirmed allergy is not a fresh assertion
    # requiring a new exclusion in this turn's delta.
    if (re.search(r"dị ứng (?:đã xác nhận|đã biết)|(?:dị ứng|allergies).*\b(?:giữ nguyên|không đổi|unchanged)\b", text)
            and not list(explicit_allergy_matches(text))):
        return False
    return any(not _is_negated(text, match.start()) for match in re.finditer(
        r"\bdị ứng\b|\bi(?:'m| am) allergic to\b", text))


def validate_explicit_evidence(update: PreferenceUpdate, message: str, *, form: UserFormInput | None = None,
                               retained_allergens: set[str] | None = None,
                               retracted_allergens: set[str] | None = None) -> None:
    """Check only unambiguous numeric/allergy/facility cues in the current turn.

    Unknown fields and ambiguous clauses still require model interpretation.
    This never generates fields, coerces units or changes a soft wish to hard.
    """
    text = normalize_text(message).replace("’", "'")
    retained = retained_allergens or set()
    retracted = retracted_allergens or set()
    containers = {}
    for scope in ("hard_constraints", "soft_preferences"):
        containers[scope] = canonical_constraints({
            **update.set_values.get(scope, {}), **getattr(update, "add_" + scope),
        })
    if any("max_distance_m" in values for values in containers.values()):
        raise ValueError("max_distance_m is unsupported; distance uses max_distance_km")
    if (any("max_distance_km" in values for values in containers.values())
            and (form is None or form.max_distance_km is None)
            and not re.search(r"\d+(?:[.,]\d+)?\s*(?:km|m|meters?|metres?|cây số)\b", text)
            and re.search(r"\d+(?:[.,]\d+)?\s*(?:phút|minutes?|người|k|nghìn|ngàn|vnd|đồng)\b", text)):
        raise ValueError("Money/time/party-size numbers are not distance evidence")
    if has_explicit_allergy(message) and not retracted and not containers["hard_constraints"].get("allergens_excluded"):
        raise AllergyEvidenceError("Explicit allergy requires a hard exclusion or clarification")
    from conversation.rule_parser import explicit_allergy_matches
    explicit = {a for _, targets in explicit_allergy_matches(text) for a in targets} - retracted
    exclusions = set(containers["hard_constraints"].get("allergens_excluded", []))
    grounded = (explicit | _literal_allergy_targets(text)) - retracted
    if explicit:
        if not explicit <= exclusions or exclusions - grounded - retained:
            raise AllergyEvidenceError("Exclusions contradict explicit known allergy targets")
    elif has_explicit_allergy(message) and not retracted:
        if not exclusions or exclusions - grounded - retained:
            raise AllergyEvidenceError("Unverified allergy target requires clarification")
    elif re.search(r"dị ứng|\ballergic\b", text) and exclusions - retained and not grounded and not retracted:
        raise AllergyEvidenceError("Negated allergy supplies no positive exclusion evidence")
    allergy_only, temporal_only, reference_only = _bounded_evidence_scope(message)
    if allergy_only and update.set_values.get("food") and (form is None or form.food is None):
        raise ValueError("An allergy assertion supplies no food-selection evidence")
    if temporal_only and set(update.context_updates) - {"meal_time"}:
        raise ValueError("A meal-time correction supplies no other context evidence")
    if reference_only:
        form_fields = {key for key in ("food", "cuisine", "location", "budget_max", "max_distance_km")
                       if form is not None and getattr(form, key) is not None}
        if any((set(update.set_values) - form_fields,
                set(containers["hard_constraints"]) - form_fields, containers["soft_preferences"],
                update.context_updates, update.add_semantic_preferences, update.add_negative_preferences,
                update.remove_preferences, update.relative_updates)):
            raise ValueError("A reference selection supplies no attribute evidence")
    from conversation.rule_parser import VEGETARIAN_PATTERN, vegetarian_matches
    if VEGETARIAN_PATTERN.search(text) and not list(vegetarian_matches(text)):
        if any(values.get("vegetarian") is True for values in containers.values()):
            raise ValueError("A negated/conditional/named vegetarian phrase is not dietary evidence")
    if any(key in update.remove_preferences for key in ("allergens_excluded", "hard_constraints.allergens_excluded")):
        retraction = re.search(r"(?:không|chẳng) (?:còn |bị |còn bị )?dị ứng|(?:bỏ|xóa|gỡ) (?:yêu cầu |giới hạn |điều kiện )?dị ứng|\b(?:not|no longer) allergic\b|\bremove (?:the )?allerg", text)
        if not retraction or re.search(r"(?:dị ứng|allergies).*\b(?:giữ nguyên|không đổi|unchanged)\b", text):
            raise ValueError("Allergy removal has no retraction evidence in the current message")
    if "hard_constraints" in update.remove_preferences:
        raise ValueError("Model cannot remove a whole hard-constraint container")
    if (re.fullmatch(r"(?:đi )?xa hơn cũng được[.!? ]*", text)
            and update.relative_updates.get("distance") == "increase"):
        raise ValueError("Permission to travel farther is not a requested increase")
    inferred_budget = any("budget_min" in values or "budget_max" in values
                          and (form is None or form.budget_max is None) for values in containers.values())
    from conversation.grounding import quantities, unitless_budgets, validate_numeric
    food_search = bool(update.set_values.get('food') or form and form.food)
    if (inferred_budget and re.search(r"\brẻ hơn\b|\bcheaper\b", text)
            and not quantities(text, 'budget', food_search=food_search)):
        raise ValueError("Cheaper feedback does not supply an absolute budget")
    if unitless_budgets(text, food_search=food_search):
        for values in containers.values():
            for key in ('budget_min', 'budget_max'):
                if key in values and (form is None or getattr(form, key, None) is None):
                    validate_numeric(key, values[key], text, food_search=food_search)

    # Restrict the check to complete, single bounds. Corrections, alternatives
    # and conditional bounds are handled by the existing rule/model merge.
    if not re.search(r"\b(?:nếu|nếu có thể|hoặc|thực ra|thật ra|if|or|actually)\b", text):
        for key, pattern, factors in (
            ("budget_max", r"\b(?:dưới|không quá|tối đa|under|below)\s+(\d+(?:[.,]\d+)?)\s*(k|nghìn|ngàn|vnd|đồng)\b",
             {"k": 1000, "nghìn": 1000, "ngàn": 1000, "vnd": 1, "đồng": 1}),
            ("max_distance_km", r"\b(?:trong(?: vòng)?|dưới|không quá|tối đa|within|under)\s+(\d+(?:[.,]\d+)?)\s*(km|m|meters?|metres?)\b",
             {"km": 1, "m": Decimal(".001"), "meter": Decimal(".001"), "meters": Decimal(".001"),
              "metre": Decimal(".001"), "metres": Decimal(".001")}),
        ):
            if form is not None and getattr(form, key) is not None:
                continue  # Explicit form values already replaced model values.
            matches = list(re.finditer(pattern, text))
            if len(matches) != 1:
                continue
            match = matches[0]
            if key == "max_distance_km" and re.search(r"\b(?:ngân sách|mức giá|giá|budget)\s+(?:thì\s+)?$", text[:match.start()]):
                if any(key in values for values in containers.values()):
                    raise ValueError("Monetary text is not a distance bound")
            if re.search(r"\b(?:không muốn|không thích|not|don't)\s*$", text[:match.start()]):
                continue
            from conversation.grounding import number
            expected = number(match[1], money=key == "budget_max" and factors[match[2]] == 1) * factors[match[2]]
            for values in containers.values():
                if key in values and Decimal(str(values[key])) != expected:
                    raise ValueError(f"{key} contradicts explicit units/value")
        travel = list(re.finditer(r"\b(?:không quá|tối đa|dưới|at most|under)\s+(\d+)\s*(?:phút|minutes?)\b", text))
        # UserFormInput has no travel-time field; only text supplies this bound.
        if len(travel) == 1:
            for values in containers.values():
                if "max_travel_time_min" in values and values["max_travel_time_min"] != int(travel[0][1]):
                    raise ValueError("Travel time contradicts explicit minutes")

    # A clear dislike is not evidence of an allergy. Do not apply this guard to
    # allergy-bearing turns, where the existing merge retains all exclusions.
    if not re.search(r"dị ứng|\ballerg(?:ic|y|ies)\b", text):
        if re.search(r"không (?:thích|ăn) (?:đậu phộng|lạc|hải sản)|\b(?:don't like|dislike) peanuts?\b", text):
            if any(v.get("allergens_excluded") for v in containers.values()):
                raise ValueError("Dislike/nonconsumption is not allergy evidence")
    allergy_mentions = re.findall(r"dị ứng|\ballerg(?:ic|y|ies)\b", text)
    negated_peanut = re.search(r"\b(?:không|chẳng) (?:bị )?dị ứng (?:đậu phộng|lạc)|\bnot allergic to peanuts?\b", text)
    if len(allergy_mentions) == 1 and negated_peanut:
        if any("peanut" in v.get("allergens_excluded", []) for v in containers.values()):
            raise ValueError("Negated allergy contradicts exclusion")
    # Protect an explicit air-conditioning wish from hard model promotion.
    soft_ac = re.search(r"(?:ưu tiên|thích) (?:có )?(?:điều hòa|máy lạnh)|\bprefer air conditioning\b", text)
    mandatory_ac = re.search(r"\b(?:bắt buộc|phải|nhất thiết) (?:có )?(?:điều hòa|máy lạnh)|\b(?:must|require) (?:have )?air conditioning\b", text)
    if soft_ac and not mandatory_ac:
        if "air_conditioning" in containers["hard_constraints"]:
            raise ValueError("Air-conditioning preference is not mandatory")
