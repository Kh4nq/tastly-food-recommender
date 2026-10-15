"""Independent synthetic templates. This module never reads the benchmark."""
import random

from common.schemas import Candidate, PreviousResult, UserPreferenceState
from conversation.labeling.leakage import prompt_hash
from conversation.labeling.models import PromptSample
from conversation.rule_parser import parse_by_rules
from conversation.state_manager import update_state


TEMPLATES = {
    "food": ["kiếm {food} cho mình", "mình muốn thử {food}"],
    "cuisine": ["mình muốn món {cuisine}", "tìm quán chuyên đồ {cuisine}"],
    "budget": ["ăn dưới {budget}k nhé", "ngân sách tối đa {budget} nghìn"],
    "distance": ["tìm quán trong {distance}km", "đi bộ không quá {minutes} phút"],
    "transport": ["mình đi {transport} nhé", "đi {transport}, ăn {food}"],
    "occasion": ["tìm chỗ {occasion}", "ăn {food} để {occasion}"],
    "party_size": ["bàn cho {party} người ăn {food}", "nhóm {party} người nhé"],
    "companions": ["ăn với {companion}, muốn {food}"],
    "meal_time": ["{meal}, mình muốn {food}"],
    "hard_soft": ["bắt buộc có chỗ gửi xe, dưới {budget}k", "có chỗ gửi xe thì tốt, ăn {food}"],
    "semantic": ["chỗ có ánh sáng dịu để trò chuyện, ăn {food}", "ăn {food}, không gian yên tĩnh"],
    "negative": ["không thích cay, muốn ăn {food}", "mình không thích mùi khói, ăn {food}"],
    "allergy": ["dị ứng đậu phộng, muốn ăn {food}", "dị ứng tôm, dưới {budget}k"],
    "add_remove": ["bỏ giới hạn ngân sách, chọn {food}", "không cần chỗ gửi xe nữa, ăn {food}"],
    "correction": ["thực ra đổi sang {food}, dưới {budget}k", "đi xe máy nhưng đổi sang taxi, ăn {food}"],
    "relative": ["rẻ hơn một chút, vẫn ăn {food}", "gần hơn nhé, vẫn muốn {food}"],
    "absolute_relative": ["rẻ hơn nhưng tối đa {budget}k", "gần hơn, trong {distance}km thôi"],
    "references": ["quán thứ hai có {food} không", "quán đó có chỗ cho {party} người không"],
    "feedback": ["quán thứ hai quá ồn, muốn ăn {food} ở chỗ khác", "quán đó đắt quá, dưới {budget}k thôi"],
    "colloquial": ["ê kiếm {food} ngon ngon, tầm {budget}k hen", "thèm {food} ghê á, đi với {companion}"],
    "noisy": ["mún an {food}, duoi {budget}k nhaaa", "tim wan {food} gan gan ik"],
    "multiple": ["{meal}, nhóm {party} người ăn {food}, dưới {budget}k, trong {distance}km"],
    "ambiguous": ["chỗ hợp với {companion} ấy, món gì cũng được", "{meal}, như lần trước được không"],
}
FOLLOWUP = {"add_remove", "correction", "relative", "absolute_relative", "references", "feedback"}


def generate_samples(count=200, seed=42, *, multi_turn=True, with_results=True):
    if count < 1:
        raise ValueError("count must be positive")
    rng = random.Random(seed)
    samples, seen = [], set()
    categories = list(TEMPLATES)
    for attempt in range(max(1000, count * 100)):
        category = categories[len(samples) % len(categories)]
        values = {
            "food": rng.choice(["ramen", "phở", "bún bò", "cơm gà", "pizza", "sushi", "bánh cuốn", "mì quảng"]),
            "cuisine": rng.choice(["Nhật", "Hàn", "Thái", "Ấn Độ", "Ý", "Việt"]),
            "budget": rng.choice(range(35, 245, 5)), "distance": rng.choice([1, 2, 3, 4, 5, 7]),
            "minutes": rng.choice([8, 12, 15, 18, 25]), "party": rng.randint(2, 9),
            "transport": rng.choice(["xe máy", "ô tô", "xe đạp", "xe buýt", "metro"]),
            "occasion": rng.choice(["hẹn hò", "mừng sinh nhật", "ăn bàn công việc"]),
            "companion": rng.choice(["bạn gái", "bạn bè", "gia đình", "đồng nghiệp"]),
            "meal": rng.choice(["sáng nay", "trưa nay", "tối nay", "ăn khuya"]),
        }
        message = (rng.choice(["", "giúp mình ", "hôm nay ", "cho tôi "])
                   + rng.choice(TEMPLATES[category]).format(**values)
                   + rng.choice(["", " nhé", " được không", " nha"]))
        key = prompt_hash(message)
        if key in seen:
            continue
        seen.add(key)
        sample_id = f"syn-{seed}-{len(samples):06d}"
        state = UserPreferenceState(session_id=sample_id)
        history = []
        if multi_turn and category in FOLLOWUP:
            # Context is a real rule/state transition; no labels are emitted.
            history = [f"giúp mình ăn cơm gà dưới {values['budget'] + 20}k, trong 7km nhé"]
            state = update_state(state, parse_by_rules(history[0]), sample_id)
        candidates, results = [], []
        if with_results and category in {"references", "feedback"}:
            candidates = [Candidate(restaurant_id=f"SYNTHETIC-R{i}", menu_item_id=f"SYNTHETIC-M{i}",
                                    dish_id=f"SYNTHETIC-D{i}", restaurant_name=f"Quán giả lập {i}",
                                    dish_name=values["food"]) for i in (1, 2, 3)]
            results = [PreviousResult(rank=i, **c.model_dump(include={
                "restaurant_id", "menu_item_id", "restaurant_name", "dish_name"}))
                       for i, c in enumerate(candidates, 1)]
        samples.append(PromptSample(sample_id=sample_id, category=category, message=message,
            current_state=state, previous_results=results, mock_candidates=candidates, history=history,
            generation={"seed": seed, "template_version": 1, "attempt": attempt,
                        "multi_turn": bool(history), "prompt_hash": key}))
        if len(samples) == count:
            return samples
    raise ValueError("Template space exhausted; request a smaller count")
