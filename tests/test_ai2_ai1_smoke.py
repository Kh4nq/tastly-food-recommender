from common.schemas import Location, UserPreferenceState
from retrieval import retrieve_candidates


class FakeSentenceTransformer:
    def __init__(self, *args, **kwargs):
        pass

    def encode(
        self,
        texts,
        convert_to_numpy=True,
        normalize_embeddings=True,
    ):
        import numpy as np

        # Chỉ cần shape hợp lệ để đi qua bước query encoding.
        # Giá trị này không được dùng để đánh giá chất lượng semantic
        # vì score_candidates đã được mock riêng.
        return np.zeros((len(texts), 4), dtype=np.float32)

def fake_score_candidates(candidates, *args, **kwargs):
    out = candidates.copy()

    out["semantic_score"] = 0.5
    out["dish_similarity"] = 0.5
    out["restaurant_similarity"] = 0.5

    return out


def test_ai2_state_can_flow_into_ai1(monkeypatch):
    import sentence_transformers
    import retrieval.vector_search as vector_search

    # Prevent Hugging Face/network access.
    monkeypatch.setattr(
        sentence_transformers,
        "SentenceTransformer",
        FakeSentenceTransformer,
    )

    # Prevent dependency on real embedding dimensions/artifacts.
    monkeypatch.setattr(
        vector_search,
        "score_candidates",
        fake_score_candidates,
    )

    state = UserPreferenceState(
        session_id="smoke-ai2-ai1",
        location=Location(
            lat=10.77,
            lon=106.69,
        ),
        food=["ph\u1edf"],
        hard_constraints={
            "budget_max": 100000,
            "max_distance_km": 5,
        },
    )

    candidates = retrieve_candidates(
        state,
        top_k=20,
    )

    assert candidates
    assert len(candidates) <= 20

    seen_menu_items = set()

    for candidate in candidates:
        # Shared identity contract.
        assert candidate.restaurant_id
        assert candidate.menu_item_id
        assert candidate.dish_id

        assert candidate.menu_item_id not in seen_menu_items
        seen_menu_items.add(candidate.menu_item_id)

        # Hard constraints must already have been applied by AI1.
        if candidate.distance_km is not None:
            assert 0 <= candidate.distance_km <= 5.0001

        if candidate.price is not None:
            assert 0 <= candidate.price <= 100000

        # AI1 retrieval evidence.
        assert "food_match" in candidate.match_features
        assert 0.0 <= candidate.match_features["food_match"] <= 1.0

        assert "semantic_similarity" in candidate.match_features
        assert (
            -1.00001
            <= candidate.match_features["semantic_similarity"]
            <= 1.00001
        )

        # Vector evidence propagated through Candidate.
        assert candidate.match_features["dish_similarity"] == 0.5
        # Display-name-contaminated restaurant vectors are neutralized for the
        # synthetic catalog; dish-only similarity remains available to CatBoost.
        assert candidate.match_features["restaurant_similarity"] == 0.0
