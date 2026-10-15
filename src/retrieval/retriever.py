"""AI1 retrieval: shared UserPreferenceState -> canonical Candidate list."""
from __future__ import annotations
from functools import lru_cache
from pathlib import Path
from typing import Any
import math
import os
import re
import unicodedata

from common.schemas import Candidate, Location, UserPreferenceState

# Browse mode (no food query): cap dishes per restaurant so one place cannot fill the list
BROWSE_MAX_DISHES_PER_RESTAURANT = 1


def _phrases(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, dict):
        result = []
        for key, val in value.items():
            if val is True:
                result.append(str(key).replace('_', ' ').strip())
            elif val not in (False, None, '', [], {}):
                result.append(f'{str(key).replace("_", " ")} {val}'.strip())
        return result
    if isinstance(value, (list, tuple, set)):
        return [str(x).strip() for x in value if x is not None and str(x).strip()]
    raise ValueError('Preference fields must be string, list or dict')

_VI_TONE_TRANSLATION = str.maketrans({
    # a
    "á": "a", "à": "a", "ả": "a", "ã": "a", "ạ": "a",
    "Á": "a", "À": "a", "Ả": "a", "Ã": "a", "Ạ": "a",

    # ă
    "ắ": "ă", "ằ": "ă", "ẳ": "ă", "ẵ": "ă", "ặ": "ă",
    "Ắ": "ă", "Ằ": "ă", "Ẳ": "ă", "Ẵ": "ă", "Ặ": "ă",

    # â
    "ấ": "â", "ầ": "â", "ẩ": "â", "ẫ": "â", "ậ": "â",
    "Ấ": "â", "Ầ": "â", "Ẩ": "â", "Ẫ": "â", "Ậ": "â",

    # e
    "é": "e", "è": "e", "ẻ": "e", "ẽ": "e", "ẹ": "e",
    "É": "e", "È": "e", "Ẻ": "e", "Ẽ": "e", "Ẹ": "e",

    # ê
    "ế": "ê", "ề": "ê", "ể": "ê", "ễ": "ê", "ệ": "ê",
    "Ế": "ê", "Ề": "ê", "Ể": "ê", "Ễ": "ê", "Ệ": "ê",

    # i
    "í": "i", "ì": "i", "ỉ": "i", "ĩ": "i", "ị": "i",
    "Í": "i", "Ì": "i", "Ỉ": "i", "Ĩ": "i", "Ị": "i",

    # o
    "ó": "o", "ò": "o", "ỏ": "o", "õ": "o", "ọ": "o",
    "Ó": "o", "Ò": "o", "Ỏ": "o", "Õ": "o", "Ọ": "o",

    # ô
    "ố": "ô", "ồ": "ô", "ổ": "ô", "ỗ": "ô", "ộ": "ô",
    "Ố": "ô", "Ồ": "ô", "Ổ": "ô", "Ỗ": "ô", "Ộ": "ô",

    # ơ
    "ớ": "ơ", "ờ": "ơ", "ở": "ơ", "ỡ": "ơ", "ợ": "ơ",
    "Ớ": "ơ", "Ờ": "ơ", "Ở": "ơ", "Ỡ": "ơ", "Ợ": "ơ",

    # u
    "ú": "u", "ù": "u", "ủ": "u", "ũ": "u", "ụ": "u",
    "Ú": "u", "Ù": "u", "Ủ": "u", "Ũ": "u", "Ụ": "u",

    # ư
    "ứ": "ư", "ừ": "ư", "ử": "ư", "ữ": "ư", "ự": "ư",
    "Ứ": "ư", "Ừ": "ư", "Ử": "ư", "Ữ": "ư", "Ự": "ư",

    # y
    "ý": "y", "ỳ": "y", "ỷ": "y", "ỹ": "y", "ỵ": "y",
    "Ý": "y", "Ỳ": "y", "Ỷ": "y", "Ỹ": "y", "Ỵ": "y",

    "Đ": "đ",
})


def _normalize_search_text(value: Any) -> str:
    """Remove Vietnamese tone marks while preserving vowel identity."""
    if value is None:
        return ""

    text = unicodedata.normalize("NFC", str(value))
    text = text.translate(_VI_TONE_TRANSLATION)
    text = text.casefold()
    text = re.sub(r"\s+", " ", text).strip()

    return text


def _contains_phrase(text: str, phrase: str) -> bool:
    """Whole-word/phrase match to avoid pho matching Phomai / Hai Phong."""
    text_norm = _normalize_search_text(text)
    phrase_norm = _normalize_search_text(phrase)

    if not text_norm or not phrase_norm:
        return False

    pattern = rf"(?<!\w){re.escape(phrase_norm)}(?!\w)"
    return re.search(pattern, text_norm) is not None


def _add_food_match(candidates, dishes, user_state: dict):
    """
    Add evidence-based lexical food_match.

    1.0 = dish name exactly equals requested food
    0.95 = dish name starts with requested food
    0.9 = requested food appears as a whole word/phrase elsewhere
    0.85 = all requested words occur in a supported qualified/reordered name
    0.0 = no lexical match
    """
    import numpy as np

    out = candidates.copy()

    foods = [
        str(x).strip()
        for x in _phrases(user_state.get("food"))
        if str(x).strip()
    ]

    if not foods or out.empty:
        out["food_match"] = np.float32(0.0)
        out['food_family_match'] = False
        return out

    dish_name_map = (
        dishes[["dish_id", "dish_name"]]
        .drop_duplicates("dish_id")
        .set_index("dish_id")["dish_name"]
    )

    from .food_matching import food_evidence
    evidence = dish_name_map.map(lambda name: food_evidence(name, foods))
    out['food_match'] = out.dish_id.map(evidence.map(lambda pair: pair[0])).fillna(0).astype('float32')
    out['food_family_match'] = out.dish_id.map(evidence.map(lambda pair: pair[1])).fillna(False).astype(bool)
    return out

def state_to_query(state: dict) -> str:
    """Build positive semantic text only; hard numeric limits are never embedded."""
    segments = []

    for key, label in [
        ("food", "Món ăn"),
        ("cuisine", "Ẩm thực"),
        ("soft_preferences", "Sở thích"),
        ("semantic_preferences", "Mong muốn"),
    ]:
        values = _phrases(state.get(key))

        if values:
            segments.append(f'{label}: {", ".join(values)}')

    context = state.get('context') or {}
    # Positive categorical context only. Numeric limits, identity, transport
    # and negatives are handled separately rather than embedded as positives.
    context_values = []
    for key in ('occasion', 'meal_time'):
        value = context.get(key)
        if isinstance(value, str) and value.strip():
            context_values.append(f'{key}: {value.strip()}')
    context_values.extend(f'companions: {v}' for v in _phrases(context.get('companions')))
    if context_values:
        segments.append('Context: ' + ', '.join(context_values))

    return ". ".join(segments)


def _shared_to_internal(state: UserPreferenceState) -> dict:
    return {
        'location': [state.location.lat, state.location.lon] if state.location else None,
        'hard_constraints': dict(state.hard_constraints),
        'food': list(state.food),
        'cuisine': list(state.cuisine),
        'soft_preferences': dict(state.soft_preferences),
        'semantic_preferences': list(state.semantic_preferences),
        'negative_preferences': list(state.negative_preferences),
        'reference_restaurants': list(state.reference_restaurants),
        'context': dict(state.context),
    }

def _json_value(value: Any):
    import numpy as np
    import pandas as pd
    if value is None or value is pd.NA:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, np.generic):
        return value.item()
    return value


class Retriever:
    """Internal dataframe retriever backed by local processed data and embeddings."""
    def __init__(self, processed_dir='data/processed', embeddings_dir='data/embeddings',
                 model=None, dish_weight=0.75, validate_menu_map=True):
        from .hard_filter import load_tables
        from .embedder import DEFAULT_MODEL, load_embeddings, _sha256
        self.processed_dir = Path(processed_dir)
        self.embeddings_dir = Path(embeddings_dir)
        self.restaurants, self.dishes, self.menus = load_tables(self.processed_dir)
        (self.restaurant_vectors, self.restaurant_ids,
         self.dish_vectors, self.dish_ids,
         self.menu_map, self.metadata) = load_embeddings(self.embeddings_dir)
        supported_dataset_versions = {
            'v2-original-ids',
            'v3-menu',
        }

        if self.metadata.get('dataset_version') not in supported_dataset_versions:
            raise ValueError(
                'Unsupported embedding dataset version; '
                'regenerate from current Parquets'
            )
        source_files = self.metadata.get('source_files')
        if source_files:
            for filename, expected_hash in source_files.items():
                source_path = self.processed_dir / filename

                if not source_path.exists():
                    raise ValueError(
                        f'Embedding source file is missing: {filename}'
                    )

                actual_hash = _sha256(source_path)

                if actual_hash != expected_hash:
                    raise ValueError(
                        f'{filename} differs from the data used to build '
                        'embeddings; regenerate embeddings'
                    )
        if not 0 <= dish_weight <= 1:
            raise ValueError('dish_weight must be between 0 and 1')
        self.dish_weight = dish_weight
        if validate_menu_map:
            actual = self.menus[['menu_item_id', 'food_place_id', 'dish_id']].sort_values('menu_item_id').reset_index(drop=True)
            stored = self.menu_map[['menu_item_id', 'food_place_id', 'dish_id']].sort_values('menu_item_id').reset_index(drop=True)
            if not actual.equals(stored):
                raise ValueError('menu_to_vectors.parquet differs from processed menu_items; regenerate embeddings')
        from .profiles import load_restaurant_profiles
        self.restaurants = load_restaurant_profiles(self.processed_dir, self.restaurants)
        self.model_name = self.metadata.get('model', DEFAULT_MODEL)
        self.model = model

    def retrieve_frame(self, user_state: dict, top_k: int = 100):
        import numpy as np
        import pandas as pd
        from .hard_filter import filter_candidates
        from .vector_search import score_candidates
        if isinstance(top_k, bool) or not isinstance(top_k, int) or top_k < 1:
            raise ValueError('top_k must be a positive integer')
        candidates = filter_candidates(self.restaurants, self.dishes, self.menus, user_state)
        candidates = _add_food_match(
            candidates, 
            self.dishes, 
            user_state,
        )
        # A named dish search must not turn lexical misses into menu matches.
        # Apply before truncation/ranking; return an honest empty list if absent.
        named = bool(_phrases(user_state.get('food')))
        if named:
            # Preserve zero-match rows with independent dish-family evidence.
            # Restaurant embeddings/names alone cannot qualify a menu alternative.
            candidates = candidates.loc[candidates.food_match.gt(0) | candidates.food_family_match].copy()
        from .preference_matching import add_preference_evidence
        candidates = add_preference_evidence(candidates, self.restaurants, self.dishes, user_state)
        if candidates.empty:
            candidates['semantic_score'] = pd.Series(dtype='float32')
        else:
            query = state_to_query(user_state)
            if query:
                if self.model is None:
                    from sentence_transformers import SentenceTransformer
                    # Query encoder only; offline embedding construction is unchanged.
                    device = os.getenv('AI1_EMBEDDING_DEVICE', '').strip()
                    options = {'device': device} if device else {}
                    self.model = SentenceTransformer(self.model_name, **options)

                query_vector = self.model.encode(
                    [query],
                    convert_to_numpy=True,
                    normalize_embeddings=True,
                )
                candidates = score_candidates(
                    candidates, np.asarray(query_vector),
                    self.restaurant_vectors, self.restaurant_ids,
                    self.dish_vectors, self.dish_ids,
                    dish_weight=self.dish_weight,
                )
                # Existing restaurant embeddings include display names. Those
                # names are arbitrary in this catalog, so neutralize that signal
                # without regenerating artifacts or changing CatBoost's schema.
                candidates['restaurant_similarity'] = np.float32(0)
                candidates['semantic_score'] = candidates['dish_similarity']
                candidates = candidates.sort_values(
                    ["food_match", "preference_mismatches", "preference_matches", "semantic_score", "menu_item_id"],
                    ascending=[False, True, False, False, True], kind='stable')
            else:
                candidates['semantic_score'] = np.float32(0)
                candidates = candidates.sort_values(
                    ["food_match", "preference_mismatches", "preference_matches", "distance_km", "price", "menu_item_id"],
                    ascending=[False, True, False, True, True, True],
                    na_position="last",
                    kind="stable",
                )
                # Rows are already sorted, so head(n) keeps each restaurant's best dishes
                candidates = candidates.groupby("restaurant_id", sort=False).head(
                    BROWSE_MAX_DISHES_PER_RESTAURANT
                )
        if named and not candidates.empty:
            # Lexical family evidence plus a modest dish-only cosine floor.
            # This is a conservative gate, not a measured relevance probability.
            candidates = candidates.loc[candidates.food_match.gt(0) | candidates.dish_similarity.ge(.25)].copy()
        candidates['recommendation_group'] = candidates.food_match.map(lambda score: 'primary' if score > 0 else 'supplementary') if named else 'general'
        from .food_matching import bounded_pools
        return bounded_pools(candidates, top_k, named).reset_index(drop=True)

    # Backward-compatible internal method for AI1 notebooks/demos.
    def retrieve_candidates(self, user_state: dict, top_k: int = 100):
        return self.retrieve_frame(user_state, top_k)


@lru_cache(maxsize=2)
def _cached_engine(processed_dir: str, embeddings_dir: str) -> Retriever:
    return Retriever(processed_dir=processed_dir, embeddings_dir=embeddings_dir)


def _frame_to_candidates(frame, engine: Retriever, top_k: int) -> list[Candidate]:
    if len(frame) > top_k:
        raise ValueError("Retriever returned more than top_k rows")

    if frame.empty:
        return []

    if frame["menu_item_id"].duplicated().any():
        raise ValueError("Duplicate menu_item_id in retrieval result")

    place_cols = [
        c
        for c in [
            "food_place_id",
            "name",
            "latitude",
            "longitude",
            "place_type",
            "supported_cuisine",
            "cuisine",
            "is_recommendable",
            "profile_evidence",
            "profile_parking", "profile_wifi", "profile_air_conditioning",
            "profile_outdoor_seating", "profile_wheelchair_accessible",
            "profile_quiet", "profile_family_friendly", "profile_highchair",
            "profile_kids_area", "profile_capacity",
        ]
        if c in engine.restaurants
    ]

    dish_cols = [
        c
        for c in [
            "dish_id",
            "dish_name",
            "supported_cuisine",
            "cuisine_origin",
            "is_vegetarian",
            "primary_category", "meal_role", "main_protein",
            "primary_cooking_style", "calories", "ingredients", "cooking_method",
            "source", "taxonomy_source", "cuisine_confidence", "cuisine_evidence",
            "is_spicy", "calorie_source",
        ]
        if c in engine.dishes
    ]

    enriched = frame.merge(
        engine.restaurants[place_cols],
        left_on="restaurant_id",
        right_on="food_place_id",
        how="left",
        validate="many_to_one",
    )

    enriched = enriched.merge(
        engine.dishes[dish_cols],
        on="dish_id",
        how="left",
        validate="many_to_one",
        suffixes=("_restaurant", "_dish"),
    )

    result = []

    for row in enriched.to_dict("records"):
        distance = _json_value(row.get("distance_km"))
        score = _json_value(row.get("semantic_score"))
        dish_similarity = _json_value(row.get("dish_similarity"))
        restaurant_similarity = _json_value(
            row.get("restaurant_similarity")
        )
        food_match = _json_value(row.get("food_match"))
        price = _json_value(row.get("price"))

        lat = _json_value(row.get("latitude"))
        lon = _json_value(row.get("longitude"))

        location = (
            Location(lat=float(lat), lon=float(lon))
            if lat is not None and lon is not None
            else None
        )

        # Validate numeric retrieval outputs.
        if distance is not None and (
            not math.isfinite(float(distance))
            or float(distance) < 0
        ):
            raise ValueError(
                "distance_km must be nonnegative or None"
            )

        if score is not None and (
            not math.isfinite(float(score))
            or not -1.00001 <= float(score) <= 1.00001
        ):
            raise ValueError(
                "semantic similarity must be finite cosine in [-1,1]"
            )

        if dish_similarity is not None and (
            not math.isfinite(float(dish_similarity))
            or not -1.00001 <= float(dish_similarity) <= 1.00001
        ):
            raise ValueError(
                "dish similarity must be finite cosine in [-1,1]"
            )

        if restaurant_similarity is not None and (
            not math.isfinite(float(restaurant_similarity))
            or not -1.00001 <= float(restaurant_similarity) <= 1.00001
        ):
            raise ValueError(
                "restaurant similarity must be finite cosine in [-1,1]"
            )

        if food_match is not None and (
            not math.isfinite(float(food_match))
            or not 0.0 <= float(food_match) <= 1.0
        ):
            raise ValueError(
                "food_match must be finite and in [0,1]"
            )

        if price is not None and (
            not math.isfinite(float(price))
            or float(price) < 0
        ):
            raise ValueError(
                "price must be nonnegative or None"
            )

        # Features describing the restaurant itself.
        restaurant_features = {}

        for key in (
            "place_type",
            "supported_cuisine_restaurant",
            "cuisine",
            "is_recommendable",
        ):
            value = _json_value(row.get(key))

            if value is not None:
                restaurant_features[key] = value

        restaurant_features["price_is_verified"] = bool(
            _json_value(row.get("price_is_verified")) or False
        )
        if getattr(engine, 'metadata', {}).get('usage') == 'synthetic_demo':
            restaurant_features['demo_only'] = True
        from .profiles import PROFILE_FIELDS
        if 'profile_evidence' in row:
            for key in (*PROFILE_FIELDS, 'capacity'):
                restaurant_features[key] = _json_value(row.get(f'profile_{key}'))
            restaurant_features['profile_evidence'] = row['profile_evidence'] or {}

        # Features describing how well this candidate matches the query.
        match_features = {}
        for key in ('primary_category', 'meal_role', 'main_protein', 'primary_cooking_style',
                    'calories', 'ingredients', 'cooking_method', 'taxonomy_source',
                    'cuisine_confidence', 'cuisine_evidence', 'is_spicy', 'calorie_source'):
            if key in row:
                match_features[key] = _json_value(row[key])
        if 'source' in row:
            match_features['dish_source'] = _json_value(row['source'])
        if 'preference_evidence' in row:
            match_features['preference_evidence'] = row['preference_evidence']

        if food_match is not None:
            match_features["food_match"] = float(food_match)
        if 'recommendation_group' in row:
            match_features['recommendation_group'] = row['recommendation_group']
        if row.get('food_family_match'):
            match_features['alternative_evidence'] = 'same_dish_family'

        if score is not None:
            match_features["semantic_similarity"] = float(score)

        if dish_similarity is not None:
            match_features["dish_similarity"] = float(
                dish_similarity
            )

        if restaurant_similarity is not None:
            match_features["restaurant_similarity"] = float(
                restaurant_similarity
            )

        dish_cuisine = _json_value(
            row.get("supported_cuisine_dish")
        )

        if dish_cuisine is not None:
            match_features["dish_supported_cuisine"] = dish_cuisine

        vegetarian = _json_value(row.get("is_vegetarian"))

        if vegetarian is not None:
            match_features["is_vegetarian"] = (
                bool(vegetarian)
                if isinstance(vegetarian, bool)
                else str(vegetarian).lower() == "true"
            )

        result.append(
            Candidate(
                restaurant_id=str(row["restaurant_id"]),
                menu_item_id=(
                    str(row["menu_item_id"])
                    if _json_value(row.get("menu_item_id")) is not None
                    else None
                ),
                dish_id=(
                    str(row["dish_id"])
                    if _json_value(row.get("dish_id")) is not None
                    else None
                ),
                restaurant_name=_json_value(row.get("name")),
                dish_name=_json_value(row.get("dish_name")),
                location=location,
                distance_km=(
                    float(distance)
                    if distance is not None
                    else None
                ),
                price=(
                    int(price)
                    if price is not None
                    else None
                ),
                restaurant_features=restaurant_features,
                match_features=match_features,
            )
        )

    return result


def retrieve_candidates(state: UserPreferenceState, top_k: int = 100, *,
                        processed_dir: str | Path = 'data/processed',
                        embeddings_dir: str | Path = 'data/embeddings',
                        retriever: Retriever | None = None) -> list[Candidate]:
    """Canonical AI1 -> AI3 entry point required by the shared contract."""
    if not isinstance(state, UserPreferenceState):
        raise TypeError('state must be common.schemas.UserPreferenceState')
    if isinstance(top_k, bool) or not isinstance(top_k, int) or top_k < 1:
        raise ValueError('top_k must be a positive integer')
    engine = retriever or _cached_engine(str(processed_dir), str(embeddings_dir))
    frame = engine.retrieve_frame(_shared_to_internal(state), top_k=top_k)
    return _frame_to_candidates(frame, engine, top_k)


def retrieve_map_places(state: UserPreferenceState, exclude=(), *,
                        processed_dir='data/processed', embeddings_dir='data/embeddings',
                        retriever: Retriever | None = None) -> list[dict]:
    """All located restaurants matching food and hard filters, without ranking/truncation."""
    from .hard_filter import filter_candidates
    engine = retriever or _cached_engine(str(processed_dir), str(embeddings_dir))
    internal = _shared_to_internal(state)
    frame = filter_candidates(engine.restaurants, engine.dishes, engine.menus, internal)
    frame = frame.loc[~frame.restaurant_id.isin(exclude)].copy()
    if state.food and not frame.empty:
        matches = _add_food_match(frame[['dish_id']].drop_duplicates(), engine.dishes, internal)
        frame = frame.merge(matches, on='dish_id', validate='many_to_one')
        frame = frame.loc[frame.food_match.gt(0)].sort_values(
            ['food_match', 'price', 'menu_item_id'], ascending=[False, True, True], kind='stable')
    frame = frame.drop_duplicates('restaurant_id')
    frame = frame.merge(engine.restaurants[['food_place_id', 'name', 'latitude', 'longitude']],
                        left_on='restaurant_id', right_on='food_place_id', validate='one_to_one')
    frame = frame.merge(engine.dishes[['dish_id', 'dish_name']], on='dish_id', validate='many_to_one')
    places = []
    for row in frame.to_dict('records'):
        lat, lon = _json_value(row['latitude']), _json_value(row['longitude'])
        if lat is None or lon is None or not (-90 <= float(lat) <= 90 and -180 <= float(lon) <= 180):
            continue
        places.append({'id': str(row['restaurant_id']), 'name': _json_value(row['name']) or '',
                       'dish': _json_value(row['dish_name']) or '', 'lat': float(lat), 'lon': float(lon),
                       'distance_km': _json_value(row['distance_km']),
                       'price_vnd': int(row['price']) if _json_value(row['price']) is not None else None})
    return places
