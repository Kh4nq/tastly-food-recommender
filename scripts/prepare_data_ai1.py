r"""AI1 Part 1: prepare v2 CSVs without changing IDs.

From the mlai-food project root (Anaconda Prompt):
    python scripts\prepare_data_ai1.py --input-dir data\raw --enrichment-dir data\processed --output-dir data\processed

If the folders are directly under the project root, use --input-dir public
and --enrichment-dir processed instead. Requires pandas and pyarrow.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import pandas as pd

PLACE_ENRICH = [
    'normalized_cuisine', 'cuisine_constraint_type',
    'cuisine_normalization_evidence', 'supported_cuisine',
    'has_hard_cuisine_constraint', 'supported_cuisine_evidence',
]
DISH_ENRICH = [
    'cuisine_origin', 'cuisine_confidence', 'cuisine_evidence',
    'supported_cuisine', 'is_hard_cuisine_eligible',
]


def load(path: Path) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(f'Missing required file: {path.resolve()}')
    return pd.read_csv(path, low_memory=False)


def assert_unique(df: pd.DataFrame, key: str, label: str) -> None:
    if key not in df:
        raise ValueError(f'{label}: missing column {key}')
    if df[key].isna().any() or df[key].duplicated().any():
        raise ValueError(f'{label}: {key} has null/duplicate values')


def add_enrichment(df: pd.DataFrame, path: Path, key: str, cols: list[str]) -> pd.DataFrame:
    if not path.is_file():
        print(f'[WARN] Enrichment not found: {path.resolve()}')
        return df
    extra = load(path)
    assert_unique(extra, key, path.name)
    keep = [key] + [col for col in cols if col in extra and col not in df]
    before = len(df)
    matched = int(df[key].isin(extra[key]).sum())
    result = df.merge(extra[keep], on=key, how='left', validate='one_to_one')
    if len(result) != before:
        raise AssertionError(f'{path.name}: join changed row count')
    print(f'[OK] Enrichment {path.name}: matched {matched:,}/{before:,}')
    return result


def normalize_text(df: pd.DataFrame, column: str) -> None:
    if column not in df:
        df[column] = pd.NA
    df[column] = (
        df[column].astype('string').str.strip().str.lower()
        .replace({'': pd.NA, 'nan': pd.NA, 'none': pd.NA})
        .fillna('unknown')
    )


def main(input_dir: Path, enrichment_dir: Path, output_dir: Path) -> None:
    places = load(input_dir / 'food-places.csv')
    dishes = load(input_dir / 'dishes.csv')
    menus = load(input_dir / 'menu-items.csv')
    for df, key, label in [
        (places, 'food_place_id', 'places'),
        (dishes, 'dish_id', 'dishes'),
        (menus, 'menu_item_id', 'menus'),
    ]:
        assert_unique(df, key, label)

    places = add_enrichment(
        places, enrichment_dir / 'food-place-supported-cuisine.csv',
        'food_place_id', PLACE_ENRICH,
    )
    dishes = add_enrichment(
        dishes, enrichment_dir / 'dish-catalog-supported-cuisine.csv',
        'dish_id', DISH_ENRICH,
    )
    for df, col in [
        (places, 'normalized_cuisine'), (places, 'supported_cuisine'),
        (dishes, 'cuisine_origin'), (dishes, 'supported_cuisine'),
    ]:
        normalize_text(df, col)
    for col in ['cuisine_confidence', 'cuisine_evidence']:
        if col not in dishes:
            dishes[col] = pd.NA
    if 'supported_cuisine_evidence' not in places:
        places['supported_cuisine_evidence'] = pd.NA

    missing_place = ~menus['food_place_id'].isin(places['food_place_id'])
    missing_dish = ~menus['dish_id'].isin(dishes['dish_id'])
    if missing_place.any() or missing_dish.any():
        raise ValueError(
            f'Orphan menus: place={int(missing_place.sum())}, '
            f'dish={int(missing_dish.sum())}'
        )

    places['latitude'] = pd.to_numeric(places['latitude'], errors='coerce')
    places['longitude'] = pd.to_numeric(places['longitude'], errors='coerce')
    bad_geo = (
        (places['latitude'].notna() & ~places['latitude'].between(-90, 90))
        | (places['longitude'].notna() & ~places['longitude'].between(-180, 180))
    )
    if bad_geo.any():
        raise ValueError(f'{int(bad_geo.sum())} invalid lat/lon values')

    menus['estimated_price_vnd'] = pd.to_numeric(
        menus['estimated_price_vnd'], errors='coerce'
    )
    if menus['estimated_price_vnd'].isna().any() or (menus['estimated_price_vnd'] <= 0).any():
        raise ValueError('Menu contains null/non-positive prices')
    if (menus['estimated_price_vnd'] % 1 != 0).any():
        raise ValueError('Menu contains fractional VND prices')
    menus['price_vnd'] = menus['estimated_price_vnd'].astype('int64')
    menus['price_is_verified'] = False  # Current v2 prices are synthetic.

    output_dir.mkdir(parents=True, exist_ok=True)
    for name, df in [
        ('restaurants', places), ('dishes', dishes), ('menu_items', menus)
    ]:
        df.to_parquet(output_dir / f'{name}.parquet', index=False)
        print(f'[OK] {name}: {len(df):,} rows')

    synthetic = menus['is_synthetic'].astype('string').str.lower().eq('true').sum()
    report = {
        'dataset_version': 'v2-original-ids',
        'restaurants': len(places),
        'dishes': len(dishes),
        'menu_items': len(menus),
        'place_cuisine_known': int(places['normalized_cuisine'].ne('unknown').sum()),
        'place_supported_cuisine_known': int((~places['supported_cuisine'].isin(['unknown', 'other'])).sum()),
        'dish_cuisine_known': int(dishes['cuisine_origin'].ne('unknown').sum()),
        'dish_supported_cuisine_known': int((~dishes['supported_cuisine'].isin(['unknown', 'other'])).sum()),
        'missing_coordinates': int((places['latitude'].isna() | places['longitude'].isna()).sum()),
        'synthetic_menu_rows': int(synthetic),
        'note': 'Menu prices are synthetic estimates, not verified restaurant menus.',
    }
    report_path = output_dir / 'quality_report.json'
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--input-dir', type=Path, default=Path('data/raw'))
    parser.add_argument('--enrichment-dir', type=Path, default=Path('data/processed'))
    parser.add_argument('--output-dir', type=Path, default=Path('data/processed'))
    args = parser.parse_args()
    main(args.input_dir, args.enrichment_dir, args.output_dir)
