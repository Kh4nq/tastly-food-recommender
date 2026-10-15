from fastapi.testclient import TestClient

from backend.adapters.session_memory import InMemorySessionStore
from backend.api.deps import Services
from backend.api.presenter import DishPresenter
from backend.main import create_app
from backend.ports import TurnResult
from backend.services.pipeline import RecommendationPipeline
from backend.services.search_service import SearchService
from common.schemas import Candidate, RankedResult, UserPreferenceState


class AccumulatingConversation:
    """Appends each message to state.food, so leftover state is easy to see."""

    def process(self, request):
        previous = request.current_state.food if request.current_state else []
        food = [*previous, request.message] if request.message else previous
        state = UserPreferenceState(session_id=request.session_id, food=food)
        return TurnResult(state=state, parser_used="rule", clarification_required=False)


class Catalog:
    def get_menu_items_by_ids(self, menu_item_ids):
        return []


def retrieve(state, top_k=100):
    return [Candidate(restaurant_id="R1", menu_item_id="M1")]


def rank(state, candidates, top_k=10):
    return [RankedResult(restaurant_id="R1", menu_item_id="M1", rank=1, score=1.0)]


def make_app():
    pipeline = RecommendationPipeline(retriever=retrieve, ranker=rank)
    service = SearchService(InMemorySessionStore(), AccumulatingConversation(), pipeline)
    return create_app(Services(service, DishPresenter(Catalog())))


def search(client, message):
    return client.post("/api/search", json={"message": message}).json()


def test_reset_answers_204_with_an_empty_body():
    client = TestClient(make_app())
    response = client.delete("/api/session")
    assert response.status_code == 204 and response.content == b""


def test_reset_without_a_cookie_still_issues_one():
    response = TestClient(make_app()).delete("/api/session")
    assert "anon_id=" in response.headers["set-cookie"]


def test_search_after_reset_starts_from_a_clean_state():
    client = TestClient(make_app())
    search(client, "pho")
    assert search(client, "bun")["state"]["food"] == ["pho", "bun"]
    client.delete("/api/session")
    assert search(client, "com")["state"]["food"] == ["com"]


def test_reset_only_touches_the_callers_session():
    app = make_app()
    mine, other = TestClient(app), TestClient(app)
    search(mine, "pho")
    search(other, "bun")
    mine.delete("/api/session")
    assert search(other, "com")["state"]["food"] == ["bun", "com"]