# Interfaces (ports) the services depend on. Adapters implement them
from dataclasses import dataclass
from typing import Protocol, Any

from dataclasses import dataclass
from collections.abc import Sequence
from datetime import datetime , timedelta
from common.schemas import UserPreferenceState, UserRequest

class SessionConflictError(Exception):
    # The session changed since it was read (optimistic locking failed)
    ...
    
@dataclass(frozen=True)
class SessionRecord:
    state: UserPreferenceState
    version : int # +1 on every successful save
    
class SessionStore(Protocol):
    def get(self , session_id : str) -> SessionRecord | None:
        ...
        
    def save(
        self ,
        session_id : str ,
        state : UserPreferenceState ,
        expected_version : int
    ) -> SessionRecord:
        ...
        
    def delete(self , session_id : str) -> None:
        ...
    
class ConversationError(Exception):
    # AI 2 rejected the request
    ...
    
@dataclass(frozen=True)
class TurnResult:
    # What the backend needs from on conversation turn
    state : UserPreferenceState
    parser_used : str #"rule" or "rule_fallback"
    clarification_required : bool
    intent: str = "search"
    assistant_message: str | None = None
    state_preserved: bool = False
    
class ConversationPort(Protocol):
    def process(self , request : UserRequest) -> TurnResult:
        ...
        
class CatalogUnavailableError(Exception):
    # The catalog service is down or misbehaving
    ...
    
class CatalogRepo(Protocol):
    def get_menu_items_by_ids(
        self,
        menu_item_ids: Sequence[str]
    ) -> list[dict[str, Any]]:
        # Rows follow the get_menu_items_by_ids SQL function one per id found
        # Raise CatalogUnavailableError when the database is down
        ...
        
# -- Accounts
# All datetimes are timezone-aware UTC; callers pass `now` so tests control the clock

class EmailTakenError(Exception):
    # An account with this email already exists
    ...
    
class InvalidCredentialsError(Exception):
    # unknown email or wrong password
    ...
    
class WrongPasswordError(Exception):
    # The user exists but the password is wrong
    ...
    
class UnauthenticatedError(Exception):
    # No valid login session on this request
    ...
    
class InvalidProfileError(Exception):
    """The profile breaks a rule that depends on the account, e.g. a shop needs a name."""

class AccountLockedError(Exception):
    # The user exists but the account is locked due to too many failed logins
    def __init__ (self ,retry_after : timedelta) -> None:
        super().__init__()
        self.retry_after = retry_after
    
@dataclass(frozen=True)
class User:
    # Public part of account. Safe to return to the browser
    user_id : str
    email: str
    full_name : str
    phone : str | None
    role : str
    shop_name : str | None
    

@dataclass(frozen=True)
class NewUser: 
    email : str 
    password_hash : str
    full_name : str
    phone : str | None
    role : str
    shop_name : str | None
    
@dataclass(frozen=True)
class Credentials:
    user : User
    password_hash : str
    failed_login_count : int
    locked_until : datetime | None
    

@dataclass(frozen=True)
class ActiveSession:
    user : User
    last_seen_at : datetime
    expires_at : datetime
    
class UserStore(Protocol):
    def create(self , new : NewUser) -> User:
        # Raise EmailTakenError when email exists
        ...
        
    def get_credentials(self , email : str) -> Credentials | None:
        ...
        
    def record_failed_login(
        self,
        user_id : str,
        *,
        max_failures : int,
        lock_for : timedelta,
        now : datetime
    ) -> None:
        # Must be atomic: concurrent failures may not lose a count
        ...

    def clear_failed_logins(self , user_id : str) -> None:
        ...
        
    def set_password_hash(self , user_id : str , password_hash : str) -> None:
        ...
        
    def update_profile(
        self , 
        user_id : str,
        *,
        full_name : str,
        phone : str | None,
        shop_name : str | None
    ) -> User:
        ...
        
class AuthSessionStore(Protocol):
    def create_session(
        self ,
        token_hash : str ,
        user_id : str ,
        * ,
        now : datetime ,
        expires_at : datetime
    ) -> None:
        ...

    def get_session(self , token_hash : str , * , now : datetime) -> ActiveSession | None:
        # None when unknown or expired
        ...

    def touch_session(self , token_hash : str , * , now : datetime , expires_at : datetime) -> None:
        ...

    def delete_session(self , token_hash : str) -> None:
        ...

    def delete_sessions_for_user(self , user_id : str , * , keep : str | None = None) -> None:
        # Revoke every session of a user, optionally keeping the current one
        ...

    def delete_expired_sessions(self , * , now : datetime) -> int:
        ...
