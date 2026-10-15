"""Conservative input edits and optional, injectable English translation.

No SDKs, models, datasets or provider clients are loaded here. Detection is a
precision-oriented heuristic, not a calibrated language probability. A rejected
translation leaves the caller's text available to the usual parsing fallback.
"""

from dataclasses import dataclass
import re
from typing import Protocol
import unicodedata

from common.schemas import UserRequest
from conversation.config import ConversationConfig


class Translator(Protocol):
    def translate(self, text: str, *, source_language: str, target_language: str) -> str:
        """Translate text, preserving every AI2KEEP token exactly once, in order."""
        ...


@dataclass(frozen=True)
class PreparedInput:
    original_message: str | None
    message: str
    input_normalized: bool = False
    translation_attempted: bool = False
    translation_succeeded: bool = False
    translation_error: str | None = None


NAME_PASSTHROUGH = frozenset("""
    find a an the restaurant restaurants place something food dish dishes eat
    i i'm i'd i've am would want like prefer please me my we we're us our to for
    with without and but or not don't doesn't do no never avoid dislike under
    over below above within at most less than budget distance quiet noisy spicy
    air conditioning conditioned must require mandatory need have has be is are
    allergic allergy allergies peanuts peanut shellfish seafood milk eggs egg
    near in on from of by second first third fourth fifth cheaper closer more
    expensive similar this that it one two three four five some any can could
    should good nice beautiful relaxed ambience atmosphere conversation suitable
    breakfast lunch dinner tonight today tomorrow friends family partner alone
    walking parking wifi vegetarian japanese korean chinese vietnamese thai
    italian western vnd km kilometers kilometer metres meters meter minutes
    minute dollars dollar usd dong thousand k ac hot prefer rather get show
    recommend looking vegan cheap halal
""".lower().split())
# These tokens disambiguate capitalized grammar/known cues from possible names.
# They are never used as a closed English dictionary or a coverage threshold.
SENTENCE_STARTERS = frozenset("cho giúp mình tôi em anh chị mún".split())
WORDS = re.compile(r"[^\W\d_]+(?:['’][^\W\d_]+)?", re.UNICODE)
VIETNAMESE_MARKERS = frozenset("cho mik minh toi muon mun tim quan khong thich voi yen tinh xiu".split())
LITERALS = ("ramen", "sushi", "pizza", "phở", "bún bò", "bánh xèo", "bun cha")


def _has_vietnamese_text(text: str) -> bool:
    words = WORDS.findall(text.lower().replace("’", "'"))
    return (any(w in VIETNAMESE_MARKERS for w in words)
            or bool(re.search(r"\b(?:an chay|an voi|di voi)\b", text, re.I))
            or any(ord(c) > 127 and c.isalpha() for c in unicodedata.normalize("NFC", text)))


def _entity_payloads(message: str) -> list[tuple[int, int]]:
    """Protect bounded dish/location slots, without guessing their translation."""
    spans = []
    for pattern in (
        r"\b(?:find|want|eat)\s+(?P<name>.+?)\s+(?:under|below|within|near|at)\b",
        r"\b(?:near|at|in)\s+(?P<name>.+?)(?=\s+(?:under|below|within|with)\b|[.!?;]|$)",
    ):
        for match in re.finditer(pattern, message, re.I):
            name = match["name"]
            # A bounded payload alone is not proof of a name. Keep uncertain
            # Vietnamese visible to language detection; explicit quotes,
            # caller-supplied names and established dishes are protected later.
            if _has_vietnamese_text(name):
                continue
            if not re.search(r"\b(?:a|an|the|some|restaurant|restaurants|place|food)\b", name, re.I):
                spans.append(match.span("name"))
    return spans


def _protected_spans(message: str, request: UserRequest) -> list[tuple[int, int]]:
    """Protect quotes, supplied names, dish names, numbers/units and proper names."""
    names = list(LITERALS)
    for result in request.previous_results:
        names.extend(n for n in (result.restaurant_name, result.dish_name) if n)
    for source in (request.form, request.current_state):
        if source is not None:
            value = source.food
            names.extend([value] if isinstance(value, str) else value or [])
    spans = _entity_payloads(message)
    for name in names:
        spans.extend(m.span() for m in re.finditer(rf"(?<!\w){re.escape(name)}(?!\w)", message, re.I))
    patterns = (
        r'"[^"\n]+"|“[^”\n]+”|‘[^’\n]+’',
        r"(?<!\w)(?:[$€£₫]\s*|(?:usd|vnd|eur)\s+)?\d+(?:[.,]\d+)*(?:\s*(?:k\b|km\b|m\b|vnd\b|usd\b|eur\b|đồng\b|dollars?\b|meters?\b|metres?\b|minutes?\b))?",
        r"\b[A-ZĐ][\w-]*(?:\s+(?:[A-ZĐ][\w-]*|\d+))*\b",
    )
    for pattern in patterns:
        for match in re.finditer(pattern, message, re.I if pattern == patterns[1] else 0):
            if pattern == patterns[-1]:
                words = WORDS.findall(match[0].lower())
                if (all(w in NAME_PASSTHROUGH for w in words)
                        or match.start() == len(message) - len(message.lstrip())
                        and len(words) == 1 and words[0] in SENTENCE_STARTERS):
                    continue
            spans.append(match.span())
    # Merge overlapping spans, preserving every original character on restoration.
    merged = []
    for start, end in sorted(spans):
        if merged and start < merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    return merged


def normalize_vietnamese_input(message: str, request: UserRequest) -> str:
    protected = _protected_spans(message, request)
    edits = []
    for pattern, replacement in (
        (r"\b(cho|giúp) mik\b", r"\1 mình"),
        (r"\b(mình|tôi|em|anh|chị) mún(?=\s+(?:ăn|tìm|quán|món|có)\b)", r"\1 muốn"),
        (r"^mún(?=\s+(?:ăn|tìm|quán|món|có)\b)", "muốn"),
        (r"\b(quán|không gian|chỗ)(\s+(?:(?:rất|thật)\s+)?)yên tĩn\b", r"\1\2yên tĩnh"),
    ):
        for match in re.finditer(pattern, message, re.I):
            if not any(match.start() < end and start < match.end() for start, end in protected):
                edits.append((match.start(), match.end(), match.expand(replacement)))
    for start, end, value in sorted(edits, reverse=True):
        message = message[:start] + value + message[end:]
    return message


def _mask(message: str, spans: list[tuple[int, int]]) -> tuple[str, dict[str, str]]:
    parts, literals, offset = [], {}, 0
    for index, (start, end) in enumerate(spans):
        token = f"AI2KEEP{index}X"
        parts.extend((message[offset:start], token))
        literals[token] = message[start:end]
        offset = end
    parts.append(message[offset:])
    return "".join(parts), literals


def is_confident_english(text: str) -> bool:
    """Skip short dish mentions, Vietnamese and uncertain mixed-language input."""
    text = re.sub(r"AI2KEEP\d+X", " entity ", text)
    words = WORDS.findall(text.lower().replace("’", "'"))
    if len(words) < 3 or _has_vietnamese_text(text):
        return False
    # Grammatical anchors permit unfamiliar English descriptors and protected
    # dish/location payloads. Ambiguous fragments have no strong anchor.
    return bool(re.match(
        r"^\s*(?:please\s+)?(?:"
        r"(?:find|recommend|show(?: me)?)\s+(?:(?:a|an|the|some|something|food|restaurants?)\b|.+?\s+(?:under|below|within|near|at)\b)"
        r"|i(?:'m| am)\s+(?:not\s+)?allergic\s+to\b"
        r"|i(?:'d| would)?\s+(?:want|prefer|like|don't like|must have|need|require)\b"
        r")", text, re.I))


NEGATION = (r"\b(?:don't|doesn't|not|no|never|without|avoid|dislike)\b",
            r"\b(?:không(?!\s+(?:gian|khí)\b)|đừng|tránh|chẳng)\b")
OBLIGATION = (r"\b(?:must|mandatory|require|required)\b", r"\b(?:bắt buộc|phải|nhất thiết)\b")
PREFERENCE = (r"\b(?:prefer|i (?:don't )?like)\b", r"\b(?:ưu tiên|thích|thì tốt)\b")
CLAUSES = re.compile(r"[.!?;]|\b(?:but|nhưng|and i|và tôi)\b", re.I)
ALLERGENS = {
    "peanut": (("peanut", "peanuts"), ("đậu phộng", "lạc")),
    "shellfish": (("shellfish",), ("động vật có vỏ", "hải sản có vỏ")),
    "seafood": (("seafood",), ("hải sản",)),
    "milk": (("milk",), ("sữa",)),
    "egg": (("egg", "eggs"), ("trứng",)),
    "soy": (("soy", "soybeans"), ("đậu nành", "đậu tương")),
    "wheat": (("wheat",), ("lúa mì",)),
    "sesame": (("sesame",), ("mè", "vừng")),
    "fish": (("fish",), ("cá",)),
}


def _allergy_signature(text: str, language: str):
    """Return target/polarity tuples, or None for unverified allergy syntax.

    The bounded allergy vocabulary is a safety check, not a shared schema or
    language dictionary. Unknown targets/conditions retain untranslated input.
    """
    text = text.lower().replace("’", "'")
    cue = r"\ballerg(?:ic|y|ies)\b" if language == "en" else r"dị ứng"
    if not re.search(cue, text):
        return []
    if re.search(r"\b(?:might|maybe|possibly|could|unless|if)\b|có thể|có lẽ|\bnếu\b", text):
        return None
    pattern = (r"\bi(?:'m| am)\s+(?P<neg>not\s+)?allergic to\s+(?P<targets>.+)" if language == "en" else
               r"(?P<neg>không\s+|chẳng\s+)?(?:bị\s+)?dị ứng\s+(?:với\s+)?(?P<targets>.+)")
    aliases = {alias: key for key, names in ALLERGENS.items()
               for alias in (names[0] if language == "en" else (*names[0], *names[1]))}
    signature = []
    for clause in CLAUSES.split(text):
        if not re.search(cue, clause):
            continue
        match = re.search(pattern, clause.strip())
        if not match or len(re.findall(cue, clause)) != 1:
            return None
        targets = [part.strip(' \t\n"“”‘’\'') for part in re.split(r",|\band\b|\bvà\b", match["targets"])]
        if not targets or any(target not in aliases for target in targets):
            return None
        signature.append((bool(match["neg"]), tuple(sorted(aliases[target] for target in targets))))
    return signature


def _structured_signature(text: str, language: str):
    """Keep known meals/facilities bound to their clause's polarity/modality."""
    index = 0 if language == "en" else 1
    atoms = (
        ("breakfast", r"\bbreakfast\b", r"\b(?:bữa sáng|ăn sáng)\b"),
        ("lunch", r"\blunch\b", r"\b(?:bữa trưa|ăn trưa)\b"),
        ("dinner", r"\bdinner\b", r"\b(?:bữa tối|ăn tối)\b"),
        ("tonight", r"\btonight\b", r"\btối nay\b"),
        ("air_conditioning", r"\bair conditioning\b", r"\b(?:điều hòa|máy lạnh)\b"),
        ("parking", r"\bparking\b", r"\b(?:parking|chỗ gửi xe|chỗ đậu xe|chỗ đỗ xe)\b"),
    )
    signature = []
    for clause in CLAUSES.split(text.lower().replace("’", "'")):
        negative = bool(re.search(NEGATION[index], clause))
        mandatory = bool(re.search(OBLIGATION[index], clause))
        preferred = bool(re.search(PREFERENCE[index], clause))
        if mandatory and preferred and any(re.search(atom[index + 1], clause) for atom in atoms):
            return None  # Do not guess the scope of conflicting modalities.
        for key, *patterns in atoms:
            if re.search(patterns[index], clause):
                signature.append((key, negative, mandatory, preferred))
    return signature


def _restore(text: str, literals: dict[str, str]) -> str:
    for token, literal in literals.items():
        text = text.replace(token, literal)
    return text


def _translation_valid(source: str, translated: str, literals: dict[str, str]) -> bool:
    if not isinstance(translated, str) or not translated.strip() or translated == source:
        return False
    tokens = re.findall(r"AI2KEEP\d+X", translated)
    if tokens != list(literals):
        return False
    clean = re.sub(r"AI2KEEP\d+X", " ", translated).lower()
    # New numbers/currencies outside protected literals are not accepted.
    if re.search(r"\d|\b(?:usd|vnd|vnđ|đồng|đô la|dollars?|euros?|km|meters?|metres?|kilomet(?:er|re)s?)\b|[$€£₫]", clean):
        return False
    if any(re.search(rf"(?<!\w){re.escape(name)}(?!\w)", clean) for name in LITERALS):
        return False  # Supplied dish names should only arrive through literals.
    if not any(ord(c) > 127 and c.isalpha() for c in clean):
        return False
    source = source.lower().replace("’", "'")
    # Compare allergen identity with its own polarity, not a global boolean.
    allergy_source = _allergy_signature(_restore(source, {k.lower(): v for k, v in literals.items()}), "en")
    allergy_target = _allergy_signature(_restore(translated, literals), "vi")
    if allergy_source is None or allergy_target is None or allergy_source != allergy_target:
        return False
    structured_source = _structured_signature(source, "en")
    structured_target = _structured_signature(clean, "vi")
    if structured_source is None or structured_target is None or structured_source != structured_target:
        return False
    # Bidirectional cue checks catch observable losses/additions; they cannot
    # prove arbitrary translation semantics. Unclear translations fail closed.
    cues = (
        (r"\b(?:allergic|allergy|allergies)\b", r"dị ứng"),
        (r"\bpeanuts?\b", r"\b(?:đậu phộng|lạc|peanuts?)\b"),
        (r"\bspicy\b", r"\bcay\b"),
        (r"\bquiet\b", r"\byên (?:tĩnh|ắng)\b"),
        (r"\bair conditioning\b", r"\b(?:điều hòa|máy lạnh)\b"),
        NEGATION,
        OBLIGATION,
        PREFERENCE,
        (r"\b(?:under|below|less than)\b", r"\b(?:dưới|thấp hơn)\b"),
        (r"\bcheaper\b", r"\brẻ hơn\b"),
        (r"\bfirst\b", r"\b(?:thứ nhất|đầu tiên)\b"),
        (r"\bsecond\b", r"\bthứ hai\b"),
        (r"\bthird\b", r"\bthứ ba\b"),
        (r"\bfourth\b", r"\bthứ (?:tư|bốn)\b"),
        (r"\bfifth\b", r"\bthứ năm\b"),
    )
    return all(bool(re.search(a, source)) == bool(re.search(b, clean)) for a, b in cues)


def prepare_input(request: UserRequest, config: ConversationConfig,
                  translator: Translator | None = None) -> PreparedInput:
    original = request.message
    message = original or ""
    if config.input_normalization_enabled:
        message = normalize_vietnamese_input(message, request)
    normalized = message != (original or "")
    base = PreparedInput(original, message, normalized)
    if not config.translation_enabled or "AI2KEEP" in message:
        return base
    protected = _protected_spans(message, request)
    masked, literals = _mask(message, protected)
    if not is_confident_english(masked):
        return base
    if (_allergy_signature(message, "en") is None
            or _structured_signature(masked, "en") is None):
        return PreparedInput(original, message, normalized, translation_error="translation_unverifiable")
    if translator is None:
        return PreparedInput(original, message, normalized, translation_error="translator_unavailable")
    try:
        translated = translator.translate(masked, source_language="en", target_language="vi")
        if not _translation_valid(masked, translated, literals):
            return PreparedInput(original, message, normalized, True, False, "translation_rejected")
        return PreparedInput(original, _restore(translated, literals), normalized, True, True)
    except Exception:
        # Provider error messages may include credentials. Keep a bounded code.
        return PreparedInput(original, message, normalized, True, False, "translation_failed")
