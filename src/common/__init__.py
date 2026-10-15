"""Shared contracts for the food recommendation modules."""

from common.schemas import (
    Candidate,
    FeedbackEvent,
    Location,
    PreferenceUpdate,
    PreviousResult,
    RankedResult,
    RecommendationResponse,
    UserFormInput,
    UserPreferenceState,
    UserRequest,
)

__all__ = [
    "Location", "PreferenceUpdate", "UserFormInput", "UserPreferenceState", "UserRequest",
    "Candidate", "RankedResult", "FeedbackEvent", "RecommendationResponse", "PreviousResult",
]
