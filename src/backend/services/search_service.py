# Use case: one search turn = load state -> converse -> recommend -> save state
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from backend.ports import ConversationPort , SessionStore
from backend.services.pipeline import RecommendationPipeline
from common.schemas import (
    PreviousResult,
    RankedResult,
    UserFormInput,
    UserPreferenceState,
    UserRequest,
)

@dataclass(frozen = True)
class SearchCommand:
    session_id : str
    form : UserFormInput = field(default_factory = UserFormInput)
    message : str | None = None
    previous_results : Sequence[PreviousResult] = ()
    exclude_restaurant_ids: Sequence[str] = ()
    top_k : int | None = None
    include_map_places: bool = False
    preference_state: UserPreferenceState | None = None
    defer_retrieval: bool = False
    
@dataclass(frozen = True)
class SearchOutCome:
    state : UserPreferenceState
    results : list[RankedResult]
    parser_used : str
    clarification_required : bool
    map_places: list[dict] | None = None
    intent: str = "search"
    assistant_message: str | None = None
    retrieval_deferred: bool = False
    
class SearchService:
    def __init__ (
        self,
        sessions: SessionStore ,
        conversation: ConversationPort ,
        pipeline: RecommendationPipeline,
        map_finder: Callable[[UserPreferenceState, Sequence[str]], list[dict]] | None = None,
    ) -> None:
        self._sessions = sessions
        self._conversation = conversation
        self._pipeline = pipeline
        self._map_finder = map_finder
        
    def search(self , command : SearchCommand) -> SearchOutCome:
        record = self._sessions.get(command.session_id)
        current_state = record.state if record else None
        if command.preference_state is not None:
            # The browser edits preferences, never the cookie session identity.
            current_state = command.preference_state.model_copy(deep=True, update={
                "session_id": command.session_id,
                "user_id": record.state.user_id if record else None,
            })
        request = UserRequest(
            session_id = command.session_id,
            form = command.form,
            message = command.message,
            current_state = current_state,
            previous_results = list(command.previous_results)
        )
        turn = self._conversation.process(request)
        if turn.intent in {"informational", "conversation"} or turn.state_preserved:
            # Browser preference snapshots do not become persisted edits when
            # the user is only asking a question/chatting or AI2 rolled back.
            state = record.state.model_copy(deep=True) if record else UserPreferenceState(session_id=command.session_id)
            return SearchOutCome(state=state, results=[], parser_used=turn.parser_used,
                clarification_required=turn.clarification_required, map_places=[] if command.include_map_places else None,
                intent=turn.intent, assistant_message=turn.assistant_message)
        deferred = command.defer_retrieval and not turn.clarification_required
        if turn.clarification_required or deferred:
            # AI2 has not accepted a searchable turn. This also covers cloud
            # failure rollback: neither ranked results nor map pins are safe.
            results = []
            map_places = [] if command.include_map_places else None
        else:
            results = self._pipeline.search(
                turn.state,
                top_k = command.top_k,
                exclude = command.exclude_restaurant_ids
            )
            map_places = None
            if command.include_map_places:
                # Preserve the existing all-matching map, independent of Top-K.
                # Selected alternatives are added from their filtered coordinates.
                places = self._map_finder(turn.state, command.exclude_restaurant_ids) if self._map_finder else []
                combined = {p['id']: p for p in places}
                for r in results:
                    point = r.reason_features.get('catalog_location')
                    if point:
                        combined[r.restaurant_id] = dict(id=r.restaurant_id, name=r.restaurant_name or '', dish=r.dish_name or '',
                            lat=point['lat'], lon=point['lon'], distance_km=r.distance_km, price_vnd=r.price)
                map_places = list(combined.values())
        
        # Save last: a failed turn leaves the stored state untouched
        self._sessions.save(
            command.session_id,
            turn.state,
            expected_version = record.version if record else 0
        )
        
        return SearchOutCome (
            state = turn.state,
            results = results,
            parser_used = turn.parser_used,
            clarification_required = turn.clarification_required,
            map_places = map_places,
            intent = turn.intent,
            assistant_message = turn.assistant_message,
            retrieval_deferred = deferred,
        )
    
    def reset(self , session_id : str) -> None:
        self._sessions.delete(session_id)
