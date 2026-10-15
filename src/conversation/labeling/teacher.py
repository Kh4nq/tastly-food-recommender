"""One-call candidate labeling through the existing AI2 parser and provider."""
from dataclasses import replace
from copy import deepcopy
from pathlib import Path

from common.schemas import PreferenceUpdate, UserRequest
from conversation.config import ConversationConfig, create_provider
from conversation.environment import load_env
from conversation.labeling.leakage import filter_pool
from conversation.labeling.models import TeacherLabel
from conversation.labeling.storage import digest, exclusive_writer, read_rows, write_rows
from conversation.parser import parse_user_input_detailed
from conversation.providers.base import ProviderError


def rule_parse(sample):
    state = sample.current_state
    request = UserRequest(session_id=state.session_id if state else sample.sample_id,
        user_id=state.user_id if state else None, message=sample.message,
        current_state=state, previous_results=sample.previous_results)
    return request, parse_user_input_detailed(request, config=ConversationConfig())


class RecordingProvider:
    name = "gemini"

    def __init__(self, provider):
        self.provider = provider
        self.prediction = None

    @property
    def last_usage(self):
        return getattr(self.provider, "last_usage", {})

    def parse_preference(self, **kwargs):
        result = self.provider.parse_preference(**kwargs)
        # Preserve the prediction before the production parser merges/normalizes it.
        if isinstance(result, PreferenceUpdate):
            self.prediction = result.model_dump(mode="json")
        elif isinstance(result, dict):
            self.prediction = deepcopy(result)
        return result


def label_samples(samples, output: Path, index, *, provider="rule", provider_factory=None):
    if provider not in {"rule", "gemini"}:
        raise ValueError("Unsupported provider")
    samples, excluded = filter_pool(samples, index)
    output = Path(output)
    with exclusive_writer(output):
        labels = [TeacherLabel.model_validate(r) for r in read_rows(output)] if output.exists() else []
        by_id = {r.sample_id: r for r in labels}
        if len(by_id) != len(labels):
            raise ValueError("Duplicate IDs in teacher journal")
        # Validate the whole resume plan before any new external call.
        for sample in samples:
            existing = by_id.get(sample.sample_id)
            if existing and (existing.sample_hash != digest(sample) or existing.provider != provider):
                raise ValueError("Resume input/provider changed; use a new output directory")
        for sample in samples:
            existing = by_id.get(sample.sample_id)
            if existing:
                continue
            request, baseline = rule_parse(sample)
            resolved = not (baseline.metadata.requires_llm or baseline.metadata.clarification_required)
            label = TeacherLabel(sample_id=sample.sample_id, sample_hash=digest(sample),
                rule_result=baseline.rule_result, rule_candidate=baseline.preference_update,
                rule_resolved=resolved, routing=baseline.metadata, provider=provider,
                candidate=baseline.preference_update.model_dump(mode="json"))
            labels.append(label)
            by_id[sample.sample_id] = label
            if provider == "gemini" and baseline.metadata.requires_llm:
                # Durable reservation BEFORE provider creation/call. Resume never retries it.
                label.status = "attempt_reserved"
                label.candidate = None
                label.error = "interrupted_attempt"
                label.attempts = 1
                write_rows(output, labels, replace=True)
                selected = None
                try:
                    if provider_factory is None:
                        load_env()
                        config = replace(ConversationConfig.from_env(), llm_provider="gemini",
                                         local_slm_enabled=False, log_enabled=False)
                        label.model = config.gemini_model
                        selected = create_provider(config)
                    else:
                        selected = provider_factory()
                        label.model = getattr(selected, "model", None)
                    recorder = RecordingProvider(selected)
                    parsed = parse_user_input_detailed(request, recorder, config=ConversationConfig())
                    label.teacher_prediction = recorder.prediction
                    label.routing = parsed.metadata
                    label.latency_ms = parsed.metadata.llm_ms
                    label.error = parsed.metadata.llm_error
                    label.retryable = label.error in {"timeout", "rate_limit"}
                    label.status = "error" if label.error else "completed"
                    label.candidate = None if label.error else parsed.preference_update.model_dump(mode="json")
                except Exception as exc:
                    label.status = "error"
                    label.error = exc.code if isinstance(exc, ProviderError) else "provider_unavailable"
                    label.retryable = label.error in {"timeout", "rate_limit"}
                    label.candidate = None
                finally:
                    if selected is not None and hasattr(selected, "close"):
                        try:
                            selected.close()
                        except Exception:
                            pass
            write_rows(output, labels, replace=True)
    return labels, excluded
