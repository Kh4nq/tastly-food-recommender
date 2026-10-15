#Account use cases: register, login authentication, logout , change password
import hashlib
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


from backend.ports import (
    AccountLockedError,
    ActiveSession,
    AuthSessionStore,
    Credentials,
    InvalidCredentialsError,
    NewUser,
    User,
    UserStore,
    WrongPasswordError,
    InvalidProfileError,
)

from backend.services.passwords import (
    MAX_PASSWORD_LENGTH,
    MIN_PASSWORD_LENGTH,
    burn_password_check,
    hash_password,
    verify_password,
    needs_rehash,
)

@dataclass (frozen = True)
class AuthConfig:
    session_ttl : timedelta = timedelta(days = 7)
    touch_after : timedelta = timedelta(hours = 1)
    max_failures : int = 5
    lock_for : timedelta = timedelta(minutes = 15)
    cleanup_every : timedelta = timedelta(hours = 1) # How often a sign-in sweeps expired sessions
    
@dataclass(frozen = True)
class Registration:
    role : str
    full_name : str
    email : str
    password : str
    phone : str | None = None
    shop_name : str | None = None
    
@dataclass (frozen = True)
class LoginResult:
    user : User
    token : str
    
def normalize_email(email : str) -> str:
    return email.strip().lower()

def hash_token(token : str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()

def utcnow() -> datetime:
    return datetime.now(timezone.utc)

def require_valid_password(password : str) -> None:
    if not MIN_PASSWORD_LENGTH <= len(password) <= MAX_PASSWORD_LENGTH:
        raise ValueError("password length out of range")
    

class AuthService:
    def __init__(
        self,
        users : UserStore,
        sessions : AuthSessionStore,
        config : AuthConfig = AuthConfig(),
        clock : Callable[[], datetime] = utcnow
    ) -> None:
        self._users = users
        self._sessions = sessions
        self._config = config
        self._clock = clock
        self._last_cleanup : datetime | None = None

    # -- Entry points
    def register(self , registration : Registration) -> LoginResult:
        require_valid_password(registration.password)
        
        is_business = registration.role == "business"
        user = self._users.create( 
            NewUser(
                email = normalize_email(registration.email),
                password_hash = hash_password(registration.password),
                full_name = registration.full_name.strip(),
                phone = (registration.phone or "").strip() or None,
                role = registration.role,
                shop_name = (registration.shop_name or "").strip() or None if is_business else None
            )
        )
        
        return self.open_session(user)
    
    
    def login(self , email : str , password : str) -> LoginResult:
        now = self._clock()
        credentials = self._users.get_credentials(normalize_email(email))
        
        if credentials is None:
            burn_password_check(password)
            raise InvalidCredentialsError
        
        self.verify_or_record_failure(credentials , password , now)
        
        if credentials.failed_login_count or credentials.locked_until:
            self._users.clear_failed_logins(credentials.user.user_id)
            
        if needs_rehash(credentials.password_hash):
            self._users.set_password_hash(credentials.user.user_id , hash_password(password))
            
        return self.open_session(credentials.user)
    

    def authenticate(self , token : str | None) -> User | None:
        # Resolve a cookie token to its user
        if not token: return None
        
        now = self._clock()
        token_hash = hash_token(token)
        session = self._sessions.get_session(token_hash , now = now)
        
        if session is None: return None
        
        if now - session.last_seen_at >= self._config.touch_after:
            self._sessions.touch_session(
                token_hash,
                now = now,
                expires_at = now + self._config.session_ttl
            )
            
        return session.user
    
    
    def logout(self , token : str | None) -> None:
        if token:
            self._sessions.delete_session(hash_token(token))
            
    
    def change_password(self, user : User , current_password : str , new_password : str) -> LoginResult:
        # Replace the password, revoke every session and sign in again with a fresh token
        
        require_valid_password(new_password)
        now = self._clock()
        credentials = self._users.get_credentials(user.email)
        
        if credentials is None:
            raise InvalidCredentialsError
        
        try:
            self.verify_or_record_failure(credentials, current_password, now)
        except InvalidCredentialsError:
            raise WrongPasswordError from None
        
        self._users.set_password_hash(user.user_id , hash_password(new_password))
        self._sessions.delete_sessions_for_user(user.user_id)
        
        return self.open_session(user)
    
    def update_profile(
        self,
        user : User,
        *,
        full_name : str,
        phone : str | None,
        shop_name : str | None
    ) -> User:
        
        is_business = user.role == "business"
        shop = (shop_name or "").strip() or None if is_business else None
        if is_business and shop is None:
            raise InvalidProfileError
        return self._users.update_profile(
            user.user_id,
            full_name = full_name.strip(),
            phone = (phone or "").strip() or None,
            shop_name = shop,
        )
        
    
    # -- Internal helpers
    def verify_or_record_failure(
        self,
        credentials : Credentials,
        password : str,
        now : datetime
    ) -> None:
        # A locked account is rejected before hashing
        
        if credentials.locked_until is not None and credentials.locked_until > now:
            raise AccountLockedError(credentials.locked_until - now)
        
        if not verify_password(password , credentials.password_hash):
            self._users.record_failed_login(
                credentials.user.user_id,
                max_failures = self._config.max_failures,
                lock_for = self._config.lock_for,
                now = now
            )
            raise InvalidCredentialsError
        
        
    def open_session(self , user : User) -> LoginResult:
        # Create a new session for an existing user
        now = self._clock()
        token = secrets.token_urlsafe(32)
        token_hash = hash_token(token)
        
        self._sessions.create_session(
            token_hash,
            user.user_id,
            now = now,
            expires_at = now + self._config.session_ttl
        )
        
        self._sweep_expired(now)

        return LoginResult(user , token)


    def _sweep_expired(self , now : datetime) -> None:
        # Best effort and at most once per cleanup_every : a sign-in never fails because of it
        last = self._last_cleanup
        if last is not None and now - last < self._config.cleanup_every:
            return

        self._last_cleanup = now
        try:
            self._sessions.delete_expired_sessions(now = now)
        except Exception:
            pass # ponytail: swallowed on purpose , the next sign-in after cleanup_every tries again
        