# PostgreSQL auth stores. One object implements UserStore and AuthSessionStore,
# like the in-memory one, because a session resolves to its user with a JOIN
from datetime import datetime, timedelta

from psycopg import errors
from psycopg_pool import ConnectionPool

from backend.ports import ActiveSession, Credentials, EmailTakenError, NewUser, User

# Constant column list, never user input, so it is safe to put in an f-string
_USER_COLUMNS = "user_id, email, full_name, phone, role, shop_name"


def _user(row) -> User:
    # The first six columns of every query below follow _USER_COLUMNS
    user_id, email, full_name, phone, role, shop_name = row[:6]
    return User(str(user_id), email, full_name, phone, role, shop_name)


class PostgresAuthStore:
    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    # -- UserStore ---------------------------------------------------------
    def create(self, new: NewUser) -> User:
        sql = (
            "INSERT INTO users (email, password_hash, full_name, phone, role, shop_name) "
            f"VALUES (%s, %s, %s, %s, %s, %s) RETURNING {_USER_COLUMNS}"
        )
        params = (new.email, new.password_hash, new.full_name, new.phone, new.role, new.shop_name)
        try:
            with self._pool.connection() as conn:
                row = conn.execute(sql, params).fetchone()
        except errors.UniqueViolation:
            raise EmailTakenError from None  # uq_users_email: the database decides who wins
        except errors.CheckViolation as exc:
            # Same type the in-memory store raises, so both stores obey one contract
            raise ValueError(f"violates {exc.diag.constraint_name}") from None
        return _user(row)

    def get_credentials(self, email: str) -> Credentials | None:
        sql = (
            f"SELECT {_USER_COLUMNS}, password_hash, failed_login_count, locked_until "
            "FROM users WHERE email = %s"
        )
        with self._pool.connection() as conn:
            row = conn.execute(sql, (email,)).fetchone()
        if row is None:
            return None
        return Credentials(_user(row), row[6], row[7], row[8])

    def record_failed_login(
        self, user_id: str, *, max_failures: int, lock_for: timedelta, now: datetime
    ) -> None:
        with self._pool.connection() as conn:  # one transaction
            # FOR UPDATE holds the row until commit, so concurrent failures queue up
            count, locked_until = conn.execute(
                "SELECT failed_login_count, locked_until FROM users WHERE user_id = %s FOR UPDATE",
                (user_id,),
            ).fetchone()
            if locked_until is not None and locked_until <= now:
                count, locked_until = 0, None  # the old lock expired: start over
            count += 1
            if count >= max_failures:
                locked_until = now + lock_for
            conn.execute(
                "UPDATE users SET failed_login_count = %s, locked_until = %s, updated_at = now() "
                "WHERE user_id = %s",
                (count, locked_until, user_id),
            )

    def clear_failed_logins(self, user_id: str) -> None:
        with self._pool.connection() as conn:
            conn.execute(
                "UPDATE users SET failed_login_count = 0, locked_until = NULL, updated_at = now() "
                "WHERE user_id = %s",
                (user_id,),
            )

    def set_password_hash(self, user_id: str, password_hash: str) -> None:
        with self._pool.connection() as conn:
            conn.execute(
                "UPDATE users SET password_hash = %s, updated_at = now() WHERE user_id = %s",
                (password_hash, user_id),
            )

    def update_profile(
        self, user_id: str, *, full_name: str, phone: str | None, shop_name: str | None
    ) -> User:
        sql = (
            "UPDATE users SET full_name = %s, phone = %s, shop_name = %s, updated_at = now() "
            f"WHERE user_id = %s RETURNING {_USER_COLUMNS}"
        )
        try:
            with self._pool.connection() as conn:
                row = conn.execute(sql, (full_name, phone, shop_name, user_id)).fetchone()
        except errors.CheckViolation as exc:
            raise ValueError(f"violates {exc.diag.constraint_name}") from None
        return _user(row)

    # -- AuthSessionStore --------------------------------------------------
    def create_session(
        self, token_hash: str, user_id: str, *, now: datetime, expires_at: datetime
    ) -> None:
        try:
            with self._pool.connection() as conn:
                conn.execute(
                    "INSERT INTO auth_sessions (token_hash, user_id, created_at, last_seen_at, expires_at) "
                    "VALUES (%s, %s, %s, %s, %s)",
                    (token_hash, user_id, now, now, expires_at),
                )
        except errors.UniqueViolation:
            raise ValueError("token_hash already exists") from None

    def get_session(self, token_hash: str, *, now: datetime) -> ActiveSession | None:
        sql = (
            "SELECT u.user_id, u.email, u.full_name, u.phone, u.role, u.shop_name, "
            "s.last_seen_at, s.expires_at "
            "FROM auth_sessions s JOIN users u ON u.user_id = s.user_id "
            "WHERE s.token_hash = %s AND s.expires_at > %s"  # expired = does not exist
        )
        with self._pool.connection() as conn:
            row = conn.execute(sql, (token_hash, now)).fetchone()
        if row is None:
            return None
        return ActiveSession(_user(row), row[6], row[7])

    def touch_session(self, token_hash: str, *, now: datetime, expires_at: datetime) -> None:
        with self._pool.connection() as conn:
            conn.execute(
                "UPDATE auth_sessions SET last_seen_at = %s, expires_at = %s WHERE token_hash = %s",
                (now, expires_at, token_hash),
            )

    def delete_session(self, token_hash: str) -> None:
        with self._pool.connection() as conn:
            conn.execute("DELETE FROM auth_sessions WHERE token_hash = %s", (token_hash,))

    def delete_sessions_for_user(self, user_id: str, *, keep: str | None = None) -> None:
        with self._pool.connection() as conn:
            # IS DISTINCT FROM, not <>: with keep=None, `token_hash <> NULL` is NULL and
            # matches no row, so "revoke everything" would silently revoke nothing
            conn.execute(
                "DELETE FROM auth_sessions "
                "WHERE user_id = %s AND token_hash IS DISTINCT FROM %s",
                (user_id, keep),
            )

    def delete_expired_sessions(self, *, now: datetime) -> int:
        with self._pool.connection() as conn:
            return conn.execute(
                "DELETE FROM auth_sessions WHERE expires_at <= %s", (now,)
            ).rowcount