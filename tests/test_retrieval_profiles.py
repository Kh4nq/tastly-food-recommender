import hashlib
import json

import pandas as pd
import pytest

from common.schemas import UserPreferenceState
from retrieval.hard_filter import filter_candidates
from retrieval.profiles import PROFILE_FIELDS, UnverifiableConstraintError, load_restaurant_profiles
from retrieval.retriever import Retriever, _frame_to_candidates, state_to_query


def tables():
    places = pd.DataFrame({'food_place_id': ['yes', 'no', 'unknown'],
                           'latitude': [10.0] * 3, 'longitude': [106.0] * 3,
                           'profile_wifi': pd.array([True, False, None], dtype='boolean'),
                           'profile_quiet': pd.array([True, False, None], dtype='boolean'),
                           'profile_family_friendly': pd.array([True, False, None], dtype='boolean')})
    dishes = pd.DataFrame({'dish_id': ['d'], 'dish_name': ['Food'], 'is_vegetarian': [True],
                          'primary_category': ['noodle'], 'main_protein': ['plant_based'],
                          'primary_cooking_style': ['steamed'], 'meal_role': ['main'], 'calories': [400]})
    menus = pd.DataFrame({'menu_item_id': ['y', 'n', 'u'], 'food_place_id': places.food_place_id,
                         'dish_id': ['d'] * 3, 'price_vnd': [40000] * 3})
    return places, dishes, menus


@pytest.mark.parametrize('requested,expected', [(True, ['yes']), (False, ['no'])])
def test_nullable_hard_filter_does_not_accept_unknown(requested, expected):
    frame = filter_candidates(*tables(), {'hard_constraints': {'wifi': requested}})
    assert frame.restaurant_id.tolist() == expected


def test_all_unknown_required_amenity_is_reported():
    places, dishes, menus = tables()
    places['profile_wifi'] = pd.array([None] * 3, dtype='boolean')
    with pytest.raises(UnverifiableConstraintError, match='wifi'):
        filter_candidates(places, dishes, menus, {'hard_constraints': {'wifi': True}})


def test_soft_and_negative_evidence_select_before_top_k_and_preserve_metadata():
    engine = Retriever.__new__(Retriever)
    engine.restaurants, engine.dishes, engine.menus = tables()
    # Negative preferences should not trigger positive encoder input.
    result = engine.retrieve_frame({'negative_preferences': ['noisy']}, top_k=2)
    assert result.restaurant_id.tolist() == ['yes', 'unknown']
    candidates = _frame_to_candidates(result, engine, 2)
    assert candidates[0].match_features['calories'] == 400
    assert candidates[0].match_features['primary_category'] == 'noodle'
    assert candidates[0].match_features['preference_evidence']['matched'] == ['quiet']
    assert candidates[1].match_features['preference_evidence']['unknown'] == ['quiet']
    # No fabricated spicy evidence from the dish name or incomplete ingredients.
    result = engine.retrieve_frame({'negative_preferences': ['spicy']}, top_k=3)
    assert all(row['unknown'] == ['spicy'] for row in result.preference_evidence)
    for candidate in _frame_to_candidates(result, engine, 3):
        UserPreferenceState(session_id='s')
        assert json.loads(candidate.model_dump_json())['match_features']['calories'] == 400


def test_context_is_positive_and_never_embeds_identity_or_negative():
    query = state_to_query({'context': {'occasion': 'family', 'meal_time': 'dinner',
                                        'party_size': 4, 'transport_mode': 'car'},
                            'negative_preferences': ['spicy'], 'session_id': 'secret-session'})
    assert 'family' in query and 'dinner' in query
    assert 'spicy' not in query and 'secret-session' not in query and 'car' not in query


def profile_release(tmp_path):
    places, dishes, menus = tables()
    places = places[['food_place_id', 'latitude', 'longitude']]
    baseline = {}
    for name, table in [('restaurants', places), ('dishes', dishes), ('menu_items', menus)]:
        path = tmp_path / f'{name}.parquet'
        table.to_parquet(path, index=False)
        baseline[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    profile = pd.DataFrame({'food_place_id': places.food_place_id})
    for key in PROFILE_FIELDS:
        profile[key] = pd.array([None] * 3, dtype='boolean')
    profile['wifi'] = pd.array([True, False, None], dtype='boolean')
    evidence = {'wifi': {'source': 'OSM', 'raw': 'wlan', 'status': 'source_reported'}}
    profile['profile_evidence'] = [json.dumps(evidence), json.dumps(evidence), '{}']
    profile['capacity'] = pd.array([None] * 3, dtype='Int64')
    path = tmp_path / 'restaurant_profiles.parquet'
    profile.to_parquet(path, index=False)
    manifest = {'version': 'ai1-profile-v1', 'baseline_sha256': baseline,
                'files': {path.name: hashlib.sha256(path.read_bytes()).hexdigest()}}
    (tmp_path / 'ai1_profile_manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
    return places, profile, manifest


def test_loader_checks_baseline_hash_and_profile_integrity(tmp_path):
    places, profile, manifest = profile_release(tmp_path)
    merged = load_restaurant_profiles(tmp_path, places)
    assert merged.profile_wifi.iloc[0] == True
    assert pd.isna(merged.profile_wifi.iloc[2])
    with (tmp_path / 'dishes.parquet').open('ab') as stream:
        stream.write(b'changed')
    with pytest.raises(ValueError, match='baseline mismatch'):
        load_restaurant_profiles(tmp_path, places)


def test_loader_rejects_value_without_evidence(tmp_path):
    places, profile, manifest = profile_release(tmp_path)
    profile['profile_evidence'] = '{}'
    path = tmp_path / 'restaurant_profiles.parquet'
    profile.to_parquet(path, index=False)
    manifest['files'][path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    (tmp_path / 'ai1_profile_manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
    with pytest.raises(ValueError, match='without source evidence'):
        load_restaurant_profiles(tmp_path, places)


def test_production_loader_rejects_synthetic_evidence(tmp_path):
    places, profile, manifest = profile_release(tmp_path)
    profile['profile_evidence'] = json.dumps({'wifi': {'source': 'generated', 'raw': True, 'status': 'synthetic'}})
    path = tmp_path / 'restaurant_profiles.parquet'
    profile.to_parquet(path, index=False)
    manifest['files'][path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    (tmp_path / 'ai1_profile_manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
    with pytest.raises(ValueError, match='without source evidence'):
        load_restaurant_profiles(tmp_path, places)


def test_parking_vehicle_scope_does_not_certify_motorbike():
    places, dishes, menus = tables()
    places['profile_parking'] = pd.array([True, None, None], dtype='boolean')
    places['profile_evidence'] = [{'parking': {'vehicle_types': ['car']}}, {}, {}]
    state = {'hard_constraints': {'parking': True}, 'context': {'transport_mode': 'car'}}
    assert filter_candidates(places, dishes, menus, state).restaurant_id.tolist() == ['yes']
    state['context']['transport_mode'] = 'motorbike'
    with pytest.raises(UnverifiableConstraintError, match='parking'):
        filter_candidates(places, dishes, menus, state)


def test_explicit_demo_release_accepts_marked_synthetic_profiles(tmp_path):
    places, profile, manifest = profile_release(tmp_path)
    profile['demo_only'] = True
    profile['profile_evidence'] = json.dumps({'wifi': {'source': 'demo', 'raw': True, 'status': 'synthetic'}})
    path = tmp_path / 'restaurant_profiles.parquet'
    profile.to_parquet(path, index=False)
    manifest.update(usage='synthetic_demo')
    manifest['files'][path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    (tmp_path / 'ai1_profile_manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
    assert load_restaurant_profiles(tmp_path, places).profile_wifi.iloc[0] == True
    profile.loc[0, 'demo_only'] = False
    profile.to_parquet(path, index=False)
    manifest['files'][path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    (tmp_path / 'ai1_profile_manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
    with pytest.raises(ValueError, match='demo_only'):
        load_restaurant_profiles(tmp_path, places)
