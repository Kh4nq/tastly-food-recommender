"""Session orchestration only: all inference and state transitions reuse AI 2."""

from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path

from common.schemas import PreferenceUpdate, PreviousResult, UserPreferenceState, UserRequest
from conversation.config import ConversationConfig
from conversation.interactive.dataset_logger import DatasetLogger, timestamp, unique_name
from conversation.providers.mock import MockProvider
from conversation.service import process_user_request
from conversation.state_manager import update_state


DEMO_RESULTS = [
    {"rank": rank, "restaurant_id": f"R{rank:03}", "restaurant_name": name}
    for rank, name in enumerate(("A", "B", "C"), 1)
]


class InteractiveSession:
    def __init__(self, *, provider: str | None = None, session_id: str | None = None,
                 directory: Path = Path("data/ai2_interactive"), no_save: bool = False):
        self.config = replace(ConversationConfig.from_env(), log_enabled=False)
        self.logger = DatasetLogger(directory, enabled=not no_save,
                                    secrets=(self.config.gemini_api_key, self.config.openai_api_key))
        self.records: list[dict] = []
        self.history: list[dict] = []
        self.save_error: str | None = None
        self.session_id = session_id if session_id is not None else unique_name("interactive")
        self.current_state = UserPreferenceState(session_id=self.session_id)
        self.previous_results: list[PreviousResult] = []
        default = self.config.llm_provider
        self.set_provider(provider if provider is not None else default if default in ("rule", "mock", "gemini", "openai") else "rule")

    def set_provider(self, name: str) -> None:
        if name not in ("rule", "mock", "gemini", "openai"):
            raise ValueError("Provider must be rule, mock, gemini or openai.")
        self.provider = name
        # Empty mock inference tests orchestration, not semantic quality.
        self.mock = MockProvider(callback=lambda **kwargs: PreferenceUpdate()) if name == "mock" else None

    def reset(self) -> None:
        self.session_id = unique_name("interactive")
        self.current_state = UserPreferenceState(session_id=self.session_id)
        self.previous_results = []
        self.history = []
        self.set_provider(self.provider)

    def results(self, source: str) -> None:
        raw = DEMO_RESULTS if source == "demo" else json.loads(Path(source).read_text(encoding="utf-8"))
        if not isinstance(raw, list):
            raise ValueError("Results must be a JSON array.")
        validated = [PreviousResult.model_validate(item) for item in raw]
        if len({item.rank for item in validated}) != len(validated):
            raise ValueError("Results must have unique ranks.")
        self.previous_results = validated

    def save(self) -> Path | None:
        try:
            path = self.logger.save(self.records)
            self.save_error = None
            return path
        except OSError:
            self.save_error = "Dataset save failed; samples remain in memory. Retry /save."
            return None

    def process(self, message: str) -> dict:
        request = UserRequest(session_id=self.session_id, message=message,
                              current_state=self.current_state.model_copy(deep=True),
                              previous_results=self.previous_results)
        config = replace(self.config, llm_provider="none" if self.provider == "rule" else self.provider)
        result = process_user_request(request, self.mock, config=config)
        metadata = result.metadata.model_dump(mode="json")
        metadata["latency"] = {"rule_ms": metadata["rule_parse_ms"],
                               "slm_ms": metadata["slm_ms"],
                               "llm_ms": metadata["llm_ms"], "total_ms": metadata["total_ms"]}
        metadata["external_llm_disabled"] = self.provider not in ("gemini", "openai")
        record = {
            "schema_version": "0.2",
            "timestamp": timestamp(), "session_id": self.session_id, "message": message,
            "old_state": request.current_state.model_dump(mode="json"),
            "previous_results": [item.model_dump(mode="json") for item in request.previous_results],
            "rule_result": result.rule_result.model_dump(mode="json"),
            "preference_update": result.preference_update.model_dump(mode="json"),
            "new_state": result.state.model_dump(mode="json"),
            "provider": self.provider, "llm_called": metadata["llm_called"], "metadata": metadata,
            "correction": None, "label_status": "unreviewed",
        }
        self.current_state = result.state.model_copy(deep=True)
        self.records.append(record)
        self.history.append(record)
        self.save()
        return deepcopy(record)

    def _last(self) -> dict:
        if not self.history:
            raise ValueError("No prediction in this session yet.")
        return self.history[-1]

    def label(self, status: str) -> None:
        if status not in ("accepted", "rejected"):
            raise ValueError("Invalid label.")
        record = self._last()
        if status == "accepted" and record["correction"] is not None:
            raise ValueError("Sample has a human correction; use /correct to revise it.")
        record["label_status"] = status
        self.save()

    def correct(self, payload: str) -> None:
        record = self._last()
        correction = PreferenceUpdate.model_validate_json(payload)
        old_state = UserPreferenceState.model_validate(record["old_state"])
        rebuilt = update_state(old_state, correction, self.session_id)
        # Validate fully before mutating either the label or the current conversation.
        record["correction"] = correction.model_dump(mode="json")
        record["corrected_state"] = rebuilt.model_dump(mode="json")
        record["label_status"] = "corrected"
        self.current_state = rebuilt
        self.save()

    def export(self) -> Path:
        return self.logger.export(self.records)
