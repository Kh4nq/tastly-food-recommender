"""Bounded runtime fixes using authored probes, no dataset/benchmark access."""
from types import SimpleNamespace

import pytest

from common.schemas import PreferenceUpdate, PreviousResult, UserPreferenceState, UserRequest
from conversation.config import ConversationConfig
from conversation.reference_resolver import resolve_message_references
from conversation.rule_parser import parse_by_rules_detailed
from conversation.service import process_user_request
from conversation.slm.base import SLMParseResult


def run(message, target, state=None, results=None):
    local = SimpleNamespace(parse=lambda inp: SLMParseResult(update=target, confidence=.80))
    return process_user_request(UserRequest(session_id="S", message=message, current_state=state, previous_results=results or []),
        config=ConversationConfig(local_slm_enabled=True), slm_provider=local)


def test_birthday_does_not_overwrite_cuisine_during_merge():
    state = UserPreferenceState(session_id="S", cuisine=["vietnamese"], food=["phở"])
    target = PreferenceUpdate(context_updates={"occasion": "celebration", "meal_time": "dinner"})
    turn = run("Giúp mình nhé: đổi thành mừng sinh nhật vào buổi tối; các tiêu chí món giữ nguyên", target, state)
    assert turn.state.cuisine == ["vietnamese"] and turn.state.food == ["phở"]
    assert turn.state.context == target.context_updates


@pytest.mark.parametrize("message", ["món Nhật", "ẩm thực Nhật Bản", "Nhật", "muốn ăn ramen Nhật"])
def test_explicit_japanese_cuisine_still_supported(message):
    assert parse_by_rules_detailed(message).update.set_values["cuisine"] == ["japanese"]


@pytest.mark.parametrize("message,target", [
    ("Ramen nha, mình đang muốn ăn món đó.", PreferenceUpdate(set_values={"food": ["ramen"]})),
    ("Không thích đậu phộng, mình vẫn ăn được; chỉ muốn tránh gợi ý món đó.",
        PreferenceUpdate(add_negative_preferences=["peanut"])),
])
def test_local_food_antecedent_does_not_require_previous_restaurant(message, target):
    turn = run(message, target)
    assert turn.state.reference_restaurants == []
    assert not turn.metadata.clarification_required
    assert turn.preference_update.model_dump() == target.model_dump()
    assert "allergens_excluded" not in turn.state.hard_constraints


@pytest.mark.parametrize("message", ["Ăn món đó", "Quán đó nhé", "zốp zép, món đó nhé"])
def test_missing_antecedent_remains_unresolved(message):
    assert resolve_message_references(message, [])[0]["status"] == "unresolved"


def test_previous_results_and_ordinals_still_require_real_selectors():
    results = [PreviousResult(rank=2, restaurant_id="fixture-r", menu_item_id="fixture-m", dish_name="ramen")]
    assert resolve_message_references("Ramen, món đó nhé", results)[0]["status"] == "unresolved"
    assert resolve_message_references("món số 2", results)[0]["restaurant_id"] == "fixture-r"
    assert resolve_message_references("món số 2", [])[0]["status"] == "unresolved"


@pytest.mark.parametrize("message,target", [
    ("Món bánh xèo nhé, cứ giữ đúng tên món Việt.", PreferenceUpdate(set_values={"food":["bánh xèo"]})),
    ("Quán có wifi sẽ hợp, nhưng không yêu cầu đồ ăn chay.", PreferenceUpdate(add_soft_preferences={"wifi":True})),
    ("Một buổi ăn bình thường thôi, không phải sinh nhật hoặc hẹn hò.", PreferenceUpdate(context_updates={"occasion":"casual"})),
])
def test_negated_or_metalinguistic_cues_do_not_survive_merge(message,target):
    turn=run(message,target)
    assert turn.preference_update.model_dump()==target.model_dump()
    assert not turn.metadata.clarification_required


@pytest.mark.parametrize("dish,rank,message,sentiment", [
    ("ramen",2,"Thích món ramen trong kết quả, dùng nó làm tham chiếu.","positive"),
    ("phở",1,"Món phở ở vị trí đầu không hợp khẩu vị mình.","negative"),
])
def test_feedback_does_not_replace_existing_food(dish,rank,message,sentiment):
    results=[PreviousResult(rank=1,restaurant_id="r1",dish_name="phở"),
             PreviousResult(rank=2,restaurant_id="r2",dish_name="ramen")]
    target=PreferenceUpdate(references=[{"mention":"món "+dish,"dish_name":dish,"rank":rank,"sentiment":sentiment}])
    turn=run(message,target,UserPreferenceState(session_id="S",food=["sushi"]),results)
    assert turn.state.food==["sushi"]
    assert len(turn.state.reference_restaurants)==1
    assert turn.state.reference_restaurants[0]["restaurant_id"]=="r"+str(rank)
    assert turn.state.reference_restaurants[0]["sentiment"]==sentiment


@pytest.mark.parametrize("message,field,value", [
    ("Tìm món Việt", "cuisine", ["vietnamese"]),
    ("Mình yêu cầu đồ ăn chay", "vegetarian", True),
    ("Không phải sinh nhật, nhưng đi hẹn hò", "occasion", "date"),
    ("Không phải sinh nhật hoặc hẹn hò, nhưng tối nay đi date", "occasion", "date"),
    ("Tìm món ramen trong kết quả", "food", ["ramen"]),
])
def test_positive_requests_and_clause_boundaries_still_work(message,field,value):
    update=parse_by_rules_detailed(message).update
    containers={**update.set_values,**update.add_hard_constraints,**update.context_updates}
    assert containers[field]==value
