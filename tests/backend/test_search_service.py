import pytest

from backend.adapters.session_memory import InMemorySessionStore
from backend.ports import ConversationError, SessionConflictError, TurnResult
from backend.services.pipeline import RecommendationPipeline
from backend.services.search_service import SearchCommand, SearchService
from common.schemas import Candidate, RankedResult, UserPreferenceState

POOL = [Candidate(restaurant_id=f"R{i}", menu_item_id=f"M{i}") for i in range(1, 6)]


def fake_retrieve(state, top_k=100):
    return POOL[:top_k]


def fake_rank(state, candidates, top_k=10):
    return [
        RankedResult(restaurant_id=c.restaurant_id, menu_item_id=c.menu_item_id, rank=i, score=1 / i)
        for i, c in enumerate(candidates[:top_k], start=1)
    ]


class FakeConversation:
    """Appends each message to state.food so we can see state carried across turns."""

    def __init__(self):
        self.requests = []

    def process(self, request):
        self.requests.append(request)
        previous = request.current_state.food if request.current_state else []
        state = UserPreferenceState(session_id=request.session_id, food=[*previous, request.message])
        return TurnResult(state=state, parser_used="rule", clarification_required=False)


@pytest.fixture
def sessions():
    return InMemorySessionStore()


@pytest.fixture
def conversation():
    return FakeConversation()


@pytest.fixture
def service(sessions, conversation):
    pipeline = RecommendationPipeline(retriever=fake_retrieve, ranker=fake_rank)
    return SearchService(sessions, conversation, pipeline)


def test_first_turn_has_no_state_and_saves_version_1(service, sessions, conversation):
    outcome = service.search(SearchCommand(session_id="S1", message="pho", top_k=3))
    assert conversation.requests[0].current_state is None
    assert [r.restaurant_id for r in outcome.results] == ["R1", "R2", "R3"]
    assert sessions.get("S1").version == 1


def test_second_turn_receives_stored_state(service, sessions, conversation):
    service.search(SearchCommand(session_id="S1", message="pho"))
    outcome = service.search(SearchCommand(session_id="S1", message="bun"))
    assert conversation.requests[1].current_state.food == ["pho"]
    assert outcome.state.food == ["pho", "bun"]
    assert sessions.get("S1").version == 2


def test_client_snapshot_syncs_removed_and_edited_preferences_without_reset(service, sessions, conversation):
    sessions.save("S1", UserPreferenceState(
        session_id="S1", user_id="server-user", food=["ramen"],
        hard_constraints={"budget_max": 50000, "max_distance_km": 9},
        semantic_preferences=["quiet"],
    ), expected_version=0)
    snapshot = UserPreferenceState(
        session_id="untrusted-other-session", user_id="untrusted-user", food=["ramen"],
        hard_constraints={"budget_max": 150000}, semantic_preferences=["quiet"],
    )
    service.search(SearchCommand(session_id="S1", message="closer", preference_state=snapshot))
    received = conversation.requests[-1].current_state
    assert received.session_id == "S1"
    assert received.user_id == "server-user"
    assert received.food == ["ramen"]
    assert received.hard_constraints == {"budget_max": 150000}
    assert received.semantic_preferences == ["quiet"]
    assert snapshot.session_id == "untrusted-other-session"
    assert sessions.get("S1").version == 2


def test_snapshot_cannot_assign_a_user_to_a_new_cookie_session(service, conversation):
    service.search(SearchCommand(
        session_id="new-cookie", message="pho",
        preference_state=UserPreferenceState(session_id="browser", user_id="other-user"),
    ))
    received = conversation.requests[-1].current_state
    assert received.session_id == "new-cookie"
    assert received.user_id is None


def test_exclude_and_top_k_reach_the_pipeline(service):
    outcome = service.search(
        SearchCommand(session_id="S1", message="pho", top_k=2, exclude_restaurant_ids=["R1"])
    )
    assert [r.restaurant_id for r in outcome.results] == ["R2", "R3"]


def test_conversation_error_saves_nothing(sessions):
    class Rejecting:
        def process(self, request):
            raise ConversationError("bad identity")

    pipeline = RecommendationPipeline(retriever=fake_retrieve, ranker=fake_rank)
    with pytest.raises(ConversationError):
        SearchService(sessions, Rejecting(), pipeline).search(SearchCommand(session_id="S1"))
    assert sessions.get("S1") is None


def test_pipeline_failure_saves_nothing(sessions, conversation):
    def broken_retrieve(state, top_k=100):
        raise RuntimeError("index offline")

    pipeline = RecommendationPipeline(retriever=broken_retrieve, ranker=fake_rank)
    service = SearchService(sessions, conversation, pipeline)
    with pytest.raises(RuntimeError):
        service.search(SearchCommand(session_id="S1", message="pho"))
    assert sessions.get("S1") is None


def test_concurrent_turn_on_same_session_raises_conflict(sessions):
    class RacingConversation(FakeConversation):
        def process(self, request):
            # Another tab saves the same session while this turn is still thinking
            sessions.save("S1", UserPreferenceState(session_id="S1"), expected_version=0)
            return super().process(request)

    pipeline = RecommendationPipeline(retriever=fake_retrieve, ranker=fake_rank)
    service = SearchService(sessions, RacingConversation(), pipeline)
    with pytest.raises(SessionConflictError):
        service.search(SearchCommand(session_id="S1", message="pho"))
