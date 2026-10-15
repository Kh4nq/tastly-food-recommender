"""Conservative Vietnamese baseline parser with explicit, replaceable vocabularies."""

import re
from decimal import Decimal

from common.schemas import Direction, PreferenceUpdate
from conversation._utils import normalize_text, unique
from conversation.models import RuleParseResult
from conversation.normalization import (
    AMBIGUOUS_CUISINE_WORDS, CONSTRAINT_VALUE_ALIASES, CUISINE_ALIASES, SEMANTIC_PHRASES, normalize_update,
)

# Immutable tuples can later be replaced by a dish database adapter.
FOOD_ALIASES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("ramen", ("ramen",)),
    ("phở", ("phở",)),
    ("bún bò", ("bún bò",)),
    ("cơm gà", ("cơm gà",)),
    ("pizza", ("pizza",)),
    ("sushi", ("sushi",)),
)
RELATIVE_RULES: tuple[tuple[str, Direction, str], ...] = (
    ("budget", "decrease", r"rẻ hơn|giá thấp hơn"),
    ("budget", "increase", r"(?:đắt|mắc) (?:hơn(?: (?:một )?chút)?|thêm (?:một )?chút) cũng được"),
    ("distance", "decrease", r"gần hơn"),
)
BUDGET_PATTERN = re.compile(
    r"\b(?:(?:ngân sách|mức giá|giá|budget)\s+(?:thì\s+)?)?"
    r"(?:dưới|không quá|tối đa|budget)\s+(\d+(?:[.,]\d+)?)\s*(k|nghìn|ngàn|vnd|đồng|đ)\b"
)
DISTANCE_PATTERN = re.compile(
    r"\b(?:khoảng cách\s+(?:thì\s+)?)?"
    r"(?:trong(?: vòng)?|dưới|không quá|tối đa|bán kính)\s+(\d+(?:[.,]\d+)?)\s*(km|m)\b"
)
NEGATIVE_SPICY_PATTERN = re.compile(r"\b(?:không (?:muốn ăn|ăn|thích) (?:đồ )?cay|đừng cay)\b")
VEGETARIAN_PATTERN = re.compile(r"\b(?:ăn (?:thuần )?chay|món (?:thuần )?chay|(?:bún riêu|bánh mì|lẩu|phở|bún|cơm|mì)(?: nấm)? (?:thuần )?chay)\b")
NEGATED_PREFIX = re.compile(r"\b(?:không|đừng|chẳng)(?:\s+phải)?(?:\s+(?:muốn|thích|ăn|chọn|tìm|cần|yêu cầu|đồ|chỗ|bị|còn|hề|có))*\s*$")
REMOVAL_TARGETS: tuple[tuple[str, str], ...] = (
    (r"quán đẹp", "beautiful ambience"),
    (r"yên tĩnh", "quiet"),
    (r"(?:ăn|món) chay", "vegetarian"),
    (r"(?:giới hạn )?\d+(?:[.,]\d+)?\s*km|giới hạn khoảng cách", "max_distance_km"),
    (r"rating cao", "rating"),
    (r"(?:giới hạn )?(?:ngân sách|budget)", "budget_max"),
    (r"(?:chỗ )?chill", "relaxed ambience"),
)
REMOVAL_PREFIX = r"(?:không cần|không quan trọng|bỏ(?: yêu cầu)?)\s+"
# Only harmless scaffolding is ignored. Unknown modifiers, conjunctions of
# contrast, conditions, negation and references deliberately remain unresolved.
BENIGN_FILLER_PHRASES = (
    "được không", "giúp mình", "bạn kiếm", "một chút", "quán",
    "cho mình", "cho tôi", "mình muốn", "tôi muốn", "mình chọn", "tôi chọn",
    "hôm nay", "nay", "tôi", "muốn", "tìm", "kiếm cái", "kiếm", "ăn",
    "và", "để", "đi", "chút", "xíu", "thôi", "nhé", "nha",
)
SCAFFOLD = re.compile(
    r"\b(?:" + "|".join(re.escape(p) for p in BENIGN_FILLER_PHRASES) + r")\b"
)
ABSOLUTE_NEAR_PATTERN = re.compile(r"\b(?:quán(?: nào)? )?gần(?: gần| đây)?\b(?!\s+hơn\b)")


def _clean_residue(original: str, spans: list[tuple[int, int]], update: PreferenceUpdate) -> str:
    """Clean each unmatched fragment, never join words across consumed spans.

    Rationale is benign only as a complete clause with a matching decrease.
    Negation, conditions, mandatory modifiers and unknown words survive.
    """
    residual = list(original)
    for start, end in spans:
        residual[start:end] = "\0" * (end - start)
    fragments = re.split(r"\0+|[,.!?;]", "".join(residual))
    cleaned = []
    for fragment in fragments:
        fragment = " ".join(SCAFFOLD.sub(" ", fragment).split())
        dimension = {"xa quá": "distance", "đắt quá": "budget", "mắc quá": "budget"}.get(fragment)
        if dimension and update.relative_updates.get(dimension) == "decrease":
            continue
        cleaned.append(fragment)
    return " ".join(re.sub(r"[^\w\s]", " ", " ".join(cleaned)).split())


def _is_negated(text: str, start: int) -> bool:
    return NEGATED_PREFIX.search(text[:start]) is not None


def vegetarian_matches(text: str):
    """Positive dietary phrases only; names/conditions remain for clarification.

    A bare dish phrase or explicit food request is evidence. A restaurant's
    name, a quoted phrase, or a hypothetical dish is not a dietary commitment.
    """
    for match in VEGETARIAN_PATTERN.finditer(text):
        prefix = re.split(r"[.!?;]", text[:match.start()])[-1]
        suffix = re.split(r"[.!?;]", text[match.end():])[0]
        if _is_negated(text, match.start()):
            continue
        if re.search(r"\b(?:nếu|giả sử|có thể|có lẽ|if|maybe)\b", prefix):
            continue
        if re.search(r"\b(?:không|chẳng|đừng)\s+(?:muốn|thích|ăn|chọn|tìm|cần)(?:\s+\w+){0,3}\s*$", prefix):
            continue
        if re.search(r"\b(?:tên|gọi là|quán|nhà hàng)\s+[\"'“‘]*\s*$", prefix):
            continue
        if prefix.count('"') % 2 or prefix.count('“') > prefix.count('”') or prefix.count("'") % 2:
            continue
        if re.search(r"\b(?:nếu|if|hoặc|or)\b", suffix):
            continue
        yield match


def explicit_allergy_matches(text: str):
    """Only known explicit targets; uncertain/negated clauses remain residual."""
    aliases = CONSTRAINT_VALUE_ALIASES["allergens_excluded"]
    target = "(?:" + "|".join(re.escape(a) for a in sorted(aliases, key=len, reverse=True)) + ")"
    patterns = (rf"\b(?:bị )?dị ứng ({target}(?:\s*(?:,|và|&|and)\s*{target})*)\b",
                rf"\btránh ({target}(?:\s*(?:,|và|&)\s*{target})*) vì (?:bị )?dị ứng\b",
                rf"\bi(?:'m| am) allergic to ({target}(?:\s*(?:,|and|&)\s*{target})*)\b")
    for pattern in patterns:
        for match in re.finditer(pattern, text):
            prefix = re.split(r"[,.!?;]", text[:match.start()])[-1]
            if _is_negated(text, match.start()) or re.search(r"\b(?:nếu|có thể|có lẽ|chưa rõ|if|might|maybe)\b", prefix):
                continue
            yield match, unique(aliases[m[0]] for m in re.finditer(rf"\b{target}\b", match[1]))


def parse_by_rules(message: str) -> PreferenceUpdate:
    """Extract clear preferences; unknown or empty text produces an empty update."""
    return parse_by_rules_detailed(message).update


def parse_by_rules_detailed(message: str) -> RuleParseResult:
    """Track consumed spans; any meaningful residual text requests one LLM pass."""
    text = normalize_text(message)
    update = PreferenceUpdate()
    spans: list[tuple[int, int]] = []

    def consume(match: re.Match[str]) -> None:
        spans.append(match.span())

    for target, key in REMOVAL_TARGETS:
        pattern = rf"\b{REMOVAL_PREFIX}(?:{target})(?: nữa)?(?: đi)?\b"
        for match in re.finditer(pattern, text):
            update.remove_preferences.append(key)
            consume(match)
    for match in re.finditer(r"\bkhông (?:đi xe máy|đi bộ|đi ô tô|đi xe đạp) nữa\b", text):
        update.remove_preferences.append("context.transport_mode")
        consume(match)
    for match in re.finditer(r"\bkhông cần (?:parking|chỗ gửi xe|chỗ đậu xe) nữa\b", text):
        update.remove_preferences.extend(["hard_constraints.parking", "soft_preferences.parking"])
        consume(match)
    # Mask removals before additions so embedded positive phrases cannot fire.
    chars = list(text)
    for start, end in spans:
        chars[start:end] = " " * (end - start)
    text = "".join(chars)

    context_rules = (
        ("transport_mode", "walking", r"(?:có thể )?đi bộ(?: tới)?"),
        ("transport_mode", "motorbike", r"đi xe máy"),
        ("transport_mode", "car", r"đi (?:ô tô|xe hơi)"),
        ("transport_mode", "bicycle", r"đi xe đạp"),
        ("transport_mode", "public_transport", r"đi (?:xe buýt|bus|metro)"),
        ("transport_mode", "ride_hailing", r"(?:đi|đặt|gọi) (?:grab|taxi|xe công nghệ)"),
        ("meal_time", "breakfast", r"(?:sáng nay|bữa sáng)"),
        ("meal_time", "lunch", r"(?:trưa nay|bữa trưa)"),
        ("meal_time", "dinner", r"(?:tối nay|bữa tối)"),
        ("meal_time", "late_night", r"ăn khuya"),
        ("occasion", "date", r"(?:đi date|hẹn hò)"),
        ("occasion", "business", r"(?:tiếp khách|ăn bàn công việc)"),
        ("occasion", "celebration", r"(?:mừng sinh nhật|ăn mừng)"),
        ("occasion", "family", r"bữa ăn gia đình"),
        ("companions", ["partner"], r"(?:đi ăn |ăn )?với (?:bạn gái|bạn trai)"),
        ("companions", ["friends"], r"(?:đi ăn |ăn )?với bạn bè"),
        ("companions", ["family"], r"(?:đi ăn |ăn )?với gia đình"),
        ("companions", ["colleagues"], r"(?:đi ăn |ăn )?với đồng nghiệp"),
    )
    mentions = []
    for key, value, pattern in context_rules:
        if key == "transport_mode":
            # This replacement operator is safe only with a resolved transport.
            pattern = rf"(?:chuyển qua )?(?:{pattern})"
        for match in re.finditer(rf"\b(?:{pattern})\b", text):
            # A coordinated list of occasions shares the explicit negation.
            # Keep this bounded to occasions, not arbitrary intervening text.
            negated_list = key == "occasion" and re.search(
                r"\bkhông phải\s+(?:(?:sinh nhật|mừng sinh nhật|hẹn hò|đi date|ăn mừng)\s+(?:hoặc|hay|và)\s+)+$",
                text[:match.start()],
            )
            if not _is_negated(text, match.start()) and not negated_list:
                mentions.append((match.start(), match.end(), key, value))
                consume(match)
    companion_end = None
    for start, end, key, value in sorted(mentions):
        if key == "companions":
            # List-valued context is additive for explicit conjunctions. Leave
            # corrections/alternatives unresolved; do not erase earlier groups
            # while claiming to understand a simple "with X and with Y".
            if (companion_end is not None
                    and re.fullmatch(r"[\s,]*(?:và[\s,]*)?", text[companion_end:start])):
                value = unique([*update.context_updates[key], *value])
            companion_end = end
        update.context_updates[key] = value
    for match in re.finditer(r"\b(?:nhóm|đi|bàn cho|có) (\d+) người\b", text):
        if int(match[1]) > 0 and not _is_negated(text, match.start()):
            update.context_updates["party_size"] = int(match[1])
            consume(match)
    for match in re.finditer(r"\b(?:không quá|tối đa|dưới) (\d+) phút\b", text):
        if int(match[1]) > 0 and not _is_negated(text, match.start()):
            update.add_hard_constraints["max_travel_time_min"] = int(match[1])
            consume(match)
    for match in re.finditer(r"\bkhông quá xa\b", text):
        if not _is_negated(text, match.start()):
            update.add_soft_preferences["distance"] = "near"
            consume(match)
    for match in re.finditer(r"\b(?:(bắt buộc|phải) )?có (?:parking|chỗ gửi xe|chỗ đậu xe)( thì tốt)?\b", text):
        if not _is_negated(text, match.start()):
            target = update.add_hard_constraints if match[1] else update.add_soft_preferences
            target["parking"] = True
            consume(match)
    for match, allergens in explicit_allergy_matches(text):
        update.add_hard_constraints["allergens_excluded"] = unique([
            *update.add_hard_constraints.get("allergens_excluded", []), *allergens])
        consume(match)
    for match in re.finditer(r"\b(?:ưu tiên|thích) (?:có )?(?:điều hòa|máy lạnh)\b", text):
        if not _is_negated(text, match.start()):
            update.add_soft_preferences["air_conditioning"] = True
            consume(match)
    for match in re.finditer(r"\b(?:bắt buộc|phải) có (?:điều hòa|máy lạnh)\b", text):
        if not _is_negated(text, match.start()):
            update.add_hard_constraints["air_conditioning"] = True
            consume(match)
    for match in re.finditer(r"\bkhông thích (?:đậu phộng|lạc)\b", text):
        update.add_negative_preferences.append("peanut")
        consume(match)

    # Last explicit mention wins within the message.
    for match in BUDGET_PATTERN.finditer(text):
        if _is_negated(text, match.start()):
            continue
        amount = Decimal(match[1].replace(",", "."))
        multiplier = 1000 if match[2] in ("k", "nghìn", "ngàn") else 1
        vnd = amount * multiplier
        if vnd == vnd.to_integral_value():
            update.add_hard_constraints["budget_max"] = int(vnd)
            consume(match)
            prefix = re.search(r"\b(?:phải|bắt buộc)\s+$", text[:match.start()])
            if prefix:
                consume(prefix)
    for match in DISTANCE_PATTERN.finditer(text):
        distance = float(Decimal(match[1].replace(",", ".")) / (1000 if match[2] == "m" else 1))
        money_prefix = re.search(r"\b(?:ngân sách|mức giá|giá|budget)\s+(?:thì\s+)?$", text[:match.start()])
        if distance > 0 and not money_prefix and not _is_negated(text, match.start()):
            update.add_hard_constraints["max_distance_km"] = distance
            consume(match)
            prefix = re.search(r"\b(?:phải|bắt buộc)\s+$", text[:match.start()])
            if prefix:
                consume(prefix)

    relative_mentions: list[tuple[int, str, Direction]] = []
    for dimension, direction, pattern in RELATIVE_RULES:
        for match in re.finditer(rf"\b(?:{pattern})\b", text):
            if not _is_negated(text, match.start()):
                relative_mentions.append((match.start(), dimension, direction))
                consume(match)
    for _, dimension, direction in sorted(relative_mentions):
        update.relative_updates[dimension] = direction

    for match in ABSOLUTE_NEAR_PATTERN.finditer(text):
        if any(match.start() < end and start < match.end() for start, end in spans):
            continue
        if not _is_negated(text, match.start()):
            update.add_soft_preferences["distance"] = "near"
            consume(match)

    for match in NEGATIVE_SPICY_PATTERN.finditer(text):
        update.add_negative_preferences.append("spicy")
        consume(match)
    # Serving requests describe food, never a drink just because it is liquid.
    serving_mentions = []
    for pattern, kind, styles in (
        (r'\b(?:món nước|mon nuoc)\b', 'food', ['broth', 'soup']),
        (r'\b(?:món khô|mon kho)\b', 'food', ['dry']),
        (r'\b(?:đồ uống|do uong|nước uống|nuoc uong|uống nước|uong nuoc)\b', 'beverage', None),
    ):
        for match in re.finditer(pattern, text):
            if not _is_negated(text, match.start()):
                serving_mentions.append((match.start(), kind, styles))
                consume(match)
    for _, kind, styles in sorted(serving_mentions):
        update.add_hard_constraints['item_kind'] = kind
        update.set_values['food'] = []
        if styles is not None:
            update.add_hard_constraints['serving_style'] = styles
            update.remove_preferences = [k for k in update.remove_preferences if k != 'hard_constraints.serving_style']
        else:
            update.add_hard_constraints.pop('serving_style', None)
            update.remove_preferences.append('hard_constraints.serving_style')

    vegetarian_foods = []
    for match in vegetarian_matches(text):
        update.add_hard_constraints["vegetarian"] = True
        if re.match(r"(?:bánh mì|lẩu|phở|bún|cơm|mì)\b", match[0]):
            vegetarian_foods.append((match.start(), match[0], match.span()))
        consume(match)

    foods: list[tuple[int, str]] = [(start, food) for start, food, _ in vegetarian_foods]
    for canonical, aliases in FOOD_ALIASES:
        for alias in aliases:
            # Category nouns belong to this recognized dish span, never to
            # global filler ("món lạ" must still request interpretation).
            for match in re.finditer(rf"\b(?:món(?: ăn)?\s+)?{re.escape(alias)}\b", text):
                if any(start <= match.start() < end or match.start() <= start < match.end()
                       for _, _, (start, end) in vegetarian_foods):
                    continue  # Preserve the explicitly requested vegetarian dish.
                # Feedback on a displayed dish is a reference, not a new food
                # selection. Leave it unresolved for the normal model route.
                displayed = re.match(r"\s+(?:trong kết quả|ở vị trí (?:đầu|\d+))\b", text[match.end():])
                requested = re.search(r"\b(?:tìm|muốn ăn|đổi sang|chọn)\s+$", text[:match.start()])
                if displayed and not requested:
                    continue
                if not _is_negated(text, match.start()):
                    foods.append((match.start(), canonical))
                    consume(match)
    if foods:
        update.set_values["food"] = unique(food for _, food in sorted(foods))
    cuisine_pattern = r"\b(?:" + "|".join(
        re.escape(alias) for alias in sorted(CUISINE_ALIASES, key=len, reverse=True)
    ) + r")\b"
    cuisines = []
    for match in re.finditer(cuisine_pattern, text):
        if re.search(r"\b(?:tên|tên gọi)\s+$", text[:match.start()]):
            continue
        food_origin = match[0] == "nhật" and any(
            re.search(rf"\b{re.escape(alias)}\s+$", text[:match.start()])
            for _, aliases in FOOD_ALIASES for alias in aliases
        )
        if (match[0] in AMBIGUOUS_CUISINE_WORDS
                and normalize_text(message).strip(".!? ") != match[0] and not food_origin):
            continue
        if not _is_negated(text, match.start()):
            cuisines.append(match[0])
            consume(match)
    if cuisines:
        update.set_values["cuisine"] = cuisines
    for phrase, meaning in SEMANTIC_PHRASES:
        for match in re.finditer(rf"\b{re.escape(phrase)}\b", text):
            if not _is_negated(text, match.start()):
                update.add_semantic_preferences.append(meaning)
                consume(match)
    update.remove_preferences = unique(update.remove_preferences)
    update.add_semantic_preferences = unique(
        value for value in update.add_semantic_preferences if value not in update.remove_preferences
    )
    update.add_negative_preferences = unique(update.add_negative_preferences)
    for key in update.remove_preferences:
        update.add_hard_constraints.pop(key, None)
    original = normalize_text(message)
    unresolved = _clean_residue(original, spans, update)
    # Scaffolding alone is not evidence of understanding a nonempty message.
    requires_llm = bool(unresolved or (original and not spans))
    return RuleParseResult(
        update=normalize_update(update), requires_llm=requires_llm,
        matched_spans=unique(original[start:end] for start, end in sorted(spans)),
        unresolved_text=unresolved or (original if requires_llm else None),
        confidence=None,
    )
