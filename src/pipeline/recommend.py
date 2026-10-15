"""Compose independently owned modules without supplying fake production logic."""

import conversation
import ranking
import retrieval

from common.config import PipelineConfig
from common.interfaces import ConversationModule, RankingModule, RetrievalModule, StateManager
from common.schemas import RecommendationResponse, UserRequest, UserPreferenceState
from pipeline.selection import identity, select_restaurants


def recommend(
    request: UserRequest, *, retrieve_fn: RetrievalModule | None = None,
    rank_fn: RankingModule | None = None, parse_fn: ConversationModule | None = None,
    update_state_fn: StateManager | None = None, config: PipelineConfig | None = None,
) -> RecommendationResponse:
    """Run AI 2 -> AI 1 -> AI 3 with injectable functions and explicit limits.

    Defaults use AI 2's environment-controlled parser, artifact-backed AI 1
    retrieval and AI 3's lazy model/baseline ranking. Offline callers should
    inject retrieval/ranking fixtures and a parser with providers/SLM disabled.
    """
    # Mirror AI 2's service preflight before any potentially paid parsing call.
    if request.current_state is not None:
        if request.current_state.session_id != request.session_id:
            raise ValueError("current_state belongs to a different session")
        if request.user_id is not None and request.current_state.user_id not in (None, request.user_id):
            raise ValueError("current_state belongs to a different user")

    settings = config if config is not None else PipelineConfig()
    transition = update_state_fn if update_state_fn is not None else conversation.update_state
    retrieve = retrieve_fn if retrieve_fn is not None else retrieval.retrieve_candidates
    rank = rank_fn if rank_fn is not None else ranking.rank_candidates

    parsed = None
    if parse_fn is None:
        from conversation.parser import parse_user_input_detailed
        parsed = parse_user_input_detailed(request)
        update = parsed.preference_update
    else:
        update = parse_fn(request)
    if parsed and parsed.metadata.state_preserved:
        state = (request.current_state.model_copy(deep=True) if request.current_state else
                 UserPreferenceState(session_id=request.session_id, user_id=request.user_id))
    else:
        state = transition(current_state=request.current_state, update=update,
                           session_id=request.session_id, user_id=request.user_id)
    if parsed and (parsed.metadata.clarification_required or
                   parsed.metadata.intent in {"conversation", "informational", "clarification"}):
        return RecommendationResponse(session_id=request.session_id, state=state, results=[])
    candidates = retrieve(state, top_k=settings.retrieval_top_k)
    candidates = sorted(candidates, key=identity)
    ranked = rank(state, candidates, top_k=len(candidates)) if candidates else []
    results = select_restaurants(state, candidates, ranked, settings.ranking_top_k)
    return RecommendationResponse(session_id=request.session_id, state=state, results=results)
