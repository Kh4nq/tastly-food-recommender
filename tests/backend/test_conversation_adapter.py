from functools import partial

import pytest

from backend.adapters.ai2_conversation import Ai2ConversationAdapter
from backend.ports import ConversationError
from common.schemas import UserFormInput, UserRequest
from conversation import process_user_request
from conversation.config import ConversationConfig

# Default config = rules only: no provider, no SLM, no logging. Offline and deterministic
OFFLINE = partial(process_user_request, config=ConversationConfig())
FORM = UserFormInput(food="pho", budget_max=60000)


def test_form_turn_builds_state_and_maps_metadata():
    result = Ai2ConversationAdapter(OFFLINE).process(UserRequest(session_id="S1", form=FORM))
    assert result.state.session_id == "S1"
    assert result.state.hard_constraints["budget_max"] == 60000
    assert result.parser_used == "rule"
    assert result.clarification_required is False


def test_follow_up_message_updates_previous_state():
    adapter = Ai2ConversationAdapter(OFFLINE)
    first = adapter.process(UserRequest(session_id="S1", form=FORM))
    second = adapter.process(
        UserRequest(session_id="S1", message="tìm bún chả dưới 80k", current_state=first.state)
    )
    assert second.state.hard_constraints["budget_max"] == 80000


def test_identity_mismatch_becomes_conversation_error():
    adapter = Ai2ConversationAdapter(OFFLINE)
    first = adapter.process(UserRequest(session_id="S1", form=FORM))
    with pytest.raises(ConversationError):
        adapter.process(UserRequest(session_id="S2", current_state=first.state))


def test_unexpected_errors_are_not_swallowed():
    def boom(request):
        raise RuntimeError("bug in AI 2")

    with pytest.raises(RuntimeError):
        Ai2ConversationAdapter(boom).process(UserRequest(session_id="S1"))