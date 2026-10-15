"""Optional, checksum-bound restaurant sidecars; no import-time data loading."""
from __future__ import annotations

import json
from pathlib import Path

PROFILE_FIELDS = ('parking', 'wifi', 'air_conditioning', 'outdoor_seating',
                  'wheelchair_accessible', 'quiet', 'family_friendly', 'highchair', 'kids_area')
HARD_PROFILE_FIELDS = frozenset(('parking', 'wifi', 'air_conditioning', 'outdoor_seating', 'wheelchair_accessible'))


class UnsupportedConstraintError(NotImplementedError):
    """AI2 requested a hard constraint without an implemented evidence policy."""


class UnverifiableConstraintError(UnsupportedConstraintError):
    """The dataset cannot verify any remaining candidate for a required field."""


class InvalidConstraintError(ValueError):
    """A user constraint has an invalid value or lacks required location."""


def load_restaurant_profiles(processed_dir, restaurants):
    import pandas as pd
    from .embedder import _sha256

    root = Path(processed_dir)
    profile_path = root / 'restaurant_profiles.parquet'
    manifest_path = root / 'ai1_profile_manifest.json'
    if not profile_path.exists() and not manifest_path.exists():
        return restaurants
    if not profile_path.exists() or not manifest_path.exists():
        raise ValueError('Incomplete AI1 profile release')
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    if manifest.get('version') != 'ai1-profile-v1':
        raise ValueError('Unsupported AI1 profile version')
    demo = manifest.get('usage') == 'synthetic_demo'
    for name in ('restaurants.parquet', 'dishes.parquet', 'menu_items.parquet'):
        if manifest.get('baseline_sha256', {}).get(name) != _sha256(root / name):
            raise ValueError(f'AI1 profile baseline mismatch: {name}')
    if manifest.get('files', {}).get(profile_path.name) != _sha256(profile_path):
        raise ValueError('AI1 restaurant profile checksum mismatch')
    profile = pd.read_parquet(profile_path)
    if demo and ('demo_only' not in profile or not profile.demo_only.eq(True).all()):
        raise ValueError('Demo profiles must explicitly mark every row demo_only')
    accepted_statuses = {'source_reported', 'reviewed_source'} | ({'synthetic'} if demo else set())
    required = {'food_place_id', 'profile_evidence', *PROFILE_FIELDS, 'capacity'}
    if not required.issubset(profile):
        raise ValueError('Incomplete restaurant profile columns')
    if profile.food_place_id.isna().any() or profile.food_place_id.duplicated().any():
        raise ValueError('Invalid restaurant profile IDs')
    if set(profile.food_place_id) != set(restaurants.food_place_id):
        raise ValueError('Restaurant profile ID coverage mismatch')
    for key in PROFILE_FIELDS:
        if str(profile[key].dtype) != 'boolean':
            raise ValueError(f'{key} must use nullable boolean dtype')
    evidence = profile.profile_evidence.map(json.loads)
    for row, sources in zip(profile.to_dict('records'), evidence):
        if not isinstance(sources, dict):
            raise ValueError('Profile evidence must be a dictionary')
        for key in PROFILE_FIELDS:
            if pd.notna(row[key]) and not (
                isinstance(sources.get(key), dict) and sources[key].get('source')
                and sources[key].get('status') in accepted_statuses
                and sources[key].get('raw') is not None
            ):
                raise ValueError(f'{key} has a value without source evidence')
            if key in HARD_PROFILE_FIELDS and pd.notna(row[key]) and sources[key].get('soft_only'):
                raise ValueError(f'{key} cannot use soft-only evidence for hard filtering')
        if pd.notna(row['capacity']) and not (
            row['capacity'] > 0 and isinstance(sources.get('capacity'), dict)
            and sources['capacity'].get('source') and sources['capacity'].get('raw') is not None
            and sources['capacity'].get('status') in accepted_statuses
        ):
            raise ValueError('capacity has a value without valid source evidence')
    profile['profile_evidence'] = evidence
    # Preserve raw baseline fields, especially outdoor_seating, for provenance.
    profile = profile.rename(columns={key: f'profile_{key}' for key in (*PROFILE_FIELDS, 'capacity')})
    return restaurants.merge(profile, on='food_place_id', how='left', validate='one_to_one')
