import re

import pytest
from fastapi.testclient import TestClient

from backend.adapters.session_memory import InMemorySessionStore
from backend.api.deps import Services
from backend.api.presenter import DishPresenter
from backend.main import create_app
from backend.ports import ConversationError, SessionConflictError, TurnResult
from backend.services.pipeline import RecommendationPipeline
from backend.services.search_service import SearchService
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
    """Appends each message to state.food so we can see state carried across requests."""

    def process(self, request):
        previous = request.current_state.food if request.current_state else []
        food = [*previous, request.message] if request.message else previous
        state = UserPreferenceState(session_id=request.session_id, food=food)
        return TurnResult(state=state, parser_used="rule", clarification_required=False)


class FakeCatalog:
    def get_menu_items_by_ids(self, menu_item_ids):
        return []


class Failing:
    """Conversation that always raises the given error."""

    def __init__(self, error):
        self.error = error

    def process(self, request):
        raise self.error


def make_client(conversation=None, map_finder=None):
    pipeline = RecommendationPipeline(retriever=fake_retrieve, ranker=fake_rank)
    search_service = SearchService(
        InMemorySessionStore(), conversation or FakeConversation(), pipeline, map_finder=map_finder,
    )
    services = Services(search_service, DishPresenter(FakeCatalog()))
    # raise_server_exceptions=False lets us see the 500 response a real client would get
    return TestClient(create_app(services), raise_server_exceptions=False)


def test_search_returns_ranked_results():
    response = make_client().post("/api/search", json={"message": "pho", "top_k": 3})
    body = response.json()
    assert response.status_code == 200
    assert [r["restaurant_id"] for r in body["results"]] == ["R1", "R2", "R3"]
    assert [r["rank"] for r in body["results"]] == [1, 2, 3]
    assert body["state"]["food"] == ["pho"]
    assert body["clarification_required"] is False


def test_map_places_are_independent_of_top_k_and_opt_in():
    calls = []
    def map_finder(state, exclude):
        calls.append((state.food, list(exclude)))
        return [{'id': f'R{i}', 'name': f'Place {i}', 'lat': 10.77, 'lon': 106.7} for i in range(140)]
    client = make_client(map_finder=map_finder)
    body = client.post('/api/search', json={'message': 'pho', 'top_k': 3,
                                          'include_map_places': True, 'exclude_restaurant_ids': ['banned']}).json()
    assert len(body['results']) == 3
    assert len(body['map_places']) == 140
    assert calls == [(['pho'], ['banned'])]
    assert make_client(map_finder=map_finder).post('/api/search', json={}).json()['map_places'] is None
    assert len(calls) == 1


def test_first_request_sets_a_safe_cookie():
    response = make_client().post("/api/search", json={})
    cookie = response.headers["set-cookie"].lower()
    assert re.fullmatch(r"[0-9a-f]{32}", response.json()["session_id"])
    assert "anon_id=" in cookie and "httponly" in cookie and "samesite=lax" in cookie


def test_same_cookie_continues_the_same_session():
    client = make_client()  # TestClient keeps cookies between calls
    first = client.post("/api/search", json={"message": "pho"}).json()
    second = client.post("/api/search", json={"message": "bun"}).json()
    assert second["session_id"] == first["session_id"]
    assert second["state"]["food"] == ["pho", "bun"]


def test_shared_snapshot_and_real_offline_ai2_keep_latest_manual_edits_and_chat_refinements():
    from functools import partial
    from backend.adapters.ai2_conversation import Ai2ConversationAdapter
    from conversation import process_user_request
    from conversation.config import ConversationConfig

    adapter = Ai2ConversationAdapter(partial(process_user_request, config=ConversationConfig()))
    client = make_client(conversation=adapter)
    snapshot = UserPreferenceState(
        session_id="frontend", food=["ramen"], cuisine=["Japanese"],
        location={"lat": 10.838, "lon": 106.665},
        hard_constraints={"budget_max": 50000, "max_distance_km": 9},
    ).model_dump(mode="json")
    first_response = client.post("/api/search", json={
        "preference_state": snapshot, "message": "ramen dưới 100k trong 5km",
    })
    assert first_response.status_code == 200
    first = first_response.json()
    assert first["state"]["hard_constraints"]["budget_max"] == 100000
    assert first["state"]["hard_constraints"]["max_distance_km"] == 5
    assert first["state"]["location"] == snapshot["location"]
    edited = first["state"]
    edited["hard_constraints"]["budget_max"] = 150000
    edited["hard_constraints"].pop("max_distance_km")
    second = client.post("/api/search", json={
        "preference_state": edited, "message": "quán yên tĩnh",
    }).json()
    assert second["session_id"] == first["session_id"]
    assert second["state"]["food"] == first["state"]["food"]
    assert second["state"]["cuisine"] == first["state"]["cuisine"]
    assert second["state"]["hard_constraints"]["budget_max"] == 150000
    assert "max_distance_km" not in second["state"]["hard_constraints"]
    assert second["state"]["location"] == snapshot["location"]


def test_malformed_cookie_is_replaced():
    client = make_client()
    client.cookies.set("anon_id", "../../evil")
    session_id = client.post("/api/search", json={}).json()["session_id"]
    assert re.fullmatch(r"[0-9a-f]{32}", session_id)


def test_every_response_carries_a_request_id():
    response = make_client().post("/api/search", json={})
    assert re.fullmatch(r"[0-9a-f]{32}", response.headers["x-request-id"])


@pytest.mark.parametrize("bad", [{"top_k": 0}, {"mesage": "typo"}, {"message": "x" * 501}])
def test_invalid_body_gives_validation_envelope(bad):
    response = make_client().post("/api/search", json=bad)
    error = response.json()["error"]
    assert response.status_code == 422
    assert error["code"] == "validation_error"
    assert error["request_id"] == response.headers["x-request-id"]


def test_validation_error_does_not_echo_the_message():
    response = make_client().post("/api/search", json={"message": "secret " * 100})
    assert "secret secret" not in response.text


def test_conversation_error_is_422():
    response = make_client(Failing(ConversationError("bad"))).post("/api/search", json={})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_request"


def test_session_conflict_is_409():
    response = make_client(Failing(SessionConflictError("S"))).post("/api/search", json={})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "session_conflict"


def test_unexpected_error_is_500_without_leaking_details():
    response = make_client(Failing(RuntimeError("db password is hunter2"))).post(
        "/api/search", json={}
    )
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"
    assert "hunter2" not in response.text
    assert response.headers["x-request-id"] == response.json()["error"]["request_id"]
