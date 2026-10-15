import pandas as pd
import pytest

from common.schemas import Candidate, Location, UserPreferenceState
from retrieval.retriever import retrieve_candidates


class FakeRetriever:
    def __init__(self):
        self.restaurants = pd.DataFrame([
            {
                'food_place_id': 'osm:1',
                'name': 'Quán A',
                'latitude': 21.03,
                'longitude': 105.85,
                'place_type': 'restaurant',
                'supported_cuisine': 'vietnamese',
                'is_recommendable': True,
            }
        ])

        self.dishes = pd.DataFrame([
            {
                'dish_id': 'dish:1',
                'dish_name': 'Bún chay',
                'supported_cuisine': 'vietnamese',
                'is_vegetarian': True,
            }
        ])

        self.calls = []

    def retrieve_frame(self, state, top_k):
        self.calls.append((state, top_k))

        return pd.DataFrame([
            {
                'restaurant_id': 'osm:1',
                'menu_item_id': 'menu:1',
                'dish_id': 'dish:1',
                'distance_km': 1.25,
                'semantic_score': 0.76,
                'dish_similarity': 0.82,
                'restaurant_similarity': 0.58,
                'price': 56000,
                'price_is_verified': False,
            }
        ]).head(top_k)


def test_canonical_candidate_contract():
    fake = FakeRetriever()

    state = UserPreferenceState(
        session_id='t1',
        location=Location(
            lat=21.03,
            lon=105.85,
        ),
        food=['bún chay'],
        hard_constraints={
            'budget_max': 100000,
        },
        negative_preferences=[
            'không cay',
        ],
        reference_restaurants=[
            'osm:reference-1',
        ],
        context={
            'transport_mode': 'motorbike',
            'party_size': 2,
            'meal_time': 'dinner',
        },
    )

    result = retrieve_candidates(
        state,
        50,
        retriever=fake,
    )

    assert len(result) == 1
    assert isinstance(result[0], Candidate)

    candidate = result[0]

    assert candidate.restaurant_id == 'osm:1'
    assert candidate.menu_item_id == 'menu:1'
    assert candidate.dish_id == 'dish:1'

    assert candidate.restaurant_name == 'Quán A'
    assert candidate.dish_name == 'Bún chay'

    assert candidate.price == 56000
    assert candidate.distance_km == pytest.approx(1.25)

    # AI1 -> AI3 match features
    assert candidate.match_features[
        'semantic_similarity'
    ] == pytest.approx(0.76)

    assert candidate.match_features[
        'dish_similarity'
    ] == pytest.approx(0.82)

    assert candidate.match_features[
        'restaurant_similarity'
    ] == pytest.approx(0.58)

    assert candidate.restaurant_features[
        'price_is_verified'
    ] is False

    internal_state = fake.calls[0][0]

    assert internal_state[
        'negative_preferences'
    ] == [
        'không cay',
    ]

    assert internal_state[
        'reference_restaurants'
    ] == [
        'osm:reference-1',
    ]

    assert internal_state[
        'context'
    ] == {
        'transport_mode': 'motorbike',
        'party_size': 2,
        'meal_time': 'dinner',
    }


def test_requires_shared_state():
    with pytest.raises(
        TypeError,
        match='UserPreferenceState',
    ):
        retrieve_candidates(
            {},
            1,
            retriever=FakeRetriever(),
        )


def test_invalid_top_k():
    with pytest.raises(ValueError):
        retrieve_candidates(
            UserPreferenceState(session_id='t'),
            0,
            retriever=FakeRetriever(),
        )


def test_invalid_dish_similarity_rejected():
    fake = FakeRetriever()

    def bad_retrieve_frame(state, top_k):
        return pd.DataFrame([
            {
                'restaurant_id': 'osm:1',
                'menu_item_id': 'menu:1',
                'dish_id': 'dish:1',
                'distance_km': 1.25,
                'semantic_score': 0.76,

                # Invalid cosine similarity
                'dish_similarity': 1.5,

                'restaurant_similarity': 0.58,
                'price': 56000,
                'price_is_verified': False,
            }
        ]).head(top_k)

    fake.retrieve_frame = bad_retrieve_frame

    state = UserPreferenceState(
        session_id='t',
    )

    with pytest.raises(
        ValueError,
        match='dish similarity',
    ):
        retrieve_candidates(
            state,
            50,
            retriever=fake,
        )


def test_invalid_restaurant_similarity_rejected():
    fake = FakeRetriever()

    def bad_retrieve_frame(state, top_k):
        return pd.DataFrame([
            {
                'restaurant_id': 'osm:1',
                'menu_item_id': 'menu:1',
                'dish_id': 'dish:1',
                'distance_km': 1.25,
                'semantic_score': 0.76,
                'dish_similarity': 0.82,

                # Invalid cosine similarity
                'restaurant_similarity': -1.5,

                'price': 56000,
                'price_is_verified': False,
            }
        ]).head(top_k)

    fake.retrieve_frame = bad_retrieve_frame

    state = UserPreferenceState(
        session_id='t',
    )

    with pytest.raises(
        ValueError,
        match='restaurant similarity',
    ):
        retrieve_candidates(
            state,
            50,
            retriever=fake,
        )