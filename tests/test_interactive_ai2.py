"""Interactive data workflow tests: never use a live provider."""

from copy import deepcopy
import json
from pathlib import Path

import pytest

from common.schemas import PreferenceUpdate
from conversation.interactive.cli import QUOTA_WARNING, run_repl
from conversation.interactive.session import InteractiveSession
from conversation.providers.gemini_provider import GeminiProvider


@pytest.fixture(autouse=True)
def no_real_gemini(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Real Gemini forbidden")
    monkeypatch.setattr(GeminiProvider, "__init__", forbidden)


@pytest.fixture
def session(tmp_path):
    return InteractiveSession(provider="rule", directory=tmp_path / "data")


def rows(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def repl(session, lines):
    iterator = iter(lines)
    output = []

    def read(prompt):
        try:
            return next(iterator)
        except StopIteration:
            raise EOFError from None

    run_repl(session, read, output.append)
    return "\n".join(output)


def test_state_persists(session):
    first = session.process("hôm nay muốn ăn ramen dưới 150k")
    second = session.process("gần gần thôi")
    assert second["old_state"] == first["new_state"]
    assert session.current_state.food == ["ramen"]
    assert session.current_state.hard_constraints["budget_max"] == 150000
    session.current_state.food.append("test")
    assert first["new_state"]["food"] == ["ramen"]


def test_reset_preserves_saved_data(session):
    session.process("ramen")
    session.label("accepted")
    session.results("demo")
    old_id = session.session_id
    session.reset()
    assert session.session_id != old_id
    assert not session.current_state.food
    assert not session.previous_results
    assert not session.history
    assert len(rows(session.logger.path)) == 1
    assert len(rows(session.export())) == 1
    with pytest.raises(ValueError):
        session.correct("{}")


def test_rule_zero_external_calls(session, monkeypatch):
    from conversation.config import create_provider
    configurations = []

    def factory(config):
        configurations.append(config.llm_provider)
        assert config.llm_provider == "none"
        return create_provider(config)

    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setattr("conversation.parser.create_provider", factory)
    result = session.process("quán chill để date")
    assert configurations == ["none"]
    assert result["rule_result"]["requires_llm"]
    assert not result["llm_called"]
    assert result["metadata"]["external_llm_disabled"]
    assert result["metadata"]["partial_result"]


def test_mock_works(session):
    session.set_provider("mock")
    session.mock.callback = lambda **kwargs: PreferenceUpdate(add_semantic_preferences=["chill"])
    result = session.process("quán chill để date")
    assert session.mock.call_count == 1
    assert result["llm_called"]
    assert result["metadata"]["llm_error"] is None
    assert session.current_state.semantic_preferences == ["relaxed ambience"]


@pytest.mark.parametrize("status", ["accepted", "rejected"])
def test_labels(session, status):
    session.process("ramen")
    session.label(status)
    assert rows(session.logger.path)[0]["label_status"] == status


def test_correction_retains_prediction_and_rebuilds_from_old_state(session):
    session.process("ramen dưới 100k")
    prediction = session.process("pizza dưới 200k")
    correction = '{"add_hard_constraints": {"budget_max": 150000}}'
    session.correct(correction)
    record = rows(session.logger.path)[-1]
    assert record["preference_update"] == prediction["preference_update"]
    assert record["new_state"] == prediction["new_state"]
    assert record["correction"]["add_hard_constraints"]["budget_max"] == 150000
    assert record["label_status"] == "corrected"
    assert session.current_state.food == ["ramen"]
    assert session.current_state.hard_constraints["budget_max"] == 150000
    next_record = session.process("gần gần thôi")
    assert next_record["old_state"] == record["corrected_state"]


def test_export_reviewed_only(session):
    accepted = session.process("ramen")
    session.label("accepted")
    session.process("pizza")
    session.correct('{"set_values":{"food":["sushi"]}}')
    corrected = deepcopy(session.history[-1]["correction"])
    session.process("bún")
    session.label("rejected")
    session.process("phở")
    output = rows(session.export())
    assert len(output) == 2
    assert output[0]["target"] == accepted["preference_update"]
    assert output[1]["target"] == corrected
    assert [item["label_status"] for item in output] == ["accepted", "corrected"]
    assert set(output[0]) == {"schema_version", "input", "target", "source", "label_status"}
    assert set(output[0]["input"]) == {"message", "old_state", "previous_results"}


def test_results_demo_reference(session):
    session.results("demo")
    record = session.process("cái thứ hai ổn nhưng hơi xa")
    assert record["previous_results"][1]["restaurant_id"] == "R002"
    assert any(ref.get("restaurant_id") == "R002" for ref in record["preference_update"]["references"])


def test_results_file(session, tmp_path):
    path = tmp_path / "results.json"
    path.write_text('[{"rank":1,"restaurant_id":"R9","restaurant_name":"Quán Việt"}]', encoding="utf-8")
    session.results(str(path))
    assert session.previous_results[0].restaurant_name == "Quán Việt"


def test_utf8(session):
    message = "cái thứ hai khá ổn nhưng xa quá, tìm giống nó mà gần hơn"
    session.process(message)
    assert rows(session.logger.path)[0]["message"] == message
    assert message.encode("utf-8") in session.logger.path.read_bytes()


def test_no_save(tmp_path, monkeypatch):
    monkeypatch.setenv("CONVERSATION_LOG_ENABLED", "true")
    monkeypatch.setenv("CONVERSATION_LOG_PATH", str(tmp_path / "audit.jsonl"))
    session = InteractiveSession(provider="mock", no_save=True, directory=tmp_path / "data")
    repl(session, ["ramen", "/accept", "/save", "/export", "/exit"])
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("payload", ["{broken", '{"unknown":1}', '{"set_values":{"food":3}}', "[]"])
def test_invalid_correction_atomic_and_repl_survives(session, payload):
    session.process("ramen")
    before = deepcopy(session.history)
    state = session.current_state.model_dump()
    output = repl(session, ["/correct", payload, "END", "/state", "/exit"])
    assert "Error:" in output and "Goodbye." in output
    assert session.history == before
    assert session.current_state.model_dump() == state


@pytest.mark.parametrize("payload", ["broken", "{}", '[{"rank":0}]', '[{"rank":1,"restaurant_id":"R"},{"rank":1,"restaurant_id":"B"}]'])
def test_invalid_results_repl_survives(session, tmp_path, payload):
    session.results("demo")
    path = tmp_path / "bad.json"
    path.write_text(payload, encoding="utf-8")
    output = repl(session, [f"/results {path}", "/results missing.json", "/state"])
    assert output.count("Error:") == 2
    assert len(session.previous_results) == 3


def test_key_redacted_everywhere(tmp_path, monkeypatch):
    secret = "private-test-credential-123"
    monkeypatch.setenv("GEMINI_API_KEY", secret)
    session = InteractiveSession(provider="mock", directory=tmp_path)
    session.process("hello " + secret)
    session.correct(json.dumps({"add_semantic_preferences": [secret], "add_soft_preferences": {secret: True}}))
    export = session.export()
    for path in (session.logger.path, export):
        text = path.read_text(encoding="utf-8")
        assert secret not in text
        assert "[REDACTED]" in text


@pytest.mark.parametrize("env,expected", [(None, "rule"), ("none", "rule"), ("unknown", "rule"), ("mock", "mock"), ("gemini", "gemini")])
def test_default_provider(tmp_path, monkeypatch, env, expected):
    if env is None:
        monkeypatch.delenv("LLM_PROVIDER", raising=False)
    else:
        monkeypatch.setenv("LLM_PROVIDER", env)
    session = InteractiveSession(directory=tmp_path, no_save=True)
    assert session.provider == expected


def test_provider_warning_and_switch(session):
    output = repl(session, ["/provider gemini", "/provider rule", "/provider invalid", "/exit"])
    assert QUOTA_WARNING in output
    assert session.provider == "rule"
    session.set_provider("gemini")
    assert QUOTA_WARNING in repl(session, ["/exit"])


@pytest.mark.parametrize("invalid", [False, True])
def test_gemini_failure_uses_existing_fallback(session, monkeypatch, invalid):
    class FakeGemini:
        name = "gemini"
        last_usage = {"input_tokens": 10, "output_tokens": 2, "total_tokens": 12}

        def parse_preference(self, **kwargs):
            if invalid:
                return {"nonsense": True}
            raise RuntimeError("secret SDK error should not be saved")

    monkeypatch.setattr("conversation.parser.create_provider", lambda config: FakeGemini())
    session.set_provider("gemini")
    record = session.process("quán chill để date ramen dưới 150k")
    assert record["metadata"]["partial_result"]
    assert record["metadata"]["llm_error"]
    assert record["metadata"]["usage"]["total_tokens"] == 12
    assert session.current_state.hard_constraints["budget_max"] == 150000
    assert "secret SDK" not in session.logger.path.read_text(encoding="utf-8")


def test_save_failure_retains_memory_and_file(session, monkeypatch):
    session.process("ramen")
    original = session.logger.path.read_bytes()
    with monkeypatch.context() as patch:
        patch.setattr("conversation.interactive.dataset_logger.os.replace", lambda *args: (_ for _ in ()).throw(OSError()))
        session.process("pizza")
        assert session.save_error
        assert session.logger.path.read_bytes() == original
    assert session.save()
    assert len(rows(session.logger.path)) == 2


def test_interrupt_during_atomic_save(session, monkeypatch):
    session.process("ramen")
    original = session.logger.path.read_bytes()
    with monkeypatch.context() as patch:
        patch.setattr("conversation.interactive.dataset_logger.os.replace", lambda *args: (_ for _ in ()).throw(KeyboardInterrupt()))
        with pytest.raises(KeyboardInterrupt):
            session.process("pizza")
    assert session.logger.path.read_bytes() == original
    assert list(session.logger.directory.iterdir()) == [session.logger.path]
    session.save()
    assert len(rows(session.logger.path)) == 2


def test_repl_history_outputs_and_invalid_command(session):
    output = repl(session, ["ramen dưới 150k", "/accept", "/history", "/unknown", "/exit"])
    for heading in ("RULE RESULT", "LLM", "PREFERENCE UPDATE", "NEW STATE", "LATENCY", "USAGE"):
        assert heading in output
    assert '1. "ramen dưới 150k"' in output
    assert "provider=rule  accepted" in output
    assert "Unknown command" in output


def test_correct_after_reject(session):
    session.process("ramen")
    session.label("rejected")
    session.correct('{"set_values":{"food":["pizza"]}}')
    assert rows(session.export())[0]["label_status"] == "corrected"


def test_eof_cancels_incomplete_correction(session):
    session.process("ramen")
    before = deepcopy(session.history)
    output = repl(session, ["/correct", "{"])
    assert session.history == before
    assert "Goodbye." in output


def test_ctrl_c_cancels_correction_and_continues(session):
    session.process("ramen")
    actions = iter(["/correct", KeyboardInterrupt(), "/accept", EOFError()])
    output = []

    def read(prompt):
        item = next(actions)
        if isinstance(item, BaseException):
            raise item
        return item

    run_repl(session, read, output.append)
    assert session.history[-1]["correction"] is None
    assert rows(session.logger.path)[-1]["label_status"] == "accepted"
    assert "Input cancelled" in "\n".join(output)
