"""Evidence matching of normalized AI2 preference labels, not chat parsing.

Counts are selection tie-breaks, not CatBoost features or probabilities.
Unknown metadata never supplies positive or negative evidence.
"""
from __future__ import annotations

import unicodedata

from .profiles import PROFILE_FIELDS


def normalized(value):
    return ' '.join(unicodedata.normalize('NFC', str(value)).casefold().strip().split())


LABELS = {
    'quiet': 'quiet', 'yên tĩnh': 'quiet', 'yen tinh': 'quiet',
    'suitable for family': 'family_friendly', 'family friendly': 'family_friendly',
    'family_friendly': 'family_friendly', 'phù hợp gia đình': 'family_friendly',
    'wifi': 'wifi', 'wi-fi': 'wifi', 'parking': 'parking',
    'air conditioning': 'air_conditioning', 'air_conditioning': 'air_conditioning',
    'outdoor seating': 'outdoor_seating', 'outdoor_seating': 'outdoor_seating',
    'wheelchair accessible': 'wheelchair_accessible',
}
NEGATIVE_LABELS = {
    'noisy': ('quiet', True), 'noise': ('quiet', True), 'ồn': ('quiet', True),
    'không ồn': ('quiet', True), 'not noisy': ('quiet', True),
    'spicy': ('spicy', False), 'cay': ('spicy', False), 'không cay': ('spicy', False),
    'not spicy': ('spicy', False),
}


def preferences(state):
    requested, unresolved, conflicts = {}, [], set()
    soft = state.get('soft_preferences') or {}
    if isinstance(soft, dict):
        for key, value in soft.items():
            if key in PROFILE_FIELDS and type(value) is bool:
                requested[key] = value
    for label in state.get('semantic_preferences') or []:
        key = LABELS.get(normalized(label))
        if key:
            requested.setdefault(key, True)
    context = state.get('context') or {}
    companions = context.get('companions') or []
    if context.get('occasion') == 'family' or any(c in ('family', 'children') for c in companions):
        requested.setdefault('family_friendly', True)
    for label in state.get('negative_preferences') or []:
        target = NEGATIVE_LABELS.get(normalized(label))
        if target:
            key, value = target
            if key in conflicts:
                continue
            if key in requested and requested[key] != value:
                requested.pop(key)
                conflicts.add(key)
                unresolved.append(f'conflicting preference: {key}')
            else:
                requested[key] = value
        else:
            unresolved.append(str(label))
    return requested, unresolved


def add_preference_evidence(frame, restaurants, dishes, state):
    import pandas as pd
    import numpy as np

    wanted, unresolved = preferences(state)
    out = frame.copy()
    places = restaurants.set_index('food_place_id')
    dish_table = dishes.set_index('dish_id')
    signals = [dict(matched=[], mismatched=[], unknown=[], unresolved_negative=list(unresolved)) for _ in range(len(out))]
    for key, value in wanted.items():
        if key == 'spicy':
            # Only an explicit dish attribute can verify this, never absence of chili.
            values = out.dish_id.map(dish_table['is_spicy']) if 'is_spicy' in dish_table else pd.Series(None, index=out.index)
        else:
            col = f'profile_{key}'
            values = out.restaurant_id.map(places[col]) if col in places else pd.Series(None, index=out.index)
        for signal, observed in zip(signals, values):
            if observed is None or pd.isna(observed):
                signal['unknown'].append(key)
            elif isinstance(observed, (bool, np.bool_)):
                signal['matched' if bool(observed) == value else 'mismatched'].append(key)
            else:
                signal['unknown'].append(key)
    party_size = (state.get('context') or {}).get('party_size')
    if isinstance(party_size, int) and not isinstance(party_size, bool) and party_size > 1:
        capacities = (out.restaurant_id.map(places['profile_capacity'])
                      if 'profile_capacity' in places else pd.Series(None, index=out.index))
        for signal, capacity in zip(signals, capacities):
            if pd.isna(capacity):
                signal['unknown'].append('party_size')
            else:
                # Total venue capacity is a soft hint; it does not certify free tables.
                signal['matched' if capacity >= party_size else 'mismatched'].append('party_size')
    out['preference_evidence'] = signals
    out['preference_matches'] = [len(s['matched']) for s in signals]
    out['preference_mismatches'] = [len(s['mismatched']) for s in signals]
    return out
