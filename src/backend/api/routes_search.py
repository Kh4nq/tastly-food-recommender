# Controller: HTTP in, HTTP out. All logic lives in the services
from fastapi import APIRouter
from starlette.concurrency import run_in_threadpool

from backend.api.deps import ServicesDep, SessionId
from backend.api.schemas import SearchRequest, SearchResponse

router = APIRouter(prefix="/api")


def preference_warnings(results, state=None):
    """Expose uncertain soft requirements without claiming every result fits."""
    unknown, mismatched, unresolved = set(), set(), set()
    for result in results:
        evidence = result.reason_features.get('preference_evidence', {})
        unknown.update(evidence.get('unknown', []))
        mismatched.update(evidence.get('mismatched', []))
        unresolved.update(evidence.get('unresolved_negative', []))
    warnings = []
    if state is not None:
        sides = state.context.get('requested_accompaniments', [])
        if isinstance(sides, list) and sides:
            warnings.append('Chưa xác minh quán có phục vụ món kèm: ' + ', '.join(str(s) for s in sides) + '. Bạn nên hỏi lại quán.')
        if state.context.get('transport_mode') and state.hard_constraints.get('max_distance_km'):
            warnings.append('Khoảng cách là khoảng cách địa lý, chưa tính quãng đường di chuyển thực tế.')
    if unknown:
        warnings.append('Chưa có dữ liệu xác minh cho một số kết quả: ' + ', '.join(sorted(unknown)) + '.')
    if mismatched:
        warnings.append('Một số kết quả không khớp ưu tiên: ' + ', '.join(sorted(mismatched)) + '.')
    if unresolved:
        warnings.append('Chưa đối chiếu được yêu cầu tránh: ' + ', '.join(sorted(unresolved)) + '.')
    return warnings


# async def, but every blocking call is handed to a thread so the event loop stays free
@router.post("/search", response_model=SearchResponse)
async def search(body: SearchRequest, session_id: SessionId, services: ServicesDep) -> SearchResponse:
    # The gate limits how many AI searches run at once and how long one may take
    outcome = await services.gate.run(services.search_service.search, body.to_command(session_id))
    results = await run_in_threadpool(services.presenter.present, outcome.results)
    return SearchResponse(
        session_id = session_id,
        results = results,
        state = outcome.state,
        clarification_required = outcome.clarification_required,
        warnings = preference_warnings(outcome.results, outcome.state),
        map_places = outcome.map_places,
        intent = outcome.intent,
        assistant_message = outcome.assistant_message,
        retrieval_deferred = outcome.retrieval_deferred,
        named_food_query = any(food.strip() for food in outcome.state.food),
    )
