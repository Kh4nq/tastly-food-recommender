"""Small integration repairs after semantic extraction, before safety acceptance."""
import re

from conversation._utils import normalize_text
from conversation.context import normalize_context
from conversation.rule_parser import _is_negated, vegetarian_matches


def normalize_search_delta(update, request, message):
    """Keep transportation in context and bind explicit vegetarian dish requests.

    This does not interpret intent, infer facilities or relax unknown hard keys.
    All repaired fields still pass the existing evidence and state validators.
    """
    result = update.model_copy(deep=True)
    modes = []
    for scope in ('hard_constraints', 'soft_preferences'):
        for values in (getattr(result, 'add_' + scope), result.set_values.get(scope, {})):
            if 'transport_mode' in values:
                modes.append(normalize_context({'transport_mode': values.pop('transport_mode')})['transport_mode'])
    if 'transport_mode' in result.context_updates:
        modes.append(result.context_updates['transport_mode'])
    if modes:
        if len(set(modes)) != 1:
            raise ValueError('Conflicting transport context')
        result.context_updates['transport_mode'] = modes[0]

    foods = result.set_values.get('food', [])
    text = normalize_text(message)
    # Food grounding runs immediately after this repair. Positive user dietary
    # evidence also protects a shortened model food label; venue names do not.
    vegetarian = any(re.search(r'\b(?:chay|vegetarian|vegan)\b', normalize_text(food)) for food in foods)
    if request.form.food is None:
        vegetarian = vegetarian or any(vegetarian_matches(text))
    if vegetarian:
        result.add_hard_constraints['vegetarian'] = True
        result.remove_preferences = [p for p in result.remove_preferences if p not in ('vegetarian', 'hard_constraints.vegetarian')]

    # This requested side has no verified catalog attribute. Preserve the source
    # phrase as context instead of claiming menu availability or requiring parking.
    side = re.search(r'\b(?:có|kèm|thêm|with)\s+(chén trứng)\b', text)
    if side and not _is_negated(text, side.start()):
        if re.search(r'(?:bắt buộc|phải|must|require)[^,.;!?]{0,30}' + re.escape(side[0]), text):
            raise ValueError('Mandatory accompaniment cannot be verified')
        sides = result.context_updates.setdefault('requested_accompaniments', [])
        if not isinstance(sides, list):
            raise ValueError('Invalid requested accompaniments')
        if side[1] not in sides:
            sides.append(side[1])
        # A side returned as a second food would incorrectly become an OR query.
        if foods:
            result.set_values['food'] = [f for f in foods if normalize_text(f) != side[1]]
    return result
