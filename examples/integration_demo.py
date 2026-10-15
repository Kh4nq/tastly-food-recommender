"""Offline integration: real AI 2 rules/state, explicitly synthetic AI 1/AI 3.

Run from the repository: python examples/integration_demo.py
No .env loading, SDK initialization, SLM inference or external calls.
"""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from common.constants import AI_INTERFACE_VERSION
from common.schemas import Candidate, PreferenceUpdate, RankedResult, UserPreferenceState, UserRequest
from conversation.config import ConversationConfig
from conversation.parser import parse_user_input_detailed
from pipeline import recommend


def offline_parse(request: UserRequest) -> PreferenceUpdate:
    """Use real parsing with explicit offline configuration, independent of env."""
    result = parse_user_input_detailed(
        request, config=ConversationConfig(llm_provider="none", local_slm_enabled=False),
    )
    if result.metadata.requires_llm or result.metadata.llm_called or result.metadata.slm_called:
        raise RuntimeError("This demo requires a fully rule-sufficient request")
    return result.preference_update


def mock_retrieve_candidates(state: UserPreferenceState, top_k: int = 100) -> list[Candidate]:
    """Return a tiny synthetic fixture, not a retrieval algorithm or real listing."""
    return [Candidate(
        restaurant_id="DEMO-R001", menu_item_id="DEMO-M053", dish_id="DEMO-D018",
        restaurant_name="Synthetic Ramen Demo", dish_name="Demo Tonkotsu Ramen",
        location={"lat": 10.771, "lon": 106.691},
        distance_km=0.8 if state.location is not None else None, price=120000,
        restaurant_features={"rating": 4.5, "cuisine": ["japanese"], "synthetic": True},
        match_features={"semantic_similarity": 0.91, "food_similarity": 0.94},
    )][:top_k]


def mock_rank_candidates(
    state: UserPreferenceState, candidates: list[Candidate], top_k: int = 10,
) -> list[RankedResult]:
    """Keep fixture order with a synthetic score; this is not a ranking model."""
    return [RankedResult(
        restaurant_id=candidate.restaurant_id, menu_item_id=candidate.menu_item_id,
        dish_id=candidate.dish_id, restaurant_name=candidate.restaurant_name,
        dish_name=candidate.dish_name, price=candidate.price, distance_km=candidate.distance_km,
        rating=candidate.restaurant_features.get("rating"), rank=position, score=0.92,
        reason_features={"synthetic": True, "food_match": candidate.match_features.get("food_similarity")},
    ) for position, candidate in enumerate(candidates[:top_k], start=1)]


def main() -> None:
    request = UserRequest(
        session_id="offline-demo", form={"location": {"lat": 10.77, "lon": 106.69}},
        message="Ăn ramen dưới 150k trong 3km",
    )
    response = recommend(
        request, parse_fn=offline_parse,
        retrieve_fn=mock_retrieve_candidates, rank_fn=mock_rank_candidates,
    )
    print(f"Interface {AI_INTERFACE_VERSION}: real AI 2 + synthetic AI 1/AI 3 (offline)")
    print(response.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
