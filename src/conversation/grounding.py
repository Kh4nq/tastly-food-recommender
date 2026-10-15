"""Check quoted provenance and numeric facts after semantic model interpretation."""

from decimal import Decimal
import re
import unicodedata

from conversation._utils import normalize_text

UNITS = {
    "budget": {"k": 1000, "nghìn": 1000, "ngàn": 1000, "thousand": 1000,
               "tr": 1000000, "triệu": 1000000, "million": 1000000,
               "vnd": 1, "vnđ": 1, "đồng": 1, "đ": 1, "₫": 1},
    "distance": {"km": 1, "kilometer": 1, "kilometers": 1, "kilometre": 1, "kilometres": 1,
                 "cây số": 1, "m": Decimal(".001"), "meter": Decimal(".001"),
                 "meters": Decimal(".001"), "metre": Decimal(".001"), "metres": Decimal(".001")},
    "time": {"phút": 1, "minute": 1, "minutes": 1, "min": 1},
    "rating": {"sao": 1, "star": 1, "stars": 1},
    "count": {"người": 1, "people": 1, "persons": 1},
}
WORDS = dict(zip(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen".split(), range(20)))
WORDS.update(dict(zip("không một hai ba bốn năm sáu bảy tám chín mười".split(), range(11))))
WORDS.update({"mốt": 1, "tư": 4, "lăm": 5, "twenty": 20, "thirty": 30, "forty": 40,
              "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90})


def number(text, *, money=False):
    if re.fullmatch(r"\d+(?:[.,]\d+)*", text):
        if money and re.fullmatch(r"\d{1,3}(?:[.,]\d{3})+", text):
            return Decimal(re.sub(r"[.,]", "", text))
        return Decimal(text.replace(",", "."))
    value = Decimal(0)
    for word in text.replace("-", " ").split():
        if word in {"and", "a", "linh", "lẻ"}:
            continue
        if word in {"hundred", "trăm"}:
            value = (value or 1) * 100
        elif word == "mươi":
            value = (value // 10) * 10 + (value % 10 or 1) * 10
        elif word in {"half", "rưỡi"}:
            value += Decimal(".5")
        else:
            value += WORDS[word]
    return value


def unitless_budgets(text, *, food_search=False):
    """VND literals need local monetary intent, not merely a plausible number.

    Food-context bound/reduction shorthand requires whole VND >=1000;
    explicit budget/price wording also supports smaller literal amounts. This
    validates a model's delta; it never extracts intent or invents a conversion.
    """
    money = r'\b(?:ngân sách|mức giá|giá|chi phí|budget|price|cost|spend)\b'
    other = r'\b(?:khoảng cách|bán kính|distance|radius|thời gian|travel time|số người|party size|rating|đánh giá|calories|calo|steps|số bước|mã(?: đơn)?|order id|id|địa chỉ|address|năm|year)\b'
    units = '|'.join(re.escape(u) for values in UNITS.values() for u in values)
    suffix = rf'\s*(?:{units}|usd|dollars?|eur|euros?|guests?|seats?|tables?|chỗ|bàn|món|items?|bước|steps?|calories|calo|kcal|tuổi|years?|%)(?!\w)'
    result = []
    for match in re.finditer(r'(?<![\w.,+\-])\d+(?:[.,]\d+)*(?!\w|[.,]\d)', text):
        literal = match[0]
        if not (literal.isdigit() or re.fullmatch(r'\d{1,3}(?:[.,]\d{3})+', literal)):
            continue
        before, after = text[:match.start()], text[match.end():]
        if re.match(suffix, after, re.I) or re.match(r'\s*[-/:]\s*\d', after) or re.search(r'[$€₫đ]\s*$', before):
            continue
        prefix = re.split(r'[,;!?]|\.(?!\d)', before)[-1][-100:]
        if re.search(r"không phải|không muốn|\bnot\b|don't want", prefix):
            continue
        monetary = list(re.finditer(money, prefix, re.I))
        nonmonetary = list(re.finditer(other, prefix, re.I))
        if nonmonetary and (not monetary or nonmonetary[-1].start() > monetary[-1].start()):
            continue
        amount = number(literal, money=True)
        bound = re.search(r'(?:dưới|trên|tối đa|tối thiểu|không quá|under|below|over|above|at most|at least|less than|more than|[<>]=?)\s*$', prefix)
        reduction = re.search(r'(?:giảm|hạ|rẻ hơn|cheaper|reduce|lower)[^,.;!?]{0,45}(?:xuống|to|dưới|under|below)\s*$', prefix)
        if monetary or amount >= 1000 and food_search and (bound or reduction):
            result.append((amount, match))
    return result


def quantities(text, kind, *, food_search=False):
    units = UNITS[kind]
    unit_pattern = "|".join(re.escape(u) for u in sorted(units, key=len, reverse=True))
    words = "|".join([*WORDS, "hundred", "trăm", "mươi", "half", "rưỡi", "and", "a", "linh", "lẻ"])
    amount = rf"(?:\d+(?:[.,]\d+)*|(?:\b(?:{words})[ -]+)*(?:{words}))"
    pattern = rf"(?<!\w)({amount})\s*({unit_pattern})(?!\w)"
    found = [(number(m[1], money=kind == "budget") * units[m[2]], m) for m in re.finditer(pattern, text)]
    if kind == 'budget':
        found.extend(unitless_budgets(text, food_search=food_search))
    return sorted(found, key=lambda pair: pair[1].start())


def quoted_evidence(evidence, message):
    """Quotes locate support; their semantic interpretation still belongs to AI2's LLM."""
    result = {}
    text = normalize_text(message)
    for entry in evidence or []:
        quote = normalize_text(entry.quote)
        if not quote.strip() or quote not in text:
            raise ValueError("Evidence quote is absent from the current message")
        result.setdefault(entry.field, []).append(quote)
    return result


def food_quote_supports(food, quotes):
    """Allow canonical accents/aliases while rejecting unrelated quoted words.

    Unknown dish names can always be preserved verbatim. This is a provenance
    check after interpretation, not a food-name parser or a required input grammar.
    """
    from conversation.rule_parser import FOOD_ALIASES
    def tokens(value):
        text = normalize_text(value).replace("vegetarian", "chay").replace("vegan", "thuần chay")
        text = "".join(c for c in unicodedata.normalize("NFD", text) if not unicodedata.combining(c)).replace("đ", "d")
        return set(re.findall(r"\w+", text)) - {"mon", "food", "dish"}
    names = [food]
    for canonical, aliases in FOOD_ALIASES:
        if tokens(food) == tokens(canonical):
            names.extend(aliases)
    return any(tokens(name) and tokens(name) <= tokens(quote) for name in names for quote in quotes)


def validate_numeric(key, value, text, *, food_search=False):
    kind = ("budget" if key in {"budget_min", "budget_max"} else
            "distance" if key == "max_distance_km" else "time" if key == "max_travel_time_min" else
            "rating" if key in {"rating", "min_rating"} else "count" if key == "party_size" else None)
    if kind is None:
        return
    matches = quantities(text, kind, food_search=food_search)
    matches = [(amount, match) for amount, match in matches if not re.search(
        r"(?:không phải(?: trong)?|không muốn(?: trong)?|not(?: within)?|don't want)\s*$", text[:match.start()])]
    if Decimal(str(value)) not in {amount for amount, _ in matches}:
        raise ValueError("Numeric constraint lacks matching units/value")
    if key in {"budget_min", "budget_max"} and len(matches) == 1:
        prefix = text[:matches[0][1].start()]
        if key == "budget_min" and re.search(r"(?:dưới|under|below|less than|không quá|tối đa|<)\s*$", prefix):
            raise ValueError("An upper bound is not a minimum budget")
        if key == "budget_max" and re.search(r"(?:trên|over|above|more than|tối thiểu|at least|>)\s*$", prefix):
            raise ValueError("A lower bound is not a maximum budget")


def validate_coordinates(location, text):
    pairs = re.findall(r"(?<![\d.])([+-]?\d+(?:\.\d+)?)\s*[,;]\s*([+-]?\d+(?:\.\d+)?)(?![\d.])", text)
    if not any(Decimal(lat) == Decimal(str(location["lat"])) and
               Decimal(lon) == Decimal(str(location["lon"])) for lat, lon in pairs):
        raise ValueError("Coordinates require an explicit latitude/longitude pair or form")
