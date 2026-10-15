"""Real AI2 and HTTP provider envelopes with synthetic retrieval/ranking fixtures."""

from contextlib import nullcontext
import json
from types import SimpleNamespace
from unittest.mock import Mock
from urllib.error import HTTPError

import pytest
from fastapi.testclient import TestClient

from backend.adapters.ai2_conversation import Ai2ConversationAdapter
from backend.adapters.session_memory import InMemorySessionStore
from backend.api.deps import Services
from backend.api.presenter import DishPresenter
from backend.main import create_app
from backend.services.pipeline import RecommendationPipeline
from backend.services.search_service import SearchService
from common.schemas import Candidate, RankedResult, UserPreferenceState, UserRequest
from pipeline import recommend
from scripts.benchmark_ai2_providers import empty_wire


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openrouter_chain")
    monkeypatch.setenv("OPENROUTER_ENABLED", "true")
    monkeypatch.setenv("OPENROUTER_API_KEY", "offline-secret")
    sessions = InMemorySessionStore()
    candidate = Candidate(restaurant_id="fixture:restaurant", menu_item_id="fixture:menu", dish_id="fixture:dish")
    retrieve = Mock(return_value=[candidate])
    rank = Mock(return_value=[RankedResult(restaurant_id=candidate.restaurant_id, menu_item_id=candidate.menu_item_id,
                                         dish_id=candidate.dish_id, rank=1, score=1)])
    maps = Mock(return_value=[])
    service = SearchService(sessions, Ai2ConversationAdapter(), RecommendationPipeline(retrieve, rank), maps)
    catalog = SimpleNamespace(get_menu_items_by_ids=lambda _: [])
    with TestClient(create_app(Services(service, DishPresenter(catalog)))) as client:
        yield client, sessions, retrieve, rank, maps


def remote(monkeypatch, replies):
    calls = []
    def send(request, **kwargs):
        payload = json.loads(request.data)
        calls.append(payload)
        assert payload["response_format"]["json_schema"]["name"] == "conversation_turn"
        context = json.loads(payload["messages"][1]["content"])
        assert context["rule_update"] is None
        reply = replies[len(calls) - 1]
        if isinstance(reply, Exception):
            raise reply
        data = json.dumps({"model": payload["model"], "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(reply)}}]}).encode()
        return nullcontext(SimpleNamespace(read=lambda _: data))
    monkeypatch.setattr("conversation.providers.openrouter_provider.urlopen", send)
    return calls


def response(intent="search", reply=None, food=None, hard=None):
    preferences = empty_wire()
    preferences["set_values"]["food"] = food
    preferences["add_hard_constraints"] = [{"key": k, "value": v} for k, v in (hard or {}).items()]
    return {"intent": intent, "reply": reply, "preferences": preferences, "evidence": []}


@pytest.mark.parametrize("message,food,budget", [
    ("Phở chay dưới 100k cách tôi 3km", "phở chay", 100000),
    ("Phở chay dưới 100k trong vòng 3km", "phở chay", 100000),
    ("Tìm ramen dưới 150k trong 3km", "ramen", 150000),
    ("Find ramen under 150k within 3km", "ramen", 150000),
])
def test_valid_search_reaches_existing_pipeline_once(app, monkeypatch, message, food, budget):
    client, _, retrieve, rank, maps = app
    calls = remote(monkeypatch, [response(food=[food], hard={"budget_max": budget, "max_distance_km": 3})])
    result = client.post("/api/search", json={"message": message, "form": {"location": {"lat": 10.77, "lon": 106.69}}, "include_map_places": True})
    assert result.status_code == 200
    body = result.json()
    assert not body["clarification_required"] and body["intent"] == "search"
    assert body["state"]["food"] == [food]
    assert body["results"][0]["restaurant_id"] == "fixture:restaurant"
    assert body["results"][0]["menu_item_id"] == "fixture:menu"
    assert body["results"][0]["dish_id"] == "fixture:dish"
    assert len(calls) == 1
    retrieve.assert_called_once(); rank.assert_called_once(); maps.assert_called_once()


@pytest.mark.parametrize("message,intent,reply", [
    ("Phở khác bún như thế nào?", "informational", "Phở thường có sợi dẹt, còn bún có sợi tròn."),
    ("Chào bạn", "conversation", "Chào bạn! Mình có thể giúp gì cho bạn?"),
    ("Hello", "conversation", "Chào bạn! Bạn muốn tìm hiểu món ăn nào?"),
    ("How is pho different from bun?", "informational", "Phở và bún có hình dạng sợi khác nhau."),
])
def test_nonsearch_http_has_natural_reply_no_retrieval_or_state_save(app, monkeypatch, message, intent, reply):
    client, sessions, retrieve, rank, maps = app
    calls = remote(monkeypatch, [response(intent, reply)])
    initial = client.post("/api/search", json={"form": {"food": "ramen", "budget_max": 150000}}).json()
    saved = sessions.get(initial["session_id"])
    for fn in (retrieve, rank, maps):
        fn.reset_mock()
    # An unrelated dirty browser snapshot cannot change the stored search on chat.
    snapshot = {**initial["state"], "food": ["pizza"], "session_id": "frontend"}
    result = client.post("/api/search", json={"message": message, "preference_state": snapshot, "include_map_places": True})
    assert result.status_code == 200
    body = result.json()
    assert body["intent"] == intent and body["assistant_message"] == reply
    assert body["state"] == initial["state"] and body["results"] == body["map_places"] == []
    assert sessions.get(body["session_id"]) == saved
    assert len(calls) == 1
    for fn in (retrieve, rank, maps):
        fn.assert_not_called()


def test_new_greeting_does_not_need_location_or_create_search_record(app, monkeypatch):
    client, sessions, retrieve, rank, maps = app
    remote(monkeypatch, [response("conversation", "Chào bạn!")])
    body = client.post("/api/search", json={"message": "Chào bạn", "defer_retrieval": True}).json()
    assert body["intent"] == "conversation" and not body["retrieval_deferred"]
    assert sessions.get(body["session_id"]) is None
    for fn in (retrieve, rank, maps):
        fn.assert_not_called()


def test_deferred_location_resumes_search_without_second_model_call(app, monkeypatch):
    client, sessions, retrieve, rank, maps = app
    calls = remote(monkeypatch, [response(food=["ramen"], hard={"budget_max": 150000, "max_distance_km": 3})])
    first = client.post("/api/search", json={"message": "Tìm ramen dưới 150k trong 3km", "defer_retrieval": True, "include_map_places": True}).json()
    assert first["retrieval_deferred"] and first["results"] == first["map_places"] == []
    assert sessions.get(first["session_id"]).state.food == ["ramen"]
    for fn in (retrieve, rank, maps):
        fn.assert_not_called()
    snapshot = {**first["state"], "location": {"lat": 10.77, "lon": 106.69}}
    second = client.post("/api/search", json={"preference_state": snapshot, "include_map_places": True}).json()
    assert second["session_id"] == first["session_id"] and not second["retrieval_deferred"]
    assert second["state"]["hard_constraints"]["max_distance_km"] == 3
    assert len(calls) == 1
    retrieve.assert_called_once(); rank.assert_called_once(); maps.assert_called_once()


def test_real_http_error_failover_and_wire_profiles(app, monkeypatch, capsys):
    client, _, _, _, _ = app
    calls = remote(monkeypatch, [HTTPError("https://offline.invalid", 429, "offline-secret", {}, None), response(food=["ramen"])])
    result = client.post("/api/search", json={"message": "Tìm ramen"})
    assert result.status_code == 200 and not result.json()["clarification_required"]
    assert [c["model"] for c in calls] == ["google/gemini-3.5-flash-lite", "openai/gpt-5.4-mini"]
    assert calls[0]["reasoning"] == {"enabled": True}
    assert calls[1]["reasoning"] == {"effort": "none"} and "temperature" not in calls[1]
    assert all(not c["provider"]["allow_fallbacks"] for c in calls)
    assert "offline-secret" not in result.text + capsys.readouterr().out


def test_both_provider_failures_preserve_http_state_and_skip_pipeline(app, monkeypatch):
    client, sessions, retrieve, rank, maps = app
    first = client.post("/api/search", json={"form": {"food": "ramen", "budget_max": 100000}}).json()
    original = sessions.get(first["session_id"])
    for fn in (retrieve, rank, maps):
        fn.reset_mock()
    remote(monkeypatch, [TimeoutError(), TimeoutError()])
    snapshot = {**first["state"], "food": ["pizza"], "hard_constraints": {"budget_max": 90000}}
    result = client.post("/api/search", json={"message": "Tìm phở dưới 80k", "preference_state": snapshot, "include_map_places": True}).json()
    assert result["intent"] == "clarification" and result["clarification_required"]
    assert result["assistant_message"] and result["state"] == first["state"]
    assert sessions.get(first["session_id"]).state.model_dump(mode="json") == first["state"]
    assert sessions.get(first["session_id"]) == original
    for fn in (retrieve, rank, maps):
        fn.assert_not_called()


def test_public_pipeline_also_honors_conversation_intent(monkeypatch, app):
    remote(monkeypatch, [response("informational", "Phở và bún có hình dạng sợi khác nhau.")])
    retrieve, rank = Mock(), Mock()
    state = UserPreferenceState(session_id="S", food=["ramen"])
    result = recommend(UserRequest(session_id="S", message="Phở khác bún như thế nào?", current_state=state), retrieve_fn=retrieve, rank_fn=rank)
    assert result.state == state and result.results == []
    retrieve.assert_not_called(); rank.assert_not_called()
