"""Backend-ready synchronous request processing, without a web framework."""

from time import perf_counter

from common.schemas import UserRequest, UserPreferenceState
from conversation.config import ConversationConfig
from conversation.conversation_logger import log_conversation
from conversation.models import ConversationResult
from conversation.parser import parse_user_input_detailed
from conversation.preprocessing import Translator
from conversation.providers.base import LLMProvider
from conversation.state_manager import update_state


def process_user_request(
    request: UserRequest, provider: LLMProvider | None = None,
    *, config: ConversationConfig | None = None, slm_provider=None, translator: Translator | None = None,
) -> ConversationResult:
    """Apply one independently-owned update and log the resulting metadata."""
    started = perf_counter()
    # Reject identity errors before invoking a paid provider.
    if request.current_state is not None:
        if request.current_state.session_id != request.session_id:
            raise ValueError("current_state belongs to a different session")
        if request.user_id is not None and request.current_state.user_id not in (None, request.user_id):
            raise ValueError("current_state belongs to a different user")
    config = config or ConversationConfig.from_env()
    parsed = parse_user_input_detailed(request, provider, config=config, slm_provider=slm_provider, translator=translator)
    if parsed.metadata.state_preserved:
        state = (request.current_state.model_copy(deep=True) if request.current_state else
                 UserPreferenceState(session_id=request.session_id, user_id=request.user_id))
    else:
        state = update_state(request.current_state, parsed.preference_update, request.session_id, request.user_id)
    result = ConversationResult(**parsed.model_dump(), state=state)
    result.metadata.total_ms = result.metadata.latency_ms = (perf_counter() - started) * 1000
    result.metadata.logging_error = log_conversation(request, result, config)
    return result
