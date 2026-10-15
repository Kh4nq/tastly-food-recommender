"""CLI configuration regressions; all provider inference is mocked."""

from pathlib import Path
import runpy
import sys
from unittest.mock import Mock

import pytest

from common.schemas import PreferenceUpdate
from conversation.interactive import cli
from conversation.providers.mock import MockProvider


MESSAGE = "Muốn ăn cơm tấm dưới 50k, gần gần thôi"
ENV_PATH = Path(__file__).resolve().parents[1] / ".env"


@pytest.fixture
def configured_cli(monkeypatch, tmp_path):
    # Supply a fake repository .env, even when launched from another directory.
    original_read = Path.read_text
    original_exists = Path.exists
    reads = []

    def read(path, *args, **kwargs):
        if path == ENV_PATH:
            reads.append(path)
            return 'LLM_PROVIDER=rule\nGEMINI_API_KEY="test-key"\nGEMINI_MODEL=test-model\n'
        return original_read(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", read)
    monkeypatch.setattr(Path, "exists", lambda path: path == ENV_PATH or original_exists(path))
    monkeypatch.chdir(tmp_path)
    instances = []

    def construct(**kwargs):
        from conversation.providers import ProviderError
        if not kwargs.get("api_key") or not kwargs.get("model"):
            raise ProviderError("Missing test Gemini configuration")
        provider = MockProvider(callback=lambda **kw: PreferenceUpdate(set_values={"food": ["cơm tấm"]}))
        provider.name = "gemini"
        instances.append(provider)
        return provider

    factory = Mock(side_effect=construct)
    monkeypatch.setattr("conversation.providers.gemini_provider.GeminiProvider", factory)
    monkeypatch.setattr("conversation.providers.openai_provider.OpenAIProvider",
                        Mock(side_effect=AssertionError("Real OpenAI forbidden")))
    return factory, instances, reads


def launch(monkeypatch, callback, provider="gemini"):
    monkeypatch.setattr(cli, "run_repl", callback)
    cli.main(["--provider", provider, "--session-id", "test", "--no-save"])


def test_cli_gemini_configuration_and_rule_merge(monkeypatch, configured_cli):
    factory, instances, reads = configured_cli

    def exercise(session):
        record = session.process(MESSAGE)
        assert record["rule_result"]["requires_llm"]
        assert record["rule_result"]["update"]["add_hard_constraints"]["budget_max"] == 50000
        assert record["rule_result"]["update"]["add_soft_preferences"]["distance"] == "near"
        assert record["provider"] == record["metadata"]["provider"] == "gemini"
        assert record["llm_called"] is True
        assert record["metadata"]["parser_used"] == "hybrid_llm"
        assert record["metadata"]["llm_error"] is None
        assert record["metadata"]["external_llm_disabled"] is False
        assert record["new_state"]["food"] == ["cơm tấm"]
        assert record["new_state"]["hard_constraints"]["budget_max"] == 50000
        assert record["new_state"]["soft_preferences"]["distance"] == "near"

    launch(monkeypatch, exercise)
    assert reads == [ENV_PATH]
    factory.assert_called_once_with(api_key="test-key", model="test-model")
    assert instances[0].call_count == 1


def test_cli_rule_sufficient_does_not_call_gemini(monkeypatch, configured_cli):
    factory, instances, _ = configured_cli

    def exercise(session):
        record = session.process("Tìm ramen dưới 150k trong vòng 2km")
        assert not record["rule_result"]["requires_llm"]
        assert not record["llm_called"]
        assert record["metadata"]["llm_error"] is None

    launch(monkeypatch, exercise)
    factory.assert_not_called()
    assert instances == []


def test_runtime_switch_reconstructs_gemini(monkeypatch, configured_cli):
    factory, instances, _ = configured_cli
    run_repl = cli.run_repl

    def exercise(session):
        lines = iter(["/provider gemini", MESSAGE, "/provider mock", MESSAGE,
                      "/provider gemini", MESSAGE, "/exit"])
        run_repl(session, read=lambda prompt: next(lines), write=lambda text: None)
        assert [r["metadata"]["provider"] for r in session.records] == ["gemini", "mock", "gemini"]
        assert all(r["llm_called"] for r in session.records)
        assert all(r["metadata"]["llm_error"] is None for r in session.records)

    launch(monkeypatch, exercise, provider="rule")
    assert factory.call_count == 2
    assert len(instances) == 2
    assert instances[0] is not instances[1]
    assert [p.call_count for p in instances] == [1, 1]
    assert all(call.kwargs == {"api_key": "test-key", "model": "test-model"}
               for call in factory.call_args_list)


def test_cli_environment_overrides_dotenv(monkeypatch, configured_cli):
    factory, _, _ = configured_cli
    monkeypatch.setenv("GEMINI_API_KEY", "environment-key")
    monkeypatch.setenv("GEMINI_MODEL", "environment-model")
    launch(monkeypatch, lambda session: session.process(MESSAGE))
    factory.assert_called_once_with(api_key="environment-key", model="environment-model")


def test_script_entrypoint_uses_cli_setup(monkeypatch, configured_cli):
    factory, instances, reads = configured_cli
    script = ENV_PATH.parent / "scripts" / "interactive_ai2.py"
    monkeypatch.setattr(sys, "argv", [str(script), "--provider", "gemini",
                                      "--session-id", "test", "--no-save"])
    # The script inserts src into sys.path; keep that mutation local to this test.
    monkeypatch.setattr(sys, "path", sys.path.copy())

    def exercise(session):
        assert session.session_id == "test"
        assert session.process(MESSAGE)["metadata"]["parser_used"] == "hybrid_llm"

    monkeypatch.setattr(cli, "run_repl", exercise)
    runpy.run_path(str(script), run_name="__main__")
    factory.assert_called_once_with(api_key="test-key", model="test-model")
    assert instances[0].call_count == 1
    assert reads == [ENV_PATH]


@pytest.mark.parametrize("env_text", ["", "GEMINI_MODEL=test-model", "GEMINI_API_KEY=test-key"])
def test_missing_gemini_configuration_falls_back(monkeypatch, env_text):
    original_read = Path.read_text
    original_exists = Path.exists
    monkeypatch.setattr(Path, "exists", lambda path: path == ENV_PATH or original_exists(path))
    monkeypatch.setattr(Path, "read_text", lambda path, *a, **kw:
                        env_text if path == ENV_PATH else original_read(path, *a, **kw))

    def exercise(session):
        record = session.process(MESSAGE)
        assert record["provider"] == "gemini"
        assert not record["llm_called"]
        assert record["metadata"]["llm_error"] == "provider_unavailable"
        assert record["metadata"]["parser_used"] == "rule_fallback"
        assert record["metadata"]["partial_result"]
        assert record["new_state"]["hard_constraints"]["budget_max"] == 50000

    launch(monkeypatch, exercise)
