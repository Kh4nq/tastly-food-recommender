"""Optional Streamlit widget tests use local AppTest and existing socket guards."""
from pathlib import Path
import asyncio
from unittest.mock import MagicMock

import pytest

from conversation.labeling.cli import load_models
from conversation.labeling.leakage import LeakageIndex
from conversation.labeling.models import PromptSample, ReviewRecord
from conversation.labeling.review import build_queue
from conversation.labeling.storage import write_rows
from conversation.labeling.teacher import label_samples

AppTest = pytest.importorskip("streamlit.testing.v1").AppTest


@pytest.fixture
def app(tmp_path, monkeypatch):
    # AppTest's unused asyncio loop creates a TCP socketpair on Windows.
    # This UI is synchronous: stub the loop, preserving every network guard.
    def offline_loop():
        loop = MagicMock(spec=asyncio.AbstractEventLoop)
        loop.is_closed.return_value = False
        return loop
    monkeypatch.setattr(asyncio, "new_event_loop", offline_loop)
    samples = load_models(Path(__file__).parent / "data/ai2_labeling_samples.jsonl", PromptSample)[:1]
    index = LeakageIndex.from_benchmark()
    labels, _ = label_samples(samples, tmp_path / "teacher_labels.jsonl", index)
    write_rows(tmp_path / "review_queue.jsonl", build_queue(samples, labels, index))
    code = "from conversation.labeling.ui import main\n" + f"main(['--directory', {str(tmp_path)!r}])\n"
    return AppTest.from_string(code, default_timeout=15).run(), tmp_path


@pytest.mark.parametrize("label,action", [("Accept", "accepted"), ("Correct", "corrected"),
                                        ("Reject", "rejected"), ("Skip", "skipped")])
def test_review_ui_actions_and_resume(app, label, action):
    at, path = app
    assert not at.exception
    assert "giúp mình" in at.subheader[0].value
    next(b for b in at.button if b.label == label).click().run()
    assert not at.exception
    rows = load_models(path / "reviewed.jsonl", ReviewRecord)
    assert len(rows) == 1 and rows[0].action == action
    at.run()
    assert not at.button
    # Revisit explicitly; old prediction and decision stay in the journal.
    at.checkbox[0].check().run()
    assert len(at.button) == 4


def test_ui_rejects_invalid_json_and_invalid_schema(app):
    at, path = app
    for text in ("{not-json}", '{"context_updates":{"party_size":-1}}'):
        at.text_area[0].set_value(text).run()
        next(b for b in at.button if b.label == "Correct").click().run()
        assert at.error and not at.exception
        assert not (path / "reviewed.jsonl").exists()
