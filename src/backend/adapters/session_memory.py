#Process-local SessionStore for dev and tests. Not shared between workers
from dataclasses import replace
from threading import Lock

from backend.ports import SessionConflictError , SessionRecord
from common.schemas import UserPreferenceState

def _clone(record : SessionRecord) -> SessionRecord:
    #State is mutable so never handout the stored object itself
    return replace(record , state = record.state.model_copy(deep = True))

class InMemorySessionStore:
    def __init__(self) -> None:
        self._records: dict[str , SessionRecord] = {}
        self._lock = Lock() # request run on a threadpool
        
    def get(self , session_id : str) -> SessionRecord | None:
        with self._lock:
            record = self._records.get(session_id)
            if record is None:
                return None
            return _clone(record)
        
    def save(
        self ,
        session_id : str,
        state : UserPreferenceState ,
        expected_version : int
    ) -> SessionRecord:
        with self._lock:
            current = self._records.get(session_id)
            current_version = current.version if current else 0
            
            if current_version != expected_version:
                raise SessionConflictError(session_id)
            
            record = SessionRecord(state = state , version = current_version + 1)
            self._records[session_id] = _clone(record)
            return _clone(record)
    
    def delete(self , session_id : str) -> None:
        with self._lock:
            self._records.pop(session_id , None)
            