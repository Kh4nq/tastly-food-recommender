# Adapter: AI2 conversation module behind ConversationPort
from collections.abc import Callable

from common.schemas import UserRequest
from conversation import process_user_request
from conversation.models import ConversationResult
from backend.ports import ConversationError , TurnResult

class Ai2ConversationAdapter:
    def __init__ (
        self,
        process : Callable[[UserRequest] , ConversationResult] = process_user_request
    ) -> None:
        #Injectd so tests can pin the config or fake AI2 entirely
        self._process = process
    
    def process(self , request : UserRequest) -> TurnResult:
        try:
            result = self._process(request)
        except ValueError as e:
            # AI2 signals bad identity/input whit ValueError
            raise ConversationError(str(e)) from e
        
        meta = result.metadata
        return TurnResult(
            state = result.state,
            parser_used = meta.parser_used,
            clarification_required = meta.clarification_required,
            intent = meta.intent,
            assistant_message = meta.assistant_message,
            state_preserved = meta.state_preserved,
        )
