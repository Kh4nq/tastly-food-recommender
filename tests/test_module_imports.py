"""Cold imports must be offline, light, and preserve canonical class identities."""

import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest


@pytest.mark.parametrize("src_first", [True, False])
@pytest.mark.parametrize("checkout_parent", [None, "data", "models", "benchmarks"])
def test_cold_public_imports_have_no_external_side_effects(src_first, checkout_parent, tmp_path):
    script = r'''
import builtins
import importlib
import os
import socket
import sys
from pathlib import Path

def forbidden(*args, **kwargs):
    raise AssertionError("Import attempted external work")

socket.socket.connect = forbidden
socket.create_connection = forbidden
original_import = builtins.__import__
def guarded_import(name, *args, **kwargs):
    if name.split('.')[0] in {'openai', 'google', 'torch', 'transformers', 'numpy', 'pandas', 'lightgbm', 'xgboost'}:
        raise AssertionError('Unexpected heavy/SDK import: ' + name)
    return original_import(name, *args, **kwargs)
builtins.__import__ = guarded_import

repo_root = Path.cwd().resolve()

def audit(event, args):
    if event == 'open' and isinstance(args[0], (str, bytes)):
        path = Path(os.fsdecode(args[0])).resolve()
        try:
            relative = path.relative_to(repo_root)
        except ValueError:
            return  # Ancestors and sibling checkouts are outside this repository.
        if relative.name == '.env' or relative.parts[:1] in [('data',), ('models',), ('benchmarks',)]:
            raise AssertionError('Import read data/model/secret file')
sys.addaudithook(audit)

# Exercise the installed hook without opening secrets or creating data files.
for name in ('data/fixture.json', 'models/weights.bin', 'benchmarks/prompts.jsonl', '.env'):
    for path in (name, str(repo_root / name), os.fsencode(repo_root / name), 'src/../' + name):
        try:
            sys.audit('open', path, 'r', 0)
        except AssertionError as error:
            assert str(error) == 'Import read data/model/secret file'
        else:
            raise AssertionError('Repository-sensitive path was allowed: ' + repr(path))
for path in (repo_root / 'src/common/schemas.py', repo_root / 'tests/data/fixture.json',
             repo_root.parent / 'sibling/data/fixture.json', repo_root.parent / '.env'):
    sys.audit('open', str(path), 'r', 0)

if SRC_FIRST:
    import src.common.schemas
else:
    import common.schemas
from src.common.schemas import UserRequest, UserPreferenceState, PreferenceUpdate, Candidate, RankedResult, FeedbackEvent, RecommendationResponse
from src.conversation import parse_user_input, update_state
from src.retrieval import retrieve_candidates
from src.ranking import rank_candidates
from src.pipeline import recommend
import common.schemas as canonical
import conversation
assert Path(canonical.__file__).resolve().is_relative_to(repo_root)
assert UserRequest is canonical.UserRequest
assert UserPreferenceState is canonical.UserPreferenceState
assert Candidate is canonical.Candidate
assert PreferenceUpdate is canonical.PreferenceUpdate
assert parse_user_input is conversation.parse_user_input
assert update_state is conversation.update_state
assert callable(recommend)
for name in ('retrieval.hard_filter', 'retrieval.geo_search', 'retrieval.embedder',
             'retrieval.vector_search', 'ranking.feature_builder', 'ranking.baseline_ranker',
             'ranking.model_ranker', 'ranking.train', 'ranking.evaluate',
             'personalization.food_preference', 'personalization.user_profile'):
    importlib.import_module(name)
assert not any(name.startswith('conversation.slm') for name in sys.modules)
assert callable(retrieve_candidates)

state = UserPreferenceState(session_id='S')
assert rank_candidates(state, []) == []
'''.replace("SRC_FIRST", repr(src_first))
    root = Path(__file__).resolve().parents[1]
    if checkout_parent is not None:
        checkout = tmp_path / checkout_parent / "MLAI"
        shutil.copytree(root / "src", checkout / "src",
                        ignore=shutil.ignore_patterns(
                            "__pycache__",
                            "*.egg-info",
                            ".next",
                            "node_modules",
                        )
                    )
        root = checkout
    env = {**os.environ, "PYTHONPATH": os.pathsep.join([str(root), str(root / "src")])}
    result = subprocess.run([sys.executable, "-c", script], cwd=root, env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
