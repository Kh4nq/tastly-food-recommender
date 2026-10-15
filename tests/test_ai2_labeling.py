"""Offline artifact safety and review gates; synthetic providers/fixtures only."""
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
import unicodedata

import pytest
from pydantic import ValidationError

from common.schemas import PreferenceUpdate, UserPreferenceState
from conversation.labeling.cli import load_models, main
from conversation.labeling.generation import TEMPLATES, generate_samples
from conversation.labeling.leakage import LeakageIndex, filter_pool, pool_issues, prompt_hash
from conversation.labeling.models import PromptSample, ReviewItem, ReviewRecord, TeacherLabel, TrainingRecord
from conversation.labeling.review import build_queue, export_records, review_item, save_review
from conversation.labeling.storage import BENCHMARK, digest, exclusive_writer, read_rows, write_rows
from conversation.labeling.teacher import label_samples
from conversation.labeling.validation import validate_batch, validate_label
from conversation.providers.base import ProviderError


@pytest.fixture
def samples():
    return load_models(Path(__file__).parent / "data/ai2_labeling_samples.jsonl", PromptSample)


@pytest.fixture
def index():
    return LeakageIndex([])


@pytest.fixture
def queue(samples, index, tmp_path):
    labels, _ = label_samples(samples, tmp_path / "teacher.jsonl", index)
    return build_queue(samples, labels, index)


def sample(message="mình đi xe máy nhé", **kwargs):
    return PromptSample(sample_id="s", category="test", message=message, **kwargs)


def test_generation_determinism_categories_and_no_labels(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Generation must not read benchmark or retrieve data")
    monkeypatch.setattr(Path, "read_text", forbidden)
    a = generate_samples(200, 42)
    assert a == generate_samples(200, 42)
    assert a != generate_samples(200, 43)
    assert len(a) == len({prompt_hash(s.message) for s in a}) == 200
    assert {s.category for s in a} == set(TEMPLATES)
    assert any(s.history for s in a) and any(not s.history for s in a)
    assert all("target" not in s.model_dump() and "candidate" not in s.model_dump() for s in a)
    for s in a:
        assert s.source == "synthetic_template" and s.generation["seed"] == 42
        if s.mock_candidates:
            assert s.mock_candidates[1].restaurant_id == s.previous_results[1].restaurant_id
            assert s.mock_candidates[1].dish_id == "SYNTHETIC-D2"
        assert "relative_updates" not in s.current_state.context
    assert all(not s.history and not s.previous_results for s in generate_samples(30, multi_turn=False, with_results=False))


def test_serialization_uses_canonical_preference_schema():
    update = PreferenceUpdate(context_updates={"transport_mode": "xe máy"}, relative_updates={"budget": "decrease"})
    target = TrainingRecord(input={}, target=update, metadata={})
    assert type(target.target) is PreferenceUpdate
    assert TrainingRecord.model_validate_json(target.model_dump_json()) == target
    assert target.schema_version == "0.2" and len(target.target.model_dump()) == 9


@pytest.mark.parametrize("payload,error", [
    ({"parking": True}, "invalid_preference_update_schema"),
    ({"add_hard_constraints": {"parking": True}}, "parking_without_explicit_evidence"),
    ({"add_soft_preferences": {"parking": True}}, "parking_without_explicit_evidence"),
    ({"set_values": {"hard_constraints": {"parking": True}}}, "parking_without_explicit_evidence"),
    ({"add_hard_constraints": {"wifi": True}, "add_soft_preferences": {"wifi": True}}, "hard_soft_conflict"),
    ({"add_hard_constraints": {"budget_max": 90_000}, "relative_updates": {"budget": "decrease"}}, "absolute_relative_conflict"),
    ({"set_values": {"soft_preferences": {"max_distance_km": 2}}, "relative_updates": {"distance": "decrease"}}, "absolute_relative_conflict"),
    ({"context_updates": {"relative_updates": {"budget": "decrease"}}}, "invalid_preference_update_schema"),
    ({"set_values": {"context": {"relative_updates": {"budget": "decrease"}}}}, "relative_event_in_context"),
    ({"remove_preferences": ["budget_max"]}, "noncanonical_removal_path"),
    ({"remove_preferences": ["banana.wifi"]}, "invalid_removal_path"),
    ({"remove_preferences": ["context."]}, "invalid_removal_path"),
    ({"set_values": {"food": 123}}, "invalid_preference_update_schema"),
    ({"add_soft_preferences": {"allergens_excluded": ["peanut"]}}, "allergy_in_soft_preferences"),
])
def test_validator_invariants(index, payload, error):
    result = validate_label(sample(), payload, index)
    assert not result.passed and error in result.errors


@pytest.mark.parametrize("message", ["dị ứng đậu phộng", "dị ứng tôm", "dị ứng trứng"])
def test_allergy_cannot_be_a_dislike(index, message):
    result = validate_label(sample(message), {"add_negative_preferences": ["peanut"]}, index)
    assert "allergy_hard_exclusion_missing" in result.errors
    assert "allergy_safety" in result.risk_flags


def test_unrelated_existing_allergy_does_not_mask_new_one(index):
    state = UserPreferenceState(session_id="s", hard_constraints={"allergens_excluded": ["peanut"]})
    assert not validate_label(sample("dị ứng tôm", current_state=state), {}, index).passed


def test_canonical_paths_extension_and_removal_precedence(index):
    payload = {"add_hard_constraints": {"wifi": True}, "add_soft_preferences": {"wifi": True, "custom_feature": "ok"},
               "remove_preferences": ["hard_constraints.wifi", "context.transport_mode"]}
    assert validate_label(sample(), payload, index).passed
    state = UserPreferenceState(session_id="s", context={"relative_updates": {"budget": "decrease"}})
    assert "relative_event_in_input_context" in validate_label(sample(current_state=state), {}, index).errors


def test_vague_distance_and_ambiguity(index):
    assert "vague_near_is_not_relative" in validate_label(sample("đi bộ gần gần"), {"relative_updates": {"distance": "decrease"}}, index).errors
    result = validate_label(sample("chỗ đó như hôm trước ấy"), {}, index)
    assert result.passed and "ambiguous_semantics" in result.risk_flags


def test_leakage_exact_unicode_punctuation_and_history(samples):
    original = samples[0]
    index = LeakageIndex([original.message])
    variant = original.model_copy(update={"sample_id": "variant", "message": unicodedata.normalize("NFD", original.message.upper()) + "!!!"})
    history = samples[1].model_copy(update={"history": [original.message]})
    accepted, excluded = filter_pool([original, variant, history], index)
    assert not accepted
    assert [e["reason"] for e in excluded] == ["benchmark_exact_overlap", "benchmark_normalized_overlap", "benchmark_exact_overlap"]
    assert all("message" not in e for e in excluded)


def test_actual_benchmark_is_excluded_before_teacher(tmp_path):
    before = BENCHMARK.read_bytes()
    message = read_rows(BENCHMARK)[0]["message"]
    factory = lambda: pytest.fail("Leaked benchmark must never reach teacher")
    labels, excluded = label_samples([sample(message)], tmp_path / "labels.jsonl", LeakageIndex.from_benchmark(),
                                     provider="gemini", provider_factory=factory)
    assert not labels and excluded[0]["reason"] == "benchmark_exact_overlap"
    assert BENCHMARK.read_bytes() == before


def test_duplicate_detection(samples, index):
    original = samples[0]
    exact = original.model_copy(update={"sample_id": "different"})
    normalized = original.model_copy(update={"sample_id": "third", "message": original.message.upper() + "!"})
    repeated_id = original.model_copy(update={"message": "một nội dung khác"})
    kept, excluded = filter_pool([original, exact, normalized, repeated_id], index)
    assert kept == [original]
    assert [r["reason"] for r in excluded] == ["duplicate_exact_message", "duplicate_normalized_message", "duplicate_sample_id"]
    issues = pool_issues([original, original], index)
    assert all("duplicate_sample_id" in item and "duplicate_normalized_message" in item for item in issues)


def test_rule_provider_never_loads_config_models_or_providers(monkeypatch, samples, index, tmp_path):
    def forbidden(*args, **kwargs):
        pytest.fail("Offline path invoked inference/configuration")
    monkeypatch.setenv("LOCAL_SLM_ENABLED", "true")
    monkeypatch.setattr("conversation.labeling.teacher.load_env", forbidden)
    monkeypatch.setattr("conversation.labeling.teacher.create_provider", forbidden)
    labels, _ = label_samples(samples, tmp_path / "labels.jsonl", index)
    assert not any(l.attempts or l.routing.slm_called or l.routing.llm_called for l in labels)
    assert labels[0].rule_resolved and not labels[1].rule_resolved
    assert labels[2].rule_resolved  # Existing standalone reference routing override.
    assert labels[2].candidate["references"][0]["restaurant_id"] == "FIXTURE-R2"


@pytest.mark.parametrize("outcome,code", [(TimeoutError("secret-key"), "timeout"),
    (ProviderError("secret-key", code="rate_limit"), "rate_limit"),
    (ProviderError("secret-key", code="authentication_error"), "authentication_error"),
    ({"unexpected": True}, "invalid_output")])
def test_teacher_failures_no_fallback_labels_or_retries(samples, index, tmp_path, outcome, code, capsys):
    calls = []
    def parse(**kwargs):
        calls.append(kwargs)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome
    provider = SimpleNamespace(parse_preference=parse, model="test-model")
    path = tmp_path / "teacher.jsonl"
    labels, _ = label_samples([samples[1]], path, index, provider="gemini", provider_factory=lambda: provider)
    label = labels[0]
    assert label.status == "error" and label.error == code and label.candidate is None
    assert label.rule_result.update and label.attempts == len(calls) == 1
    assert label.retryable == (code in {"timeout", "rate_limit"})
    resumed, _ = label_samples([samples[1]], path, index, provider="gemini", provider_factory=lambda: provider)
    assert resumed == labels and len(calls) == 1
    assert "secret-key" not in path.read_text(encoding="utf-8") + capsys.readouterr().out
    assert build_queue([samples[1]], labels, index)[0].priority == "high"


def test_teacher_success_preserves_raw_prediction_and_existing_merge(samples, index, tmp_path):
    prediction = PreferenceUpdate(set_values={"food": ["bánh cuốn"]}, add_hard_constraints={"parking": True})
    calls = []
    def parse(**kwargs):
        calls.append(kwargs)
        return prediction
    labels, _ = label_samples(samples[:2], tmp_path / "labels.jsonl", index, provider="gemini",
        provider_factory=lambda: SimpleNamespace(parse_preference=parse, model="mock-model"))
    assert len(calls) == 1 and labels[0].attempts == 0
    label = labels[1]
    assert label.teacher_prediction["add_hard_constraints"]["parking"] is True
    assert "parking" not in label.candidate["add_hard_constraints"]
    assert label.candidate["set_values"]["food"] == ["bánh cuốn"]
    assert label.model == "mock-model" and label.latency_ms >= 0
    item = build_queue(samples[:2], labels, index)[0]
    assert item.disagreement and item.priority == "high"


def test_crash_reservation_prevents_second_call(samples, index, tmp_path):
    path = tmp_path / "labels.jsonl"
    calls = []
    def interrupted(**kwargs):
        calls.append(1)
        raise KeyboardInterrupt()
    provider = SimpleNamespace(parse_preference=interrupted)
    with pytest.raises(KeyboardInterrupt):
        label_samples([samples[1]], path, index, provider="gemini", provider_factory=lambda: provider)
    saved = load_models(path, TeacherLabel)[0]
    assert saved.status == "attempt_reserved" and saved.candidate is None
    label_samples([samples[1]], path, index, provider="gemini", provider_factory=lambda: provider)
    assert len(calls) == 1


def test_resume_rejects_changed_context_provider_and_duplicate_journal(samples, index, tmp_path):
    path = tmp_path / "labels.jsonl"
    labels, _ = label_samples(samples[:1], path, index)
    before = path.read_bytes()
    changed = samples[0].model_copy(deep=True)
    changed.current_state.food = ["pizza"]
    with pytest.raises(ValueError, match="Resume"):
        label_samples([changed], path, index)
    with pytest.raises(ValueError, match="Resume"):
        label_samples(samples[:1], path, index, provider="gemini")
    assert path.read_bytes() == before
    write_rows(path, [labels[0], labels[0]], replace=True)
    with pytest.raises(ValueError, match="Duplicate"):
        label_samples(samples[:1], path, index)


@pytest.mark.parametrize("action", ["accepted", "corrected", "rejected", "skipped"])
def test_review_actions_preserve_original(queue, index, tmp_path, action):
    item = next(i for i in queue if i.sample.sample_id == "fixture-clear")
    original = deepcopy(item.model_dump())
    correction = {"set_values": {"food": ["ramen"]}, "add_hard_constraints": {"budget_max": 85000, "max_distance_km": 4}}
    record = review_item(item, action, index, correction=correction, note="synthetic test decision")
    path = tmp_path / "reviewed.jsonl"
    save_review(path, record)
    assert load_models(path, ReviewRecord)[0] == record
    assert record.original_candidate == item.teacher.candidate
    assert item.model_dump() == original
    assert record.timestamp.tzinfo is not None
    assert (record.final_label is not None) == (action in {"accepted", "corrected"})


def test_invalid_correction_does_not_save(queue, index, tmp_path):
    with pytest.raises(ValidationError):
        review_item(queue[0], "corrected", index, correction={"context_updates": {"party_size": -1}})
    with pytest.raises(ValueError):
        review_item(queue[0], "corrected", index, correction={"add_hard_constraints": {"parking": True}})
    assert not (tmp_path / "reviewed.jsonl").exists()


def test_export_excludes_unreviewed_rejected_skipped_and_resolved(queue, index):
    assert export_records(queue, [], index)[0] == []
    reviews = [review_item(i, "accepted", index) for i in queue]
    training, _ = export_records(queue, reviews, index)
    assert len(training) == 3 and all(r.schema_version == "0.2" for r in training)
    unresolved, _ = export_records(queue, reviews, index, only_unresolved=True)
    assert len(unresolved) == 1 and unresolved[0].metadata["sample_id"] == "fixture-unclear"
    for action in ("rejected", "skipped"):
        latest = [review_item(i, action, index) for i in queue]
        assert not export_records(queue, reviews + latest, index)[0]


def test_export_revalidates_and_refuses_stale_reviews_duplicates_and_leakage(queue, index):
    item = queue[0]
    record = review_item(item, "accepted", index)
    assert not export_records([item], [record], LeakageIndex([item.sample.message]))[0]
    assert not export_records([item, item], [record], index)[0]
    edited = item.model_copy(deep=True)
    edited.sample.message += " altered"
    assert not export_records([edited], [record], index)[0]
    invalid = record.model_copy(update={"action": "corrected", "final_label": {"oops": True}})
    assert not export_records([item], [invalid], index)[0]
    tampered_accept = record.model_copy(update={"final_label": {}})
    assert not export_records([item], [tampered_accept], index)[0]


def test_review_journal_retains_old_decisions(queue, index, tmp_path):
    path = tmp_path / "reviews.jsonl"
    first = review_item(queue[0], "accepted", index)
    save_review(path, first)
    save_review(path, review_item(queue[0], "rejected", index))
    records = load_models(path, ReviewRecord)
    assert records[0] == first and len(records) == 2
    assert not export_records([queue[0]], records, index)[0]


@pytest.mark.parametrize("reference", [
    {"status": "resolved", "rank": 2, "restaurant_id": "FAKE"},
    {"status": "resolved", "rank": 1, "restaurant_id": "FIXTURE-R2"},
    {"status": "resolved", "rank": 2, "restaurant_id": "FIXTURE-R2", "menu_item_id": "FAKE"},
    {"status": "resolved", "rank": 2, "restaurant_id": "FIXTURE-R2", "similar_to": "FAKE"},
    {"status": "unresolved", "restaurant_id": "FIXTURE-R2"},
    {"status": "banana", "restaurant_id": "FIXTURE-R2"},
])
def test_invalid_reference_fixture(samples, index, reference):
    assert not validate_label(samples[2], {"references": [reference]}, index).passed


def test_storage_locks_no_overwrites_and_secrets(tmp_path, monkeypatch):
    path = tmp_path / "artifact.jsonl"
    write_rows(path, [{"a": 1}])
    with pytest.raises(ValueError):
        write_rows(path, [{"a": 2}])
    assert read_rows(path) == [{"a": 1}]
    with exclusive_writer(path):
        with pytest.raises(ValueError, match="lock"):
            with exclusive_writer(path):
                pytest.fail("Second writer acquired lock")
    monkeypatch.setenv("GEMINI_API_KEY", "fake-private-value")
    with pytest.raises(ValueError, match="credential"):
        write_rows(tmp_path / "secret.jsonl", [{"message": "fake-private-value"}])
    assert not (tmp_path / "secret.jsonl").exists()
    with pytest.raises(ValueError, match="benchmark"):
        write_rows(BENCHMARK, [])


def test_offline_orchestrator_resume_export_and_cli_stats(tmp_path, monkeypatch, capsys):
    def forbidden(*a, **kw):
        pytest.fail("Dry run invoked provider or .env")
    monkeypatch.setattr("conversation.labeling.teacher.create_provider", forbidden)
    monkeypatch.setattr("conversation.labeling.teacher.load_env", forbidden)
    args = ["--directory", str(tmp_path), "--count", "20", "--provider", "gemini", "--dry-run"]
    assert main("prepare", args) == 0
    journal = (tmp_path / "teacher_labels.jsonl").read_bytes()
    assert main("prepare", args) == 0
    assert (tmp_path / "teacher_labels.jsonl").read_bytes() == journal
    assert not (tmp_path / "training_v02.jsonl").exists()
    assert not (tmp_path / "reviewed.jsonl").exists()
    assert main("queue", ["--directory", str(tmp_path), "--stats"]) == 0
    assert main("export", ["--directory", str(tmp_path)]) == 0
    assert read_rows(tmp_path / "training_v02.jsonl") == []
    assert len(read_rows(tmp_path / "training_v02.jsonl.excluded.jsonl")) == 20
    assert '"exported": 0' in capsys.readouterr().out


def test_validation_batch_duplicate_ids_and_missing_labels(samples, index):
    results = validate_batch([samples[0], samples[0]], [], index)
    assert all(not r.passed and "duplicate_sample_id" in r.errors and "missing_teacher_label" in r.errors for r in results)


def test_cli_error_never_echoes_secret_values(tmp_path, capsys):
    pool = tmp_path / "prompt_pool.jsonl"
    pool.write_text('{"sample_id":"test", "message":"Bearer super-private-value"}\n', encoding="utf-8")
    assert main("teacher", ["--directory", str(tmp_path)]) == 2
    assert "super-private-value" not in capsys.readouterr().out


def test_existing_gemini_config_is_reused_with_slm_forced_off(samples, index, tmp_path, monkeypatch):
    observed = []
    monkeypatch.setenv("LOCAL_SLM_ENABLED", "true")
    monkeypatch.setenv("GEMINI_MODEL", "synthetic-test-model")
    monkeypatch.setattr("conversation.labeling.teacher.load_env", lambda: observed.append("env"))
    def factory(config):
        assert config.llm_provider == "gemini" and not config.local_slm_enabled and not config.log_enabled
        observed.append("factory")
        return SimpleNamespace(parse_preference=lambda **kw: PreferenceUpdate(set_values={"food": ["bánh cuốn"]}))
    monkeypatch.setattr("conversation.labeling.teacher.create_provider", factory)
    labels, _ = label_samples(samples[:2], tmp_path / "labels.jsonl", index, provider="gemini")
    assert observed == ["env", "factory"]
    assert labels[1].model == "synthetic-test-model" and labels[1].status == "completed"


def test_human_correction_can_recover_failed_teacher(samples, index, tmp_path):
    def broken(**kw):
        raise ProviderError("synthetic failure")
    labels, _ = label_samples(samples[1:2], tmp_path / "teacher.jsonl", index, provider="gemini",
        provider_factory=lambda: SimpleNamespace(parse_preference=broken))
    item = build_queue(samples[1:2], labels, index)[0]
    with pytest.raises(ValueError, match="failed"):
        review_item(item, "accepted", index)
    corrected = review_item(item, "corrected", index, correction={"set_values": {"food": ["bánh cuốn"]}})
    training, excluded = export_records([item], [corrected], index)
    assert len(training) == 1 and not excluded
    assert training[0].metadata["review_status"] == "corrected"
    assert item.teacher.candidate is None and corrected.original_candidate is None


def test_full_resume_preflight_happens_before_new_calls(samples, index, tmp_path):
    path = tmp_path / "labels.jsonl"
    label_samples(samples[:1], path, index, provider="gemini")
    changed = samples[0].model_copy(update={"message": "changed input"})
    with pytest.raises(ValueError, match="Resume"):
        label_samples([samples[1], changed], path, index, provider="gemini",
            provider_factory=lambda: pytest.fail("Must reject changed resume input before any new call"))


def test_stale_and_malformed_validation_records(samples, index, tmp_path):
    labels, _ = label_samples(samples[:1], tmp_path / "teacher.jsonl", index)
    altered = samples[0].model_copy(update={"message": "new message"})
    assert "stale_teacher_label" in validate_batch([altered], labels, index)[0].errors
    with pytest.raises(ValueError, match="Duplicate"):
        validate_batch(samples[:1], labels + labels, index)


def test_individual_cli_stages_and_invalid_exit(tmp_path, samples):
    pool = tmp_path / "prompt_pool.jsonl"
    write_rows(pool, samples[:2])
    options = ["--directory", str(tmp_path)]
    assert main("teacher", options) == 0
    assert main("validate", options) == 0
    assert main("queue", options) == 0
    labels = read_rows(tmp_path / "teacher_labels.jsonl")
    labels[0]["candidate"] = {"illegal_top_level": True}
    write_rows(tmp_path / "teacher_labels.jsonl", labels, replace=True)
    assert main("validate", options) == 1
    assert not read_rows(tmp_path / "validation.jsonl")[0]["passed"]
