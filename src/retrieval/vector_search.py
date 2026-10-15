"""Cosine semantic scoring for the offline v2 restaurant/dish embeddings."""
from __future__ import annotations


def _unit(vectors):
    import numpy as np
    a = np.asarray(vectors, dtype=np.float32)
    if a.ndim == 1:
        a = a.reshape(1, -1)
    if a.ndim != 2 or not np.isfinite(a).all():
        raise ValueError('Embeddings must be finite 1D/2D arrays')
    norms = np.linalg.norm(a, axis=1, keepdims=True)
    return np.divide(a, norms, out=np.zeros_like(a), where=norms > 0)


def score_candidates(candidates, query_vector, restaurant_vectors, restaurant_ids,
                     dish_vectors, dish_ids, dish_weight: float = 0.75):
    """Return candidates with semantic_score; score is weighted cosine [-1, 1].

    All candidate IDs must exist in the stored row-to-ID maps. Fails loudly if
    the embedding release doesn't match the processed Parquet release.
    """
    import numpy as np
    import pandas as pd

    if not 0 <= dish_weight <= 1:
        raise ValueError('dish_weight must be between 0 and 1')
    required = {'restaurant_id', 'dish_id', 'menu_item_id'}
    if not required.issubset(candidates.columns):
        raise ValueError(f'Candidates missing {sorted(required - set(candidates.columns))}')
    out = candidates.copy()
    if out.empty:
        out['semantic_score'] = pd.Series(dtype='float32')
        return out
    for ids, id_col, vectors in [(restaurant_ids, 'food_place_id', restaurant_vectors),
                                  (dish_ids, 'dish_id', dish_vectors)]:
        if not {'vector_row', id_col}.issubset(ids.columns):
            raise ValueError(f'Missing vector mapping for {id_col}')
        if ids[id_col].duplicated().any() or ids['vector_row'].duplicated().any():
            raise ValueError(f'Duplicate vector mapping for {id_col}')
        rows = pd.to_numeric(ids['vector_row'], errors='coerce')
        if rows.isna().any() or (rows < 0).any() or (rows >= len(vectors)).any() or (rows % 1 != 0).any():
            raise ValueError(f'Invalid vector_row mapping for {id_col}')
    rmap = restaurant_ids.set_index('food_place_id')['vector_row']
    dmap = dish_ids.set_index('dish_id')['vector_row']
    ri = out['restaurant_id'].map(rmap)
    di = out['dish_id'].map(dmap)
    if ri.isna().any() or di.isna().any():
        raise ValueError(f'Candidate IDs absent from embeddings: restaurants={int(ri.isna().sum())}, dishes={int(di.isna().sum())}')
    rv, dv = _unit(restaurant_vectors), _unit(dish_vectors)
    if rv.shape[1] != dv.shape[1]:
        raise ValueError('Restaurant/dish embedding dimensions differ')
    q = _unit(query_vector)
    if q.shape != (1, rv.shape[1]) or not np.any(q):
        raise ValueError('Query embedding dimension mismatch or zero vector')
    rscore = rv[ri.to_numpy(dtype=np.int64)] @ q[0]
    dscore = dv[di.to_numpy(dtype=np.int64)] @ q[0]
    out['restaurant_similarity'] = rscore.astype('float32')
    out['dish_similarity'] = dscore.astype('float32')

    out['semantic_score'] = (
        dish_weight * dscore + (1 - dish_weight) * rscore
    ).astype('float32')

    return out
