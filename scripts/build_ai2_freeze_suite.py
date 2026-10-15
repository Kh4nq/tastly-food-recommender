"""Freeze authored diagnostic expectations BEFORE inference; never independent gold."""
import argparse
import copy
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SESSION = "adapter-regression"


def state(**fields):
    return {"session_id": SESSION, **fields}


def build_suite():
    prior = json.loads((ROOT / "tests/data/ai2_adapter_regressions.json").read_text(encoding="utf-8"))
    categories = ["allergy", "allergy", "allergy_retention", "travel_time", "feedback", "context", "reference"]
    cases = []
    for row, category in zip(prior, categories):
        row = copy.deepcopy(row)
        row.update(category=category, origin="existing_7_diagnostic_probes",
                   label_status="authored_regression_expectation_not_independent_gold",
                   source="tests/data/ai2_adapter_regressions.json", family_id="diagnostic-" + category,
                   history=[])
        raw = copy.deepcopy(row["expected_update"])
        for ref in raw.get("references", []):
            for key in ("status", "restaurant_id", "menu_item_id"):
                ref.pop(key, None)
        row["expected_raw_update"] = raw
        cases.append(row)

    def add(id, category, message, update, expected, initial=None, results=None, history=None):
        raw = copy.deepcopy(update)
        for ref in raw.get("references", []):
            for key in ("status", "restaurant_id", "menu_item_id"):
                ref.pop(key, None)
        cases.append({"id": id, "category": category, "message": message,
            "current_state": initial, "previous_results": results or [], "history": history or [],
            "expected_raw_update": raw, "expected_update": update, "expected_state": expected,
            "origin": "authored_before_model_run_20261015", "family_id": "diagnostic-" + category,
            "label_status": "authored_regression_expectation_not_independent_gold",
            "source": "scripts/build_ai2_freeze_suite.py"})

    add("sesame-negated", "allergy", "Không bị dị ứng mè.", {}, state())
    add("mixed-allergy-negation", "allergy", "Tôi không dị ứng mè nhưng bị dị ứng sữa.",
        {"add_hard_constraints": {"allergens_excluded": ["milk"]}},
        state(hard_constraints={"allergens_excluded": ["milk"]}))
    add("triple-allergy", "allergy", "Mình bị dị ứng mè, sữa và đậu phộng.",
        {"add_hard_constraints": {"allergens_excluded": ["sesame", "milk", "peanut"]}},
        state(hard_constraints={"allergens_excluded": ["sesame", "milk", "peanut"]}))
    initial = state(hard_constraints={"allergens_excluded": ["milk", "peanut"]}, soft_preferences={"wifi": True})
    add("wifi-only-no-allergy-cue", "allergy_retention", "Bỏ yêu cầu wifi, chỉ cập nhật mục đó.",
        {"remove_preferences": ["soft_preferences.wifi"]},
        state(hard_constraints={"allergens_excluded": ["milk", "peanut"]}), initial,
        history=["Mình dị ứng sữa và đậu phộng.", "Ưu tiên wifi."])
    add("allergy-accumulation", "allergy_retention", "Mình bị dị ứng sữa.",
        {"add_hard_constraints": {"allergens_excluded": ["milk"]}},
        state(hard_constraints={"allergens_excluded": ["sesame", "milk"], "max_distance_km": 2}),
        state(hard_constraints={"allergens_excluded": ["sesame"], "max_distance_km": 2}),
        history=["Mình dị ứng hạt mè.", "Trong vòng 2km."])
    add("context-correction", "context", "Tối nay, à thực ra trưa mai.",
        {"context_updates": {"meal_time": "lunch"}}, state(context={"meal_time": "lunch", "party_size": 3}),
        state(context={"meal_time": "dinner", "party_size": 3}), history=["Nhóm 3 người, tối nay."])
    results = [{"rank": 1, "restaurant_id": "eval-r1", "menu_item_id": "eval-m1"},
               {"rank": 2, "restaurant_id": "eval-r2", "menu_item_id": "eval-m2"}]
    ref = {"status": "resolved", "rank": 2, "restaurant_id": "eval-r2", "menu_item_id": "eval-m2", "mention": "quán số 2"}
    negative = {**ref, "sentiment": "negative"}
    add("negative-reference", "reference", "Quán số 2 không hợp khẩu vị mình.",
        {"references": [negative]}, state(food=["sushi"], reference_restaurants=[negative]),
        state(food=["sushi"]), results)
    add("ordinal-selection", "reference", "Chọn quán số 2.", {"references": [ref]},
        state(reference_restaurants=[ref]), results=results)
    unresolved = {"status": "unresolved", "mention": "quán số 3"}
    add("missing-rank", "reference", "Quán số 3 nhé.", {"references": [unresolved]},
        state(reference_restaurants=[unresolved]), results=results)
    cases[-1]["expected_raw_update"] = {"references": [{"rank": 3, "mention": "quán số 3"}]}
    add("travel-english", "travel_time", "At most 15 minutes by motorbike.",
        {"add_hard_constraints": {"max_travel_time_min": 15}, "context_updates": {"transport_mode": "motorbike"}},
        state(hard_constraints={"max_travel_time_min": 15}, context={"transport_mode": "motorbike"}))
    add("travel-correction", "travel_time", "Thời gian di chuyển tối đa 15 phút.",
        {"add_hard_constraints": {"max_travel_time_min": 15}},
        state(hard_constraints={"max_travel_time_min": 15, "max_distance_km": 2}, context={"transport_mode": "motorbike"}),
        state(hard_constraints={"max_travel_time_min": 30, "max_distance_km": 2}, context={"transport_mode": "motorbike"}))
    add("travel-removal", "travel_time", "Không cần giới hạn 15 phút nữa.",
        {"remove_preferences": ["hard_constraints.max_travel_time_min"]}, state(),
        state(hard_constraints={"max_travel_time_min": 15}))
    add("facilities-hard-soft", "hard_constraint", "Phải có máy lạnh, ưu tiên wifi.",
        {"add_hard_constraints": {"air_conditioning": True}, "add_soft_preferences": {"wifi": True}},
        state(hard_constraints={"air_conditioning": True}, soft_preferences={"wifi": True}))
    add("relative-budget-preserve", "feedback", "Rẻ hơn đi.", {"relative_updates": {"budget": "decrease"}},
        state(hard_constraints={"budget_max": 90000}), state(hard_constraints={"budget_max": 90000}),
        history=["Ngân sách dưới 90k."])

    # These do not get accuracy labels; human review is still required.
    for id, category, message, initial, previous in [
        ("vegetarian-hotpot", "food_trace", "Tôi muốn tìm lẩu chay.", None, []),
        ("vegetarian-hotpot-retention", "food_trace", "Đổi món thành lẩu chay, vẫn giữ điều kiện ăn chay.",
            state(food=["ramen"], hard_constraints={"vegetarian": True}), []),
        ("unknown-allergen-cashew", "allergy", "Mình bị dị ứng hạt điều.", None, []),
        ("similar-reference-pronoun", "reference", "Quán số 2 ổn, tìm giống quán đó nhưng gần hơn.", None, results),
    ]:
        cases.append({"id": id, "category": category, "message": message, "current_state": initial,
                      "previous_results": previous, "history": [], "family_id": "candidate-" + category,
                      "origin": "authored_unreviewed_candidate_20261015", "source": "scripts/build_ai2_freeze_suite.py",
                      "label_status": "needs_human_review", "expected_update": None,
                      "expected_raw_update": None, "expected_state": None})
    return {"kind": "diagnostic_suite_not_independent_benchmark", "created": "2026-10-15",
            "independent_gold_count": 0, "expectations_frozen_before_inference": True,
            "history_policy": "History is audit evidence only; production SLMInput consumes state and previous_results, not raw history.",
            "cases": cases}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Do not overwrite frozen expectations")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(build_suite(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Frozen 25 cases: 21 diagnostic expectations + 4 human-review candidates")
