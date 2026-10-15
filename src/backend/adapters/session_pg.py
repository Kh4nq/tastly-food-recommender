# Adapter: PostgreSQL SessionStore. Share by every worker process
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from common.schemas import UserPreferenceState
from backend.ports import SessionConflictError , SessionRecord

_INSERT = (
    "INSERT INTO sessions (session_id, state, version) VALUES (%s, %s, 1) "
    "ON CONFLICT (session_id) DO NOTHING RETURNING version"
)
_UPDATE = (
    "UPDATE sessions SET state = %s, version = version + 1, updated_at = now() "
    "WHERE session_id = %s AND version = %s RETURNING version"
)

class PostgresSessionStore:
    def __init__(self , pool : ConnectionPool) -> None:
        self._pool = pool
        
    def get(self , session_id : str) -> SessionRecord | None:
        with self._pool.connection() as conn:
            row = conn.execute(
                "SELECT state, version FROM sessions WHERE session_id = %s" ,
                (session_id ,)
            ).fetchone()
            
            if row is None: return None
            state , version = row
            
            return SessionRecord(state = UserPreferenceState.model_validate(state) , version = version)
        
    def save(
        self,
        session_id : str,
        state : UserPreferenceState ,
        expected_version : int
    ) -> SessionRecord:
        payload = Jsonb(state.model_dump(mode = "json"))
        
        #One atomic statement: the database decides who wins a race, no extra lock needed
        if expected_version == 0:
            sql , params = _INSERT , (session_id , payload)
        else: sql , params = _UPDATE , (payload , session_id , expected_version)

        with self._pool.connection() as conn:
            row = conn.execute(sql , params).fetchone()

        if row is None:
            raise SessionConflictError(session_id)
    
        return SessionRecord(state = state.model_copy(deep = True) , version = row[0])
    

    def delete(self , session_id : str) -> None:
        with self._pool.connection() as conn:
            conn.execute("DELETE FROM sessions WHERE session_id = %s" , (session_id ,))