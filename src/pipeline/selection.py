"""Restaurant assembly after AI3 scoring; source IDs and model scores stay intact."""
from collections import defaultdict

from common.schemas import RankedResult


def identity(item):
    return item.restaurant_id, item.menu_item_id or '', item.dish_id or ''


def select_restaurants(state, candidates, ranked, top_k):
    if type(top_k) is not int or top_k < 1:
        raise ValueError('top_k must be a positive integer')
    source = {identity(c): c for c in candidates}
    menus = [c.menu_item_id for c in candidates if c.menu_item_id is not None]
    if len(source) != len(candidates) or len(set(menus)) != len(menus):
        raise ValueError('Duplicate retrieved menu identity')
    named = any(food.strip() for food in state.food)
    # Older injected retrievers have no optional food evidence. Preserve their
    # general-result contract without claiming verified named-dish matches.
    legacy = not any('food_match' in c.match_features for c in candidates)
    groups = defaultdict(list)
    seen = set()
    for item in ranked:
        key = identity(item)
        if key not in source or key in seen:
            raise ValueError('Ranker returned an unknown or duplicate candidate identity')
        seen.add(key)
        candidate = source[key]
        match = candidate.match_features.get('food_match', 0.)
        group = 'general' if not named or legacy else 'primary' if match > 0 else 'supplementary'
        if group == 'supplementary' and candidate.match_features.get('alternative_evidence') != 'same_dish_family':
            continue  # no semantic/restaurant-only guess can enter as an alternative
        evidence = {**item.reason_features, 'food_match': match, 'recommendation_group': group,
                    'candidate_rank': item.rank, 'catalog_only': True,
                    'price_is_verified': candidate.restaurant_features.get('price_is_verified', False),
                    'catalog_location': candidate.location.model_dump(mode='json') if candidate.location else None,
                    'match_evidence': candidate.match_features}
        groups[item.restaurant_id].append(item.model_copy(deep=True, update={'reason_features': evidence}))

    assembled = []
    for items in groups.values():
        items.sort(key=lambda item: (-item.score, *identity(item)))
        direct = [item for item in items if item.reason_features['recommendation_group'] == 'primary']
        representative = (direct or items)[0]
        group = 'primary' if direct else representative.reason_features['recommendation_group']
        evidence = {**representative.reason_features, 'recommendation_group': group,
                    'eligible_menu_items': [item.model_dump(mode='json') for item in items]}
        assembled.append(representative.model_copy(deep=True, update={'reason_features': evidence}))
    assembled.sort(key=lambda item: (item.reason_features['recommendation_group'] == 'supplementary', -item.score, *identity(item)))
    return [item.model_copy(update={'rank': rank}) for rank, item in enumerate(assembled[:top_k], 1)]
