"""Regression coverage for Kaggle float/unknown nutrient COPY and recovery."""
import importlib.util
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd

from scripts import kaggle_setup

ROOT = Path(__file__).resolve().parents[1]


def test_copy_preserves_decimal_nutrients_and_unknowns(monkeypatch):
    monkeypatch.setenv('DATABASE_URL', 'postgresql://unused')
    spec = importlib.util.spec_from_file_location('nutrition_seed', ROOT / 'scripts/seed_database.py')
    seed = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(seed)
    connection = MagicMock()
    writer = connection.cursor.return_value.__enter__.return_value.copy.return_value.__enter__.return_value
    frame = pd.DataFrame({'fat': [20.0, 3.5, float('nan')], 'protein': [16.0, 2.75, float('nan')]})
    seed.copy_dataframe(connection, 'dishes', frame, ['fat', 'protein'])
    rows = [call.args[0] for call in writer.write_row.call_args_list]
    assert rows == [(20.0, 16.0), (3.5, 2.75), (None, None)]


def test_kaggle_recovery_updates_existing_integer_schema_once(tmp_path, monkeypatch):
    schema = tmp_path / 'database/schema.sql'
    schema.parent.mkdir()
    schema.write_text('BEGIN;\nCREATE TABLE dishes (\n' + ',\n'.join(
        f'{name} INTEGER NOT NULL' for name in ('fat', 'fiber', 'sugar', 'protein')) + '\n);\nCOMMIT;')
    calls = []
    monkeypatch.setattr(kaggle_setup, 'setup_database', lambda *args: calls.append(args))
    source = (ROOT / 'dist/kaggle/fix_nutrition_schema.py').read_text(encoding='utf-8')
    namespace = {'PROJECT': tmp_path, 'LOGS': tmp_path, 'PYTHON': 'python'}
    exec(compile(source, '<kaggle-recovery>', 'exec'), namespace)
    exec(compile(source, '<kaggle-recovery>', 'exec'), namespace)
    result = schema.read_text()
    assert result.count('ALTER TABLE dishes') == 1
    for name in ('fat', 'fiber', 'sugar', 'protein'):
        assert f'{name} DOUBLE PRECISION' in result
        assert f'ALTER COLUMN {name} DROP NOT NULL' in result
    assert len(calls) == 2


def test_release_schema_preserves_missing_and_fractional_nutrition():
    schema = (ROOT / 'database/schema.sql').read_text()
    for name in ('fat', 'fiber', 'sugar', 'protein'):
        assert f'    {name} DOUBLE PRECISION,' in schema
        assert f'ALTER COLUMN {name} DROP NOT NULL' in schema
