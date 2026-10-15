#Process local auth stores for dev and test
from dataclasses import dataclass, replace
from datetime import datetime , timedelta
from threading import Lock
from uuid import uuid4

from backend.ports import ActiveSession , Credentials , EmailTakenError , NewUser , User

_ROLES = ["customer" , "business"]

@dataclass
class _UserRow:
    user : User
    password_hash: str
    failed_login_count : int = 0
    locked_until : datetime | None = None
    
@dataclass
class _SessionRow:
    user_id : str
    last_seen_at : datetime
    expires_at : datetime
    
    
def _check_shop(role : str , shop_name : str | None) -> None:
    if role == "business" and not (shop_name or "").strip():
        raise ValueError("Business accounts need a shop name")
    
def _check_like_the_database(new : NewUser) -> None:
    if new.email != new.email.lower():
        raise ValueError("Email must be lowercase")
    
    if new.role not in _ROLES:
        raise ValueError(f"unknown role : {new.role}")
    
    _check_shop(new.role , new.shop_name)
    

class InMemoryAuthStore:
    # One object implements UserStore and AuthSessionStore
    def __init__(self) -> None:
        self._users : dict[str , _UserRow] = {} # user_id -> row
        self._user_by_email : dict[str , str] = {} # email -> user_id
        self._sessions : dict[str , _SessionRow] = {} # token_hash -> row
        self._lock = Lock() # requests run on a threadpool
        

    # User store
    def create(self, new: NewUser) -> User:
        _check_like_the_database(new)
        with self._lock:
            if new.email in self._user_by_email:
                raise EmailTakenError
            user = User(str(uuid4()), new.email, new.full_name, new.phone, new.role, new.shop_name)
            self._users[user.user_id] = _UserRow(user, new.password_hash)
            self._user_by_email[new.email] = user.user_id
            return user
        
    
    def get_credentials(self , email : str) -> Credentials | None:
        with self._lock:
            user_id = self._user_by_email.get(email)
            if user_id is None:
                return None
            
            row = self._users[user_id]
            return Credentials(row.user , row.password_hash , row.failed_login_count , row.locked_until)
        
    def record_failed_login(
        self,
        user_id : str,
        *,
        max_failures : int,
        lock_for : timedelta,
        now : datetime
    ) -> None:
        with self._lock:
            row = self._users[user_id]
            if row.locked_until is not None and row.locked_until <= now:
                row.failed_login_count , row.locked_until = 0 , None
                
            row.failed_login_count += 1
            if row.failed_login_count >= max_failures:
                row.locked_until = now + lock_for
                
    def clear_failed_logins(self , user_id : str) -> None:
        with self._lock:
            row = self._users[user_id]
            row.failed_login_count , row.locked_until = 0 , None
            
    def set_password_hash(self , user_id : str , password_hash : str) -> None:
        with self._lock:
            self._users[user_id].password_hash = password_hash
            
    def update_profile(
        self ,
        user_id : str,
        *,
        full_name : str,
        phone : str | None,
        shop_name : str | None
    ) -> User:
        with self._lock:
            row = self._users[user_id]
            _check_shop(row.user.role , shop_name)
            new_user = replace(row.user , full_name=full_name , phone=phone , shop_name=shop_name)
            row.user = new_user
            return new_user
        
    # -- AuthSessionStore
    def create_session(
            self,
            token_hash : str,
            user_id : str,
            *,
            now : datetime,
            expires_at : datetime
        ) -> None:
        with self._lock:
            if token_hash in self._sessions:
                raise ValueError("token_hash already exists")
            
            self._sessions[token_hash] = _SessionRow(user_id , now , expires_at)
            
            
    def get_session(self , token_hash : str , * , now : datetime) -> ActiveSession | None:
        with self._lock:
            row = self._sessions.get(token_hash)
            if row is None or row.expires_at <= now:
                return None
            
            return ActiveSession(self._users[row.user_id].user, row.last_seen_at, row.expires_at)
        

    def touch_session(
        self,
        token_hash : str,
        *,
        now : datetime,
        expires_at : datetime
    ) -> None:
        with self._lock:
            row = self._sessions.get(token_hash)
            if row is not None:
                row.last_seen_at , row.expires_at = now , expires_at
                
    
    def delete_session(self , token_hash : str) -> None:
        with self._lock:
            self._sessions.pop(token_hash , None)
            
    def delete_sessions_for_user(
        self,
        user_id : str,
        *,
        keep : str | None = None
    ) -> None:
        with self._lock:
            doomed = [t for t , s in self._sessions.items() if s.user_id == user_id and t != keep]
            
            for token_hash in doomed:
                del self._sessions[token_hash]
                
    
    def delete_expired_sessions(self , * , now : datetime) -> int:
        with self._lock:
            doomed = [t for t , s in self._sessions.items() if s.expires_at <= now]
            
            for token_hash in doomed:
                del self._sessions[token_hash]
                
            return len(doomed)