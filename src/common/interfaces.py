"""Callable protocols: functions and callable objects need no inheritance."""

from typing import Protocol

from common.schemas import Candidate, PreferenceUpdate, RankedResult, UserPreferenceState, UserRequest


class ConversationModule(Protocol):
    def __call__(self, request: UserRequest) -> PreferenceUpdate: ...


class StateManager(Protocol):
    def __call__(
        self, current_state: UserPreferenceState | None, update: PreferenceUpdate,
        session_id: str, user_id: str | None = None,
    ) -> UserPreferenceState: ...


class RetrievalModule(Protocol):
    def __call__(self, state: UserPreferenceState, top_k: int = 100) -> list[Candidate]: ...


class RankingModule(Protocol):
    def __call__(
        self, state: UserPreferenceState, candidates: list[Candidate], top_k: int = 10,
    ) -> list[RankedResult]: ...
