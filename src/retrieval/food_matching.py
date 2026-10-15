"""Dish-name evidence only. Restaurant names never establish menu relevance."""
import re
import unicodedata


def normalized(value):
    text = unicodedata.normalize('NFKD', str(value or '').casefold().replace('đ', 'd'))
    return ' '.join(re.findall(r'\w+', ''.join(c for c in text if not unicodedata.combining(c))))


FAMILIES = ('hu tieu', 'com tam', 'pho', 'ramen', 'bun', 'pizza', 'sushi', 'mi')
# These are different dishes/products even when a marketing name mentions pho.
OTHER_HEADS = {'banh', 'cake', 'salad', 'pizza', 'tra', 'tea', 'sinh', 'smoothie', 'nuoc', 'juice', 'kem', 'ice'}
NON_PHO = ('pho mai', 'pho mat')  # phô mai / pho mát are cheese, not pho


def family(value):
    text = normalized(value)
    if any(text == phrase or text.startswith(phrase + ' ') for phrase in NON_PHO):
        return None
    for name in FAMILIES:
        if text == name or text.startswith(name + ' '):
            return name
    return None


def food_evidence(name, foods):
    """Exact/prefix/phrase/reordered matches; same-family alternatives stay zero."""
    text = normalized(name)
    tokens = text.split()
    best, related = 0., False
    for food in foods:
        query = normalized(food)
        if not query:
            continue
        qtokens = query.split()
        base = family(query)
        actual = family(text)
        if base == 'pho' and any(text == phrase or text.startswith(phrase + ' ') for phrase in NON_PHO):
            continue
        # Never turn a dessert, beverage or a different dish family into pho.
        if base and actual != base:
            if tokens and tokens[0] in OTHER_HEADS:
                continue
            if not set(qtokens) <= set(tokens):
                continue
        if base and actual == base:
            related = True
        if text == query:
            best = max(best, 1.)
        elif text.startswith(query + ' '):
            best = max(best, .95)
        elif re.search(r'(?<!\w)' + re.escape(query) + r'(?!\w)', text):
            best = max(best, .9)
        elif len(qtokens) > 1 and set(qtokens) <= set(tokens):
            best = max(best, .85)
    return best, related


def diverse_rows(frame, limit):
    """Keep multiple menu items, in rounds, so prolific venues cannot starve others."""
    if frame.empty or limit <= 0:
        return frame.head(0)
    ordered = frame.assign(_round=frame.groupby('restaurant_id', sort=False).cumcount())
    return ordered.sort_values('_round', kind='stable').head(limit).drop(columns='_round')


def bounded_pools(frame, limit, named):
    if not named:
        return diverse_rows(frame, limit)
    primary = frame.loc[frame.food_match.gt(0)]
    supplementary = frame.loc[frame.food_match.eq(0)]
    # Reserve at least one slot per available matching restaurant, then leave
    # room for alternatives. Unused capacity returns to the other pool.
    reserve = min(len(primary), max(primary.restaurant_id.nunique(), limit // 2), limit)
    direct = diverse_rows(primary, reserve)
    matching_ids = set(primary.restaurant_id)
    chosen_ids = set(direct.restaurant_id)
    # A venue with a known direct match outside the bounded slice cannot be
    # reintroduced as an apparent alternative by one of its other dishes.
    supplementary = supplementary.loc[~supplementary.restaurant_id.isin(matching_ids - chosen_ids)].copy()
    supplementary = supplementary.assign(_has_direct=supplementary.restaurant_id.isin(matching_ids)).sort_values('_has_direct', kind='stable').drop(columns='_has_direct')
    extra = diverse_rows(supplementary, limit - len(direct))
    direct = diverse_rows(primary, limit - len(extra))
    import pandas as pd
    return pd.concat([direct, extra], ignore_index=True)
