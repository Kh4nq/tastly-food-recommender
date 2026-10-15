"""Bounded production acceptance checks; existing parser/state contracts stay authoritative."""
from copy import deepcopy
import re

from common.schemas import PreferenceUpdate
from conversation._utils import normalize_text
from conversation.evidence import AllergyEvidenceError, has_explicit_allergy, validate_explicit_evidence
from conversation.normalization import canonical_constraints, CONSTRAINT_VALUE_ALIASES, CUISINE_ALIASES
from conversation.rule_parser import explicit_allergy_matches, _is_negated
from conversation.state_manager import update_state

ALLERGY_PATHS = {"allergens_excluded", "hard_constraints.allergens_excluded"}
NOOP = re.compile(r"(?:ok(?:ay)?|ừ|ừm|cảm ơn(?: bạn)?|thanks|thank you|được rồi)(?:[ ,.!]+(?:ok|cảm ơn(?: bạn)?|thanks))*[ .!]*")
KEY_EVIDENCE = {
    "wifi": r"wi[ -]?fi", "parking": r"parking|gửi xe|đậu xe|đỗ xe",
    "vegetarian": r"chay|vegetarian|vegan|\bveg\b", "air_conditioning": r"máy lạnh|điều hòa|air conditioning|\bac\b",
    "max_travel_time_min": r"phút|minutes?|thời gian", "max_distance_km": r"km\b|kilomet(?:er|re)s?\b|khoảng cách|cây số|\d+\s*m\b",
    "budget_max": r"ngân sách|budget|giá|\d+\s*(?:k|nghìn|ngàn|đồng)",
    "budget_min": r"ngân sách|budget|giá|\d+\s*(?:k|nghìn|ngàn|đồng)",
    "transport_mode": r"xe|đi bộ|walking|motorbike|taxi|grab|bus|metro|\bcar\b|bicycle",
    "requested_accompaniments": r"chén trứng|with|kèm|thêm",
    "meal_time": r"sáng|trưa|tối|khuya|breakfast|lunch|dinner",
    "party_size": r"\d+\s*(?:người|people)", "companions": r"với|with|một mình|alone",
    "occasion": r"hẹn hò|date|sinh nhật|gia đình|family|công việc|business|celebrat",
    "quiet": r"yên tĩnh|quiet",
    "item_kind": r"món nước|mon nuoc|món khô|mon kho|đồ ăn|food|đồ uống|do uong|nước uống|nuoc uong|uống nước|drink|beverage",
    "serving_style": r"món nước|mon nuoc|món khô|mon kho|broth|soup|dry|hotpot|lẩu",
}


def is_noop(message):
    return NOOP.fullmatch(normalize_text(message)) is not None


def allergy_retraction_targets(message):
    """Only named, unconditional targets; no inference from a bare pronoun/list clear."""
    text = normalize_text(message)
    removal = re.search(r"không còn|bỏ|xóa|gỡ|remove|no longer", text)
    if not removal or not re.search(r"dị ứng|allerg", text):
        if re.search(r"từng dị ứng|used to be allergic", text):
            raise AllergyEvidenceError("Historical allergy needs a current confirmation or named retraction")
        return set()
    if re.search(r"dị ứng.*(?:giữ nguyên|không đổi)|giữ nguyên dị ứng", text):
        return set()  # e.g. Wi-Fi correction explicitly retaining allergies.
    aliases = CONSTRAINT_VALUE_ALIASES["allergens_excluded"]
    target = "(?:" + "|".join(re.escape(a) for a in sorted(aliases, key=len, reverse=True)) + ")"
    found = set()
    patterns = (
        rf"(?:không còn (?:bị )?dị ứng|(?:bỏ|xóa|gỡ) (?:yêu cầu |ràng buộc |giới hạn )?dị ứng)\s+({target})\b",
        rf"\b(?:no longer allergic to|remove (?:the )?allergy (?:to|for))\s+({target})\b",
        rf"\btừng dị ứng\s+({target})\b[^.!?;]*\bđã hết\b[^.!?;]*\bbỏ ràng buộc đó\b",
    )
    for pattern in patterns:
        found.update(aliases[m[1]] for m in re.finditer(pattern, text) if not _is_negated(text, m.start()))
    if not found or re.search(r"\b(?:nếu|có thể|có lẽ|if|maybe)\b|đừng bỏ|không (?:muốn )?bỏ", text):
        raise AllergyEvidenceError("Ambiguous allergy retraction")
    # Coordinated/competing targets need explicit policy, not a partial deletion.
    mentions = {aliases[m[0]] for m in re.finditer(rf"\b{target}\b", text)}
    if mentions != found:
        raise AllergyEvidenceError("Mixed allergy retraction needs clarification")
    return found


def confirmed_allergens(state):
    return set(canonical_constraints(state.hard_constraints).get("allergens_excluded", [])) if state else set()


def validate_model_delta(update, request, message, retracted, *, evidence=None):
    text = normalize_text(message)
    from conversation.grounding import quoted_evidence, validate_numeric, validate_coordinates, food_quote_supports
    quotes = quoted_evidence(evidence, message)
    from conversation.reference_resolver import REFERENCE_PATTERN, resolve_message_references
    context_text = REFERENCE_PATTERN.sub(" ", text)
    prior = confirmed_allergens(request.current_state)
    explicit = {a for _, targets in explicit_allergy_matches(text) for a in targets} - retracted
    hard = canonical_constraints({**update.set_values.get("hard_constraints", {}), **update.add_hard_constraints})
    added = set(hard.get("allergens_excluded", []))
    if added - prior - explicit - retracted:
        raise AllergyEvidenceError("Allergen lacks verified positive evidence")
    if set(update.remove_preferences) & ALLERGY_PATHS and not retracted:
        raise AllergyEvidenceError("Unscoped allergy removal")
    if "hard_constraints" in update.remove_preferences:
        raise AllergyEvidenceError("Whole constraint removal is unsupported")
    if evidence is not None and update.set_values.get("food") == [] and request.form.food is None and not re.search(
            r"bỏ|xóa|không cần|món nào cũng|anything|any food|whatever|clear|remove|forget|món nước|mon nuoc|món khô|mon kho|đồ uống|do uong|nước uống|nuoc uong|drink|beverage", text):
        raise ValueError("Clearing food needs an explicit removal or category switch")
    for food in update.set_values.get("food", []):
        if request.form.food is not None:
            continue  # The authoritative form replaces this field before commit.
        normalized = normalize_text(food)
        start = text.find(normalized)
        if start < 0 and not food_quote_supports(food, quotes.get("food", [])):
            raise ValueError("Food lacks a supporting source span")
        if start >= 0 and (_is_negated(text, start) or re.search(r"(?:not|no|don't want|do not want)\s*$", text[:start])):
            raise ValueError("Food is ungrounded or negated")
        if re.search(r"ăn .*bình thường|ăn được", text) and not re.search(r"muốn|tìm|chọn|cho mình", text):
            raise ValueError("Tolerance is not a food request")
    if request.form.cuisine is None:
        for cuisine in update.set_values.get("cuisine", []):
            names = [normalize_text(cuisine), *[alias for alias, value in CUISINE_ALIASES.items() if value == cuisine]]
            if not quotes.get("cuisine") and not any(re.search(rf"\b{re.escape(name)}\b", text) for name in names):
                raise ValueError("Cuisine lacks evidence")
    location = update.set_values.get("location")
    if location and request.form.location is None:
        validate_coordinates(location, text)
    for values in (hard, update.context_updates):
        for key, value in values.items():
            if key == "allergens_excluded":
                continue
            if getattr(request.form, key, None) is not None:
                continue
            if key == 'vegetarian' and request.form.food is not None:
                foods = [request.form.food] if isinstance(request.form.food, str) else request.form.food
                if value is True and any(re.search(r'\b(?:chay|vegetarian|vegan)\b', normalize_text(f)) for f in foods):
                    continue
            if evidence is not None:
                validate_numeric(key, value, text, food_search=bool(update.set_values.get('food') or request.form.food or request.current_state and request.current_state.food))
            pattern = KEY_EVIDENCE.get(key, re.escape(key.replace("_", " ")))
            evidence_text = context_text if key in {"companions", "party_size"} else text
            # Context is model-interpreted; exact source quotes support synonyms
            # without claiming a new regex for every possible expression.
            supported_context = values is update.context_updates and quotes.get("context." + key)
            numeric = evidence is not None and key in {"budget_min", "budget_max", "max_distance_km", "max_travel_time_min"}
            if not supported_context and not numeric and not re.search(pattern, evidence_text):
                raise ValueError("Field lacks textual evidence")
            matches = list(re.finditer(pattern, text))
            if value is True and matches and all(_is_negated(text, m.start()) or
                    re.search(r"(?:not|no|without|don't want|do not want)\s*$", text[:m.start()]) for m in matches):
                raise ValueError("Positive constraint contradicts explicit negation")
    modes = {"walking": r"đi bộ|walking", "motorbike": r"xe máy|motorbike", "car": r"ô tô|xe hơi|car",
             "bicycle": r"xe đạp|bicycle", "public_transport": r"buýt|bus|metro", "ride_hailing": r"grab|taxi"}
    mode = update.context_updates.get("transport_mode")
    if mode in modes and not re.search(modes[mode], text):
        raise ValueError("Transport mode lacks matching evidence")
    for side in update.context_updates.get('requested_accompaniments', []):
        start = text.find(normalize_text(side)) if isinstance(side, str) else -1
        if start < 0 or _is_negated(text, start):
            raise ValueError('Accompaniment lacks positive source evidence')
    if "max_distance_km" in hard and re.search(r"(?:không phải|not)\s+(?:trong\s+|within\s+)?\d+\s*km\b", text):
        if len(re.findall(r"\d+\s*km\b", text)) == 1:
            raise ValueError("Negated distance is not a travel-time bound")
    for key in ("wifi", "parking", "air_conditioning", "quiet"):
        if key not in hard:
            continue
        target = KEY_EVIDENCE[key]
        mandatory = re.search(rf"(?:bắt buộc|phải|cần|must|require|need)[^,.;!?]{{0,20}}(?:{target})", text)
        soft = re.search(rf"(?:ưu tiên|thích|prefer)[^,.;!?]{{0,20}}(?:{target})|(?:{target})\s*(?:thì tốt|would be nice)", text)
        removal = re.search(rf"(?:không cần|bỏ(?: yêu cầu)?)[^,.;!?]{{0,15}}(?:{target})", text)
        if hard[key] is False and (mandatory or removal) or soft and not mandatory or key == "quiet" and not mandatory:
            raise ValueError("Facility constraint strength contradicts evidence")
    for ref in update.references:
        if any(key in ref for key in ("restaurant_id", "menu_item_id")):
            raise ValueError("Provider IDs must come from the deterministic resolver")
        if ref.get("mention") and normalize_text(str(ref["mention"])) not in text:
            raise ValueError("Reference mention lacks evidence")
        if ref.get("rank") is not None and not any(r.get("status") == "resolved" and r.get("rank") == ref["rank"]
                for r in resolve_message_references(message, request.previous_results)):
            raise ValueError("Reference rank lacks a grounded selector")
        if ref.get("sentiment") and not re.search(r"thích|ghét|ổn|ngon|tệ|like|dislike|good|bad", text):
            raise ValueError("Reference sentiment lacks evidence")
        if ref.get("sentiment") == "positive" and re.search(r"không thích|ghét|dislike|not like", text):
            raise ValueError("Reference sentiment contradicts feedback")
    for dimension, direction in update.relative_updates.items():
        cue = {("budget", "decrease"): r"rẻ hơn|giá thấp hơn|cheaper", ("budget", "increase"): r"đắt|mắc|more expensive",
               ("distance", "decrease"): r"gần hơn|closer", ("distance", "increase"): r"xa hơn|farther|further"}.get((dimension, direction))
        if cue is None or not re.search(cue, text):
            raise ValueError("Relative direction lacks evidence")
    if set(update.remove_preferences) & {"food", "cuisine"} and not re.search(r"bỏ|xóa|không cần|remove|clear", text):
        raise ValueError("Food/cuisine removal lacks evidence")


def scope_allergy_removal(candidate, request, retracted):
    result = candidate.model_copy(deep=True)
    if not retracted:
        return result
    if result.relative_updates:
        # A complete hard-container replacement would make existing absolute
        # bounds suppress relative events under the authoritative normalizer.
        raise AllergyEvidenceError("Combined retraction/relative update needs clarification")
    existing = canonical_constraints(deepcopy(request.current_state.hard_constraints)) if request.current_state else {}
    remaining = [a for a in existing.get("allergens_excluded", []) if a not in retracted]
    existing["allergens_excluded"] = remaining
    result.remove_preferences = [p for p in result.remove_preferences if p not in ALLERGY_PATHS]
    # State Manager supports replacement containers; additions alone would union
    # the removed target back in. Include ALL previous constraints in this snapshot.
    result.add_hard_constraints.pop("allergens_excluded", None)
    existing.update(result.set_values.get("hard_constraints", {}))
    existing["allergens_excluded"] = remaining
    result.set_values["hard_constraints"] = existing
    return result


def validate_candidate(candidate, request, message, retracted, *, evidence=None):
    prior = confirmed_allergens(request.current_state)
    if not retracted and has_explicit_allergy(message) and not list(explicit_allergy_matches(normalize_text(message))):
        # Repeating a prior exclusion cannot resolve a newly unnamed allergen.
        raise AllergyEvidenceError("Unverified allergy target needs clarification")
    validate_explicit_evidence(candidate, message, form=request.form,
                              retained_allergens=prior - retracted, retracted_allergens=retracted)
    state = update_state(request.current_state, candidate, request.session_id, request.user_id)
    beverage_switch = candidate.add_hard_constraints.get("item_kind") == "beverage"
    if evidence is not None and beverage_switch and state.hard_constraints.get("serving_style"):
        raise ValueError("A beverage switch must clear the previous food serving style")
    if not prior - retracted <= confirmed_allergens(state):
        raise AllergyEvidenceError("Unrelated confirmed allergy was lost")
    if retracted & confirmed_allergens(state):
        raise AllergyEvidenceError("Retraction was not scoped correctly")
    from conversation.reference_resolver import resolve_message_references
    text = normalize_text(message)
    for ref in resolve_message_references(message, request.previous_results):
        mention = re.escape(normalize_text(ref.get("mention", "")))
        if ref.get("status") == "resolved" and re.search(
            rf"(?:không thích|ghét)\s+{mention}|{mention}\s+(?:mình |tôi )?(?:không thích|tệ|không ngon)", text):
            if not any(r.get("restaurant_id") == ref["restaurant_id"] and r.get("sentiment") == "negative" for r in candidate.references):
                raise ValueError("Explicit reference feedback was lost")
    if request.current_state:
        for key, value in request.current_state.hard_constraints.items():
            if key == "allergens_excluded" or state.hard_constraints.get(key) == value:
                continue
            if getattr(request.form, key, None) is not None:
                continue
            if evidence is not None and key == "serving_style" and beverage_switch:
                continue
            if key == 'vegetarian' and request.form.food is not None and state.hard_constraints.get(key) is True:
                foods = [request.form.food] if isinstance(request.form.food, str) else request.form.food
                if any(re.search(r'\b(?:chay|vegetarian|vegan)\b', normalize_text(f)) for f in foods):
                    continue
            pattern = KEY_EVIDENCE.get(key, re.escape(key.replace("_", " ")))
            if evidence is not None and key in candidate.add_hard_constraints and key in {
                    "budget_min", "budget_max", "max_distance_km", "max_travel_time_min"}:
                from conversation.grounding import validate_numeric
                validate_numeric(key, candidate.add_hard_constraints[key], normalize_text(message),
                    food_search=bool(state.food))
                continue  # Semantic wording need not repeat the canonical field name.
            if not re.search(pattern, normalize_text(message)) and getattr(request.form, key, None) is None:
                raise ValueError("Unrequested hard-constraint mutation")
    return state
