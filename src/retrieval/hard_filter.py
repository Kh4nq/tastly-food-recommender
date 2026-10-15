"""AI1 hard filtering over processed restaurant/dish/menu tables."""
from __future__ import annotations
from pathlib import Path
import math
from .profiles import InvalidConstraintError, HARD_PROFILE_FIELDS, UnsupportedConstraintError, UnverifiableConstraintError

SUPPORTED_DIET = {'vegetarian', 'veggie', 'chay', 'ăn chay', 'an chay'}
SUPPORTED_HARD_KEYS = {'budget_min', 'budget_max', 'max_distance_km', 'vegetarian', 'item_kind', 'serving_style'} | HARD_PROFILE_FIELDS


def load_tables(processed_dir: str | Path):
    import pandas as pd
    root = Path(processed_dir)
    return tuple(pd.read_parquet(root / f'{name}.parquet') for name in
                 ('restaurants', 'dishes', 'menu_items'))


def _positive_number(value, name, allow_zero=False):
    try:
        n = float(value)
    except (ValueError, TypeError) as exc:
        raise InvalidConstraintError(f'{name} must be numeric') from exc
    if not math.isfinite(n) or n < 0 or (n == 0 and not allow_zero):
        raise InvalidConstraintError(f'{name} must be finite and {"nonnegative" if allow_zero else "positive"}')
    return n


def _constraints(state: dict) -> dict:
    raw = state.get('hard_constraints') or {}
    # Legacy AI1 state remains accepted internally for demos/tests.
    if isinstance(raw, str):
        raw = [raw]
    if isinstance(raw, (list, tuple, set)):
        converted = {}
        for token in raw:
            key = str(token).strip().lower()
            if key in SUPPORTED_DIET:
                converted['vegetarian'] = True
            elif key:
                raise UnsupportedConstraintError(f'Unsupported hard constraint: {key}')
        raw = converted
    if not isinstance(raw, dict):
        raise InvalidConstraintError('hard_constraints must be a dict (or legacy list/string)')
    result = dict(raw)
    # Legacy top-level numeric fields are normalized into the shared container.
    for key in ('budget_min', 'budget_max', 'max_distance_km'):
        if key not in result and state.get(key) is not None:
            result[key] = state[key]
    if state.get('budget_max_vnd') is not None and 'budget_max' not in result:
        result['budget_max'] = state['budget_max_vnd']
    if state.get('vegetarian') is True:
        result['vegetarian'] = True
    unknown = set(result) - SUPPORTED_HARD_KEYS
    if unknown:
        raise UnsupportedConstraintError(
            'Unsupported hard constraint(s): ' + ', '.join(sorted(unknown)) +
            '. This requirement cannot be verified. Please remove or relax it.'
        )
    return result


def filter_candidates(restaurants, dishes, menu_items, state: dict):
    """Return evidence-valid menu candidates after supported hard constraints."""
    import pandas as pd
    from .geo_search import restaurants_with_distance
    if not isinstance(state, dict):
        raise TypeError('state must be a dict')
    for df, required, name in [
        (restaurants, {'food_place_id', 'latitude', 'longitude'}, 'restaurants'),
        (dishes, {'dish_id', 'is_vegetarian'}, 'dishes'),
        (menu_items, {'menu_item_id', 'food_place_id', 'dish_id'}, 'menu_items'),
    ]:
        missing = required - set(df.columns)
        if missing:
            raise ValueError(f'{name} missing columns: {sorted(missing)}')

    constraints = _constraints(state)
    budget = constraints.get('budget_max')
    if budget is not None:
        budget = _positive_number(budget, 'budget_max', allow_zero=True)
    budget_min = constraints.get('budget_min')
    if budget_min is not None:
        budget_min = _positive_number(budget_min, 'budget_min', allow_zero=True)
    if budget_min is not None and budget is not None and budget_min > budget:
        raise InvalidConstraintError('budget_min must be less than or equal to budget_max')
    max_distance = constraints.get('max_distance_km')
    if max_distance is not None:
        max_distance = _positive_number(max_distance, 'max_distance_km')
    vegetarian = constraints.get('vegetarian', False)
    if type(vegetarian) is not bool:
        raise InvalidConstraintError('vegetarian must be boolean')

    location = state.get('location')
    if max_distance is not None and location is None:
        raise InvalidConstraintError('max_distance_km requires location')

    places = restaurants
    if 'is_recommendable' in places:
        recommendable = places['is_recommendable'].astype('string').str.lower().eq('true')
        places = places.loc[recommendable].copy()
    if location is not None:
        places = restaurants_with_distance(places, location)

        # When the user supplies a location, candidates without usable
        # coordinates cannot provide valid geo evidence.
        places = places.loc[
            places['distance_km'].notna()
        ].copy()

        if max_distance is not None:
            places = places.loc[
                places['distance_km'] <= max_distance
            ]
    else:
        places = places.copy()
        places['distance_km'] = float('nan')

    # Source-backed sidecars only; baseline strings are not silently treated as verified.
    for key in sorted(HARD_PROFILE_FIELDS & constraints.keys()):
        requested = constraints[key]
        if type(requested) is not bool:
            raise InvalidConstraintError(f'{key} must be boolean')
        column = f'profile_{key}'
        if column not in places:
            raise UnverifiableConstraintError(f'Unsupported without evidence: {key}. Please relax this condition.')
        known = places[column].notna()
        if key == 'parking' and requested:
            transport = (state.get('context') or {}).get('transport_mode')
            if transport in {'car', 'motorbike', 'bicycle'}:
                def supports_vehicle(evidence):
                    scope = evidence.get('parking', {}).get('vehicle_types', []) if isinstance(evidence, dict) else []
                    return transport in scope
                scoped = (places.profile_evidence.map(supports_vehicle)
                          if 'profile_evidence' in places else pd.Series(False, index=places.index))
                known = known & scoped
        if not places.empty and not known.any():
            raise UnverifiableConstraintError(f'Cannot verify required {key} for restaurants in this area. Please relax it.')
        places = places.loc[known & places[column].eq(requested)].copy()

    menus = menu_items
    price_col = 'price_vnd' if 'price_vnd' in menus else 'estimated_price_vnd'
    if price_col not in menus:
        raise ValueError('menu_items missing price_vnd/estimated_price_vnd')
    price = pd.to_numeric(menus[price_col], errors='coerce')
    # Source rows with unusable prices cannot satisfy a price-bearing Candidate.
    menus = menus.loc[price.notna() & (price >= 0)]
    if budget_min is not None:
        menus = menus.loc[price.loc[menus.index] >= budget_min]
    if budget is not None:
        menus = menus.loc[price.loc[menus.index] <= budget]
    menus = menus.loc[menus['food_place_id'].isin(places['food_place_id'])]
    eligible = dishes
    for key, allowed in (('item_kind', {'food', 'beverage'}), ('serving_style', {'dry', 'broth', 'soup', 'hotpot', 'unknown'})):
        if key not in constraints:
            continue
        value = constraints[key]
        requested = [value] if key == 'item_kind' else value
        if not isinstance(requested, list) or not requested or any(not isinstance(v, str) or v not in allowed for v in requested):
            raise InvalidConstraintError(f'Invalid {key}')
        if key not in eligible:
            raise UnverifiableConstraintError(f'Dataset has no {key}; update taxonomy artifacts first.')
        eligible = eligible.loc[eligible[key].isin(requested)]
        if key == 'serving_style':
            if 'item_kind' not in eligible:
                raise UnverifiableConstraintError('serving_style requires item_kind evidence')
            eligible = eligible.loc[eligible.item_kind.eq('food')]
    menus = menus.loc[menus.dish_id.isin(eligible.dish_id)]
    if vegetarian:
        known_veg = dishes['is_vegetarian'].astype('string').str.lower().eq('true')
        eligible_ids = dishes.loc[known_veg, 'dish_id']
        menus = menus.loc[menus['dish_id'].isin(eligible_ids)]

    candidates = menus.merge(places[['food_place_id', 'distance_km']],
                             on='food_place_id', how='inner', validate='many_to_one')
    candidates = candidates.rename(columns={'food_place_id': 'restaurant_id'})
    candidates['price'] = pd.to_numeric(candidates[price_col], errors='coerce')
    candidates['price_is_verified'] = False
    cols = ['restaurant_id', 'menu_item_id', 'dish_id', 'distance_km',
            'price', 'price_is_verified']
    return candidates[cols].reset_index(drop=True)
