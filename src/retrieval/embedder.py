"""AI1 Part 3: offline restaurant/dish embeddings with stable row-to-ID mapping.

Only downloads the model on the FIRST run; later runs use the local HF cache.
Menu items reuse dish/restaurant vectors through the original v2 foreign keys.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path

DEFAULT_MODEL = 'sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2'


def clean(value) -> str:
    import pandas as pd
    if value is None or pd.isna(value):
        return ''
    text = str(value).strip()
    return '' if text.lower() in {'nan', 'none', 'null', 'unknown'} else text


def restaurant_text(row) -> str:
    fields = [('Tên quán', 'name'), ('Loại hình', 'place_type'),
              ('Ẩm thực', 'supported_cuisine'), ('Ẩm thực gốc', 'cuisine'),
              ('Địa chỉ', 'full_address')]
    return '. '.join(f'{label}: {clean(row.get(col))}' for label, col in fields
                     if clean(row.get(col))) or 'Quán ăn'


def dish_text(row) -> str:
    fields = [('Món', 'dish_name'), ('Mô tả', 'description'),
              ('Danh mục', 'primary_category'), ('Loại món', 'dish_type'),
              ('Ẩm thực', 'supported_cuisine'), ('Nguyên liệu', 'ingredients'),
              ('Cách nấu', 'cooking_method'), ('Thẻ', 'dish_tags')]
    return '. '.join(f'{label}: {clean(row.get(col))}' for label, col in fields
                     if clean(row.get(col))) or 'Món ăn'


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def _build_one(df, id_col, text_fn, name, out, model, batch_size):
    import numpy as np
    import pandas as pd
    if df[id_col].isna().any() or df[id_col].duplicated().any():
        raise ValueError(f'{name}: null or duplicate {id_col}')
    # Sort for deterministic index order; index i in .npy equals row i in IDs CSV.
    df = df.sort_values(id_col, kind='stable').reset_index(drop=True)
    texts = [text_fn(row) for row in df.to_dict('records')]
    vectors = model.encode(texts, batch_size=batch_size, show_progress_bar=True,
                           convert_to_numpy=True, normalize_embeddings=True)
    vectors = np.asarray(vectors, dtype=np.float32)
    if vectors.ndim != 2 or vectors.shape[0] != len(df):
        raise ValueError(f'{name}: unexpected embedding shape {vectors.shape}')
    if not np.isfinite(vectors).all():
        raise ValueError(f'{name}: embeddings contain NaN/inf')
    # Exact row alignment; don't reorder either file after creation.
    vector_path = out / f'{name}_vectors.npy'
    ids_path = out / f'{name}_ids.csv'
    np.save(vector_path, vectors)
    pd.DataFrame({'vector_row': np.arange(len(df)), id_col: df[id_col]}).to_csv(ids_path, index=False)
    return {'rows': len(df), 'dimension': int(vectors.shape[1]),
            'vectors': vector_path.name, 'ids': ids_path.name,
            'vectors_sha256': _sha256(vector_path), 'ids_sha256': _sha256(ids_path)}


def build_embeddings(processed_dir, output_dir, model_name=DEFAULT_MODEL,
                     batch_size=64, model=None):
    import pandas as pd
    """Optional injected model allows unit tests without downloading weights."""
    processed_dir, output_dir = Path(processed_dir), Path(output_dir)
    if batch_size < 1:
        raise ValueError('batch_size must be >= 1')
    restaurants = pd.read_parquet(processed_dir / 'restaurants.parquet')
    dishes = pd.read_parquet(processed_dir / 'dishes.parquet')
    menus = pd.read_parquet(processed_dir / 'menu_items.parquet')
    for df, cols, label in [(restaurants, {'food_place_id'}, 'restaurants'),
                            (dishes, {'dish_id'}, 'dishes'),
                            (menus, {'menu_item_id', 'food_place_id', 'dish_id'}, 'menus')]:
        if not cols.issubset(df):
            raise ValueError(f'{label}: missing {sorted(cols - set(df))}')
    if menus['menu_item_id'].duplicated().any() or menus['menu_item_id'].isna().any():
        raise ValueError('menus: duplicate/null menu_item_id')
    if not menus['food_place_id'].isin(restaurants['food_place_id']).all():
        raise ValueError('menu_items contain unknown food_place_id')
    if not menus['dish_id'].isin(dishes['dish_id']).all():
        raise ValueError('menu_items contain unknown dish_id')
    if model is None:
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer(model_name)
    output_dir.mkdir(parents=True, exist_ok=True)
    result = {
        'dataset_version': 'v3-menu',
        'model': model_name,
        'normalized': True,
        'dtype': 'float32',
        'batch_size': batch_size,
        'note': 'Restaurant and dish vectors with V3 menu mapping.'
    }
    result['restaurants'] = _build_one(restaurants, 'food_place_id', restaurant_text,
                                       'restaurants', output_dir, model, batch_size)
    result['dishes'] = _build_one(dishes, 'dish_id', dish_text,
                                  'dishes', output_dir, model, batch_size)
    # 346k menu IDs are NOT encoded redundantly; map to existing vectors instead.
    menu_map = menus[['menu_item_id', 'food_place_id', 'dish_id']].sort_values('menu_item_id')
    map_path = output_dir / 'menu_to_vectors.parquet'
    menu_map.to_parquet(map_path, index=False)
    result['menu_mapping'] = {'rows': len(menu_map), 'file': map_path.name,
                              'sha256': _sha256(map_path)}
    result['source_files'] = {
        'restaurants.parquet': _sha256(
            processed_dir / 'restaurants.parquet'
        ),
        'dishes.parquet': _sha256(
            processed_dir / 'dishes.parquet'
        ),
        'menu_items.parquet': _sha256(
            processed_dir / 'menu_items.parquet'
        ),
    }
    (output_dir / 'metadata.json').write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')
    return result


def load_embeddings(output_dir):
    import numpy as np
    import pandas as pd
    """Load and validate index mapping; return (restaurant_vectors, restaurant_ids,
    dish_vectors, dish_ids, menu_map, metadata)."""
    root = Path(output_dir)
    meta = json.loads((root / 'metadata.json').read_text(encoding='utf-8'))
    loaded = []
    for name, id_col in [('restaurants', 'food_place_id'), ('dishes', 'dish_id')]:
        info = meta[name]
        vp, ip = root / info['vectors'], root / info['ids']
        if _sha256(vp) != info['vectors_sha256'] or _sha256(ip) != info['ids_sha256']:
            raise ValueError(f'{name}: file checksum mismatch; regenerate embeddings')
        vectors, ids = np.load(vp, mmap_mode='r'), pd.read_csv(ip)
        if vectors.shape != (info['rows'], info['dimension']) or len(ids) != len(vectors):
            raise ValueError(f'{name}: vectors and ID mapping misaligned')
        if not (ids['vector_row'].to_numpy() == np.arange(len(ids))).all():
            raise ValueError(f'{name}: vector_row mapping incorrect')
        loaded.extend([vectors, ids])
    mp = root / meta['menu_mapping']['file']
    if _sha256(mp) != meta['menu_mapping']['sha256']:
        raise ValueError('menu mapping checksum mismatch')
    return (*loaded, pd.read_parquet(mp), meta)


def main():
    parser = argparse.ArgumentParser(description='Build offline dish + restaurant embeddings')
    parser.add_argument('--processed-dir', type=Path, default=Path('data/processed'))
    parser.add_argument('--output-dir', type=Path, default=Path('data/embeddings'))
    parser.add_argument('--model', default=DEFAULT_MODEL)
    parser.add_argument('--batch-size', type=int, default=64)
    args = parser.parse_args()
    result = build_embeddings(args.processed_dir, args.output_dir, args.model, args.batch_size)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
