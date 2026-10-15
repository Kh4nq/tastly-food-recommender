"""Versioned, offline enrichment; preserve IDs and existing embedding input text."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shutil
import unicodedata
import zipfile

from retrieval.embedder import _sha256, dish_text, restaurant_text

VERSION = 'serving-space-v1'


def folded(value):
    value = unicodedata.normalize('NFD', str(value or '').lower()).replace('đ', 'd')
    return ' '.join(''.join(c for c in value if not unicodedata.combining(c)).split())


def classify_dish(row):
    """Conservative inference with an explicit unknown value and rule evidence."""
    name = folded(row.get('dish_name'))
    category = row.get('primary_category')
    if category == 'beverage' or row.get('meal_role') == 'drink':
        return 'beverage', 'not_applicable', 'category:beverage/meal_role:drink'
    # Dry variants must precede soup/noodle cues (pho cuon, hu tieu kho).
    if re.search(r'\b(tron|xao|chien|ran|nuong|cuon)\b', name) or re.search(r'\bkhô\b', str(row.get('dish_name', '')).lower()):
        return 'food', 'dry', 'name:explicit_dry_variant'
    if category == 'hotpot' or re.search(r'\blau\b', name):
        return 'food', 'hotpot', 'category/name:hotpot'
    if category == 'soup' or re.search(r'\b(canh|sup|soup|chao)\b', name):
        return 'food', 'soup', 'category/name:soup'
    if category == 'noodle':
        if re.search(r'\b(pho|bun bo hue|bun rieu|bun moc|bun thang)\b', name):
            return 'food', 'broth', 'name:conventional_broth_dish'
        description = folded(row.get('description'))
        if re.search(r'\b(nuoc dung|nuoc leo|broth|noodle soup)\b', name + ' ' + description):
            return 'food', 'broth', 'text:explicit_broth'
        return 'food', 'unknown', 'ambiguous_noodle_variant'
    if category in {'rice', 'salad', 'bakery'}:
        return 'food', 'dry', 'category:rice/salad/bakery'
    # Dessert/snack and cooking methods alone do not prove a dry serving style.
    return 'food', 'unknown', 'insufficient_serving_evidence'


def describe_space(profile):
    """Describe existing demo profiles, without inventing luxury or decor facts."""
    tags, phrases = [], []
    for key, tag, phrase in (
        ('quiet', 'quiet', 'Không gian yên tĩnh'),
        ('outdoor_seating', 'outdoor', 'Có khu vực ngồi ngoài trời'),
        ('air_conditioning', 'air_conditioning', 'Có điều hòa'),
        ('family_friendly', 'family_friendly', 'Phù hợp đi cùng gia đình'),
        ('wifi', 'wifi', 'Có Wi-Fi'),
    ):
        if profile.get(key) is True:
            tags.append(tag)
            phrases.append(phrase)
    if profile.get('capacity') is not None:
        phrases.append(f"Sức chứa khoảng {int(profile['capacity'])} người")
    return '. '.join(phrases) + ('.' if phrases else ''), json.dumps(tags, ensure_ascii=False)


def update(root: Path):
    import pandas as pd

    processed, embeddings = root / 'data/processed', root / 'data/embeddings'
    manifest_path = processed / 'ai1_profile_manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    if manifest.get('usage') != 'synthetic_demo':
        raise ValueError('Space generation requires an explicitly marked synthetic_demo release')
    # Load and validate the complete old release before changing any file.
    from retrieval.retriever import Retriever
    Retriever(processed, embeddings)
    restaurants = pd.read_parquet(processed / 'restaurants.parquet')
    dishes = pd.read_parquet(processed / 'dishes.parquet')
    profiles = pd.read_parquet(processed / 'restaurant_profiles.parquet')
    before_dish_text = [dish_text(r) for r in dishes.to_dict('records')]
    before_place_text = [restaurant_text(r) for r in restaurants.to_dict('records')]
    classifications = [classify_dish(r) for r in dishes.to_dict('records')]
    dishes['item_kind'], dishes['serving_style'], dishes['serving_style_evidence'] = zip(*classifications)
    dishes['serving_taxonomy_version'] = VERSION
    descriptions = {p['food_place_id']: describe_space(p) for p in profiles.to_dict('records')}
    restaurants['space_description'] = restaurants.food_place_id.map(lambda k: descriptions[k][0])
    restaurants['space_tags'] = restaurants.food_place_id.map(lambda k: descriptions[k][1])
    restaurants['space_source'] = 'synthetic_demo:restaurant_profiles'
    # These display/filter columns are deliberately outside embedding templates.
    assert before_dish_text == [dish_text(r) for r in dishes.to_dict('records')]
    assert before_place_text == [restaurant_text(r) for r in restaurants.to_dict('records')]

    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    backup = root / 'data/backups' / f'before-{VERSION}-{stamp}'
    backup.mkdir(parents=True)
    for source in (processed, embeddings):
        shutil.copytree(source, backup / source.name)
    dishes.to_parquet(processed / 'dishes.parquet', index=False)
    restaurants.to_parquet(processed / 'restaurants.parquet', index=False)
    hashes = {name: _sha256(processed / name) for name in manifest['baseline_sha256']}
    manifest['baseline_sha256'] = hashes
    manifest['taxonomy_version'] = VERSION
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    meta_path = embeddings / 'metadata.json'
    meta = json.loads(meta_path.read_text(encoding='utf-8'))
    meta['source_files'] = hashes
    meta['taxonomy_version'] = VERSION
    meta['embedding_reuse_reason'] = 'Exact per-ID restaurant_text/dish_text unchanged; added filter/display columns only.'
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding='utf-8')
    card_path = processed / 'ai1_dataset_card.json'
    card = json.loads(card_path.read_text(encoding='utf-8'))
    card['taxonomy_version'] = VERSION
    card['serving_style_counts'] = dict(Counter(dishes.serving_style))
    card['item_kind_counts'] = dict(Counter(dishes.item_kind))
    limitation = 'Serving styles are conservative rule inferences; unknown is excluded by explicit filters. Space descriptions are synthetic demo metadata, not observed venue facts.'
    if limitation not in card['limitations']:
        card['limitations'].append(limitation)
    card_path.write_text(json.dumps(card, ensure_ascii=False, indent=2), encoding='utf-8')
    Retriever(processed, embeddings)
    # Rebuild the private data package, including a complete payload checksum manifest.
    files = [p for folder in (processed, embeddings) for p in sorted(folder.iterdir()) if p.is_file() and p.name != '.gitkeep']
    payload = {'usage': meta['usage'], 'taxonomy_version': VERSION,
               'sha256': {p.relative_to(root / 'data').as_posix(): _sha256(p) for p in files}}
    with zipfile.ZipFile(root / 'data/ai1-demo-data.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, path.relative_to(root / 'data').as_posix())
        archive.writestr('dataset_manifest.json', json.dumps(payload, ensure_ascii=False, indent=2))
    print(json.dumps({'version': VERSION, 'item_kind': card['item_kind_counts'],
                      'serving_style': card['serving_style_counts'], 'backup': str(backup)}, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    update(parser.parse_args().root)
