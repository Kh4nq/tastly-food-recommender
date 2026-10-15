"""Canonical context values; unknown keys retain simple JSON values."""
from conversation._utils import normalize_text, unique

ALIASES = {
    "transport_mode": {
        "walking": ("đi bộ", "on foot"), "motorbike": ("xe máy", "đi xe máy", "by motorbike"),
        "car": ("ô tô", "xe hơi", "đi ô tô", "đi xe hơi", "by car"), "bicycle": ("xe đạp", "đi xe đạp", "by bicycle"),
        "public_transport": ("xe buýt", "bus", "metro", "đi xe buýt", "đi bus", "đi metro"),
        "ride_hailing": ("grab", "taxi", "xe công nghệ", "đi grab", "đi taxi", "đi xe công nghệ"),
    },
    "occasion": {"casual": (), "date": ("hẹn hò", "đi date"), "family": ("gia đình", "bữa ăn gia đình"),
                 "business": ("công việc", "tiếp khách", "ăn bàn công việc"),
                 "celebration": ("sinh nhật", "mừng sinh nhật", "ăn mừng")},
    "meal_time": {"breakfast": ("bữa sáng", "sáng nay"), "lunch": ("bữa trưa", "trưa nay"),
                  "dinner": ("bữa tối", "tối nay"), "late_night": ("ăn khuya", "late night")},
    "companions": {"alone": ("một mình", "solo"), "partner": ("bạn gái", "bạn trai"),
                   "friend": (), "friends": ("bạn bè",), "family": ("gia đình",),
                   "children": ("trẻ em",), "colleagues": ("đồng nghiệp",)},
}


def normalize_context(values):
    def simple(value):
        return (value is None or type(value) in (str, int, float, bool)
                or isinstance(value, list) and all(simple(item) for item in value))

    result = {}
    for key, value in values.items():
        if key in ("location", "food", "cuisine", "session_id", "user_id", "reference_restaurants", "relative_updates") or not simple(value):
            raise ValueError("Context accepts simple values, excluding location and relative events")
        if key == "party_size" and (type(value) is not int or value <= 0):
            raise ValueError("party_size must be a positive integer")
        if key in ALIASES:
            aliases = {normalize_text(alias): canonical for canonical, names in ALIASES[key].items()
                       for alias in (canonical, *names)}
            items = value if key == "companions" else [value]
            if not isinstance(items, list) or not all(isinstance(v, str) for v in items):
                raise ValueError("Invalid context value")
            normalized = [aliases.get(normalize_text(v), v) for v in items]
            if key != "companions" and any(v not in ALIASES[key] for v in normalized):
                raise ValueError("Unknown canonical context value")
            value = unique(normalized) if key == "companions" else normalized[0]
        result[key] = value
    return result
