import pytest
from fastapi.testclient import TestClient

from backend.adapters.session_memory import InMemorySessionStore
from backend.api.deps import Services
from backend.api.presenter import DishPresenter
from backend.gate import AiTimeoutError, BusyError
from backend.main import create_app
from backend.ports import TurnResult
from backend.services.pipeline import RecommendationPipeline
from backend.services.search_service import SearchService
from backend.settings import Settings
from common.schemas import Candidate, RankedResult, UserPreferenceState

ORIGIN = "http://localhost:3000"


class Conversation:
    def process(self, request):
        state = UserPreferenceState(session_id=request.session_id)
        return TurnResult(state=state, parser_used="rule", clarification_required=False)


class Catalog:
    def get_menu_items_by_ids(self, menu_item_ids):
        return []


class FailingGate:
    """Gate stand-in that raises the given error instead of running the work."""

    def __init__(self, error):
        self.error = error

    async def run(self, fn, *args):
        raise self.error


def retrieve(state, top_k=100):
    return [Candidate(restaurant_id="R1", menu_item_id="M1")]


def rank(state, candidates, top_k=10):
    return [RankedResult(restaurant_id="R1", menu_item_id="M1", rank=1, score=1.0)]


def make_client(settings=None, **overrides):
    pipeline = RecommendationPipeline(retriever=retrieve, ranker=rank)
    service = SearchService(InMemorySessionStore(), Conversation(), pipeline)
    services = Services(service, DishPresenter(Catalog()), **overrides)
    return TestClient(create_app(services, settings), raise_server_exceptions=False)


def test_health_is_always_ok():
    response = make_client().get("/health")
    assert response.status_code == 200 and response.json() == {"status": "ok"}


def test_ready_when_all_checks_pass():
    response = make_client(health_checks={"database": lambda: None}).get("/ready")
    assert response.status_code == 200 and response.json() == {"status": "ready"}


def test_not_ready_names_the_failing_dependency_without_details():
    def database_down():
        raise RuntimeError("password=hunter2 refused")

    response = make_client(health_checks={"database": database_down}).get("/ready")
    assert response.status_code == 503
    assert response.json() == {"status": "not_ready", "failed": ["database"]}
    assert "hunter2" not in response.text


def test_busy_gate_gives_503_with_retry_after():
    response = make_client(gate=FailingGate(BusyError())).post("/api/search", json={})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "busy"
    assert response.headers["retry-after"] == "2"


def test_slow_gate_gives_504():
    response = make_client(gate=FailingGate(AiTimeoutError())).post("/api/search", json={})
    assert response.status_code == 504
    assert response.json()["error"]["code"] == "timeout"


@pytest.mark.parametrize('error_type,code', [
    ('unsupported', 'unsupported_constraint'), ('unknown', 'unverifiable_constraint'),
])
def test_unverifiable_retrieval_requirement_is_a_422_not_a_500(error_type, code):
    from retrieval.profiles import UnsupportedConstraintError, UnverifiableConstraintError
    cls = UnsupportedConstraintError if error_type == 'unsupported' else UnverifiableConstraintError
    response = make_client(gate=FailingGate(cls('Cannot verify parking; please relax it.'))).post('/api/search', json={})
    assert response.status_code == 422
    assert response.json()['error']['code'] == code
    assert 'parking' in response.json()['error']['message']


def test_invalid_retrieval_constraint_is_a_422():
    from retrieval.profiles import InvalidConstraintError
    response = make_client(gate=FailingGate(InvalidConstraintError('budget_min exceeds budget_max'))).post('/api/search', json={})
    assert response.status_code == 422
    assert response.json()['error']['code'] == 'invalid_constraint'


def test_successful_http_response_reports_soft_uncertainty():
    from backend.api.routes_search import preference_warnings
    from common.schemas import RankedResult
    result = RankedResult(restaurant_id='r', rank=1, score=1, reason_features={
        'demo_only': True,
        'preference_evidence': {'unknown': ['quiet'], 'mismatched': ['wifi'], 'unresolved_negative': ['smoke']}})
    warnings = preference_warnings([result])
    assert len(warnings) == 3
    assert 'quiet' in warnings[0] and 'wifi' in warnings[1] and 'smoke' in warnings[2]


def test_demo_result_does_not_add_provenance_notice_to_reply():
    from backend.api.routes_search import preference_warnings
    from common.schemas import RankedResult
    result = RankedResult(restaurant_id='r', rank=1, score=1, reason_features={'demo_only': True})
    assert preference_warnings([result]) == []


def test_allowed_origin_can_read_responses_and_send_cookies():
    response = make_client().post("/api/search", json={}, headers={"Origin": ORIGIN})
    assert response.headers["access-control-allow-origin"] == ORIGIN
    assert response.headers["access-control-allow-credentials"] == "true"
    assert "x-request-id" in response.headers["access-control-expose-headers"].lower()


def test_unexpected_500_is_still_readable_by_the_browser():
    class Boom:
        def process(self, request):
            raise RuntimeError("bug")

    pipeline = RecommendationPipeline(retriever=retrieve, ranker=rank)
    service = SearchService(InMemorySessionStore(), Boom(), pipeline)
    app = create_app(Services(service, DishPresenter(Catalog())))
    client = TestClient(app, raise_server_exceptions=False)
    response = client.post("/api/search", json={}, headers={"Origin": ORIGIN})
    assert response.status_code == 500
    assert response.headers["access-control-allow-origin"] == ORIGIN


def test_preflight_for_an_allowed_origin():
    response = make_client().options(
        "/api/search",
        headers={
            "Origin": ORIGIN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == ORIGIN


def test_other_origins_get_no_cors_headers():
    response = make_client().post("/api/search", json={}, headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in response.headers


@pytest.mark.parametrize("secure", [False, True])
def test_cookie_secure_flag_follows_settings(secure):
    client = make_client(Settings(cookie_secure=secure))
    cookie = client.post("/api/search", json={}).headers["set-cookie"].lower()
    assert ("secure" in cookie.replace("samesite", "")) is secure
