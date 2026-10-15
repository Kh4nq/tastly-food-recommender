"""HTTP boundary tests with real AI2 and mocked OpenRouter HTTP responses."""

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
from scripts.benchmark_ai2_providers import empty_wire


@pytest.fixture
def web(monkeypatch):
    # Preserve the previous integration contract as an explicit legacy-mode regression.
    monkeypatch.setenv("AI2_LLM_FIRST_ENABLED", "false")
    monkeypatch.setenv("LLM_PROVIDER", "openrouter_chain")
    monkeypatch.setenv("OPENROUTER_ENABLED", "true")
    monkeypatch.setenv("OPENROUTER_API_KEY", "offline-test-secret")
    sessions = InMemorySessionStore()
    retrieve = Mock(return_value=[])
    maps = Mock(return_value=[])
    service = SearchService(sessions, Ai2ConversationAdapter(),
                            RecommendationPipeline(retrieve, Mock(return_value=[])), maps)
    catalog = SimpleNamespace(get_menu_items_by_ids=lambda _: [])
    with TestClient(create_app(Services(service, DishPresenter(catalog)))) as client:
        yield client, sessions, retrieve, maps


def transport(monkeypatch, replies):
    models = []
    def send(request, **kwargs):
        model = json.loads(request.data)["model"]
        models.append(model)
        reply = replies[len(models) - 1]
        if isinstance(reply, Exception):
            raise reply
        body = json.dumps({"model": model, "choices": [{"finish_reason": "stop",
            "message": {"content": json.dumps(reply)}}]}).encode()
        return nullcontext(SimpleNamespace(read=lambda _: body))
    monkeypatch.setattr("conversation.providers.openrouter_provider.urlopen", send)
    return models


def test_cookie_turns_update_budget_and_preserve_allergies(web, monkeypatch):
    client, sessions, _, _ = web
    calls = transport(monkeypatch, [])
    first = client.post("/api/search", json={"message": "ramen dưới 100k, dị ứng sữa và đậu phộng"})
    assert first.status_code == 200
    second = client.post("/api/search", json={"message": "dưới 80k"})
    assert second.status_code == 200
    state = second.json()["state"]
    assert state["food"] == ["ramen"]
    assert state["hard_constraints"] == {"budget_max": 80000, "allergens_excluded": ["milk", "peanut"]}
    assert second.json()["session_id"] == first.json()["session_id"]
    assert sessions.get(state["session_id"]).state.model_dump(mode="json") == state
    assert calls == []  # Complete rules bypass the paid chain.


@pytest.mark.parametrize("failure", [TimeoutError(), HTTPError("https://offline.invalid", 429, "rate limit", {}, None),
                                     HTTPError("https://offline.invalid", 401, "unauthorized", {}, None)])
def test_primary_api_failure_uses_backup_through_default_adapter(web, monkeypatch, failure):
    client, _, _, _ = web
    wire = empty_wire()
    wire["set_values"]["food"] = ["bún riêu"]
    calls = transport(monkeypatch, [failure, wire])
    response = client.post("/api/search", json={"message": "Mình muốn ăn bún riêu"})
    assert response.status_code == 200
    assert response.json()["state"]["food"] == ["bún riêu"]
    assert not response.json()["clarification_required"]
    assert calls == ["google/gemini-3.5-flash-lite", "openai/gpt-5.4-mini"]
    assert "offline-test-secret" not in response.text


def test_failed_chain_rolls_back_and_skips_ranked_and_map_retrieval(web, monkeypatch):
    client, sessions, retrieve, maps = web
    initial = client.post("/api/search", json={"message": "ramen dưới 100k, dị ứng sữa"}).json()
    retrieve.reset_mock()
    maps.reset_mock()
    calls = transport(monkeypatch, [TimeoutError(), TimeoutError()])
    response = client.post("/api/search", json={"message": "dưới 80k, ánh sáng dịu", "include_map_places": True})
    assert response.status_code == 200
    body = response.json()
    assert body["clarification_required"]
    assert body["results"] == body["map_places"] == []
    assert body["state"] == initial["state"]
    assert sessions.get(body["session_id"]).state.model_dump(mode="json") == initial["state"]
    retrieve.assert_not_called()
    maps.assert_not_called()
    assert len(calls) == 2


def test_bad_request_does_not_call_provider_or_change_session(web, monkeypatch):
    client, sessions, _, _ = web
    initial = client.post("/api/search", json={"form": {"food": "ramen", "budget_max": 100000}}).json()
    calls = transport(monkeypatch, [])
    response = client.post("/api/search", json={"message": "x" * 501})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    assert sessions.get(initial["session_id"]).state.model_dump(mode="json") == initial["state"]
    assert calls == []


def test_browser_snapshot_retains_serving_fields_and_server_session_identity(web, monkeypatch):
    client, _, _, _ = web
    calls = transport(monkeypatch, [])
    first = client.post("/api/search", json={"form": {"food": "ramen", "item_kind": "food", "serving_style": ["broth"]}}).json()
    snapshot = first["state"]
    snapshot["session_id"] = "frontend"
    response = client.post("/api/search", json={"preference_state": snapshot, "message": "dưới 80k", "include_map_places": True})
    assert response.status_code == 200
    state = response.json()["state"]
    assert state["session_id"] == first["session_id"]
    assert state["hard_constraints"] == {"budget_max": 80000, "item_kind": "food", "serving_style": ["broth"]}
    assert calls == []
