import numpy as np
import pandas as pd
import pytest
from retrieval.embedder import build_embeddings, load_embeddings, restaurant_text, dish_text


class FakeModel:
    def encode(self, texts, **kwargs):
        values = np.array([[len(t), t.count(':'), 1] for t in texts], dtype=np.float32)
        return values / np.linalg.norm(values, axis=1, keepdims=True)


def test_texts():
    assert 'Tên quán: Quán A' in restaurant_text({'name': 'Quán A', 'supported_cuisine': None})
    assert 'Món: Phở' in dish_text({'dish_name': 'Phở', 'description': 'Nước dùng'})


def test_build_load_and_mapping(tmp_path):
    source, output = tmp_path / 'processed', tmp_path / 'embeddings'
    source.mkdir()
    pd.DataFrame([{'food_place_id': 'r2', 'name': 'B'}, {'food_place_id': 'r1', 'name': 'A'}]).to_parquet(source / 'restaurants.parquet')
    pd.DataFrame([{'dish_id': 'd2', 'dish_name': 'Bún'}, {'dish_id': 'd1', 'dish_name': 'Phở'}]).to_parquet(source / 'dishes.parquet')
    pd.DataFrame([{'menu_item_id': 'm1', 'food_place_id': 'r1', 'dish_id': 'd2'}]).to_parquet(source / 'menu_items.parquet')
    meta = build_embeddings(source, output, model=FakeModel())
    rv, ri, dv, di, menu, loaded_meta = load_embeddings(output)
    assert meta['restaurants']['rows'] == 2 and meta['dishes']['rows'] == 2
    assert ri['food_place_id'].tolist() == ['r1', 'r2']
    assert di['dish_id'].tolist() == ['d1', 'd2']
    assert rv.shape == dv.shape == (2, 3)
    assert menu.iloc[0]['menu_item_id'] == 'm1'
    assert np.allclose(np.linalg.norm(rv, axis=1), 1)
    with (output / 'restaurants_ids.csv').open('a') as f:
        f.write('\n')
    with pytest.raises(ValueError, match='checksum'):
        load_embeddings(output)
