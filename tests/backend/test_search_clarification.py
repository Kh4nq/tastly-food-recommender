"""Real AI2 clarification must stop recommendations at the backend boundary."""

from functools import partial
from unittest.mock import Mock

import pytest

from backend.adapters.ai2_conversation import Ai2ConversationAdapter
from backend.adapters.session_memory import InMemorySessionStore
from backend.services.pipeline import RecommendationPipeline
from backend.services.search_service import SearchCommand, SearchService
from conversation.config import ConversationConfig
from conversation.service import process_user_request


@pytest.mark.parametrize("message", ["Bị dị ứng một nguyên liệu chưa rõ", "quán số 2"])
def test_clarification_preserves_partial_form_without_recommending(message):
    sessions = InMemorySessionStore()
    retrieve, rank = Mock(return_value=[]), Mock(return_value=[])
    conversation = Ai2ConversationAdapter(partial(process_user_request, config=ConversationConfig()))
    service = SearchService(sessions, conversation, RecommendationPipeline(retrieve, rank))

    result = service.search(SearchCommand(session_id="S", message=message, form={"food": "phở"}))

    assert result.clarification_required
    assert result.results == []
    assert result.state.food == ["phở"]
    assert sessions.get("S").state == result.state
    retrieve.assert_not_called()
    rank.assert_not_called()
