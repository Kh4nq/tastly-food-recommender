"""Offline programmable provider; each instance owns its call counter."""

from collections.abc import Callable, Mapping

from common.schemas import PreferenceUpdate, PreviousResult, UserPreferenceState
from conversation.providers.base import ProviderError
from conversation.providers.structured import StructuredPreferenceUpdate, llm_output_to_preference_update


class MockProvider:
    name = "mock"

    def __init__(self, responses: Mapping[str, PreferenceUpdate | StructuredPreferenceUpdate] | None = None,
                 callback: Callable[..., PreferenceUpdate | StructuredPreferenceUpdate] | None = None) -> None:
        self.responses = {k: v.model_copy(deep=True) for k, v in (responses or {}).items()}
        self.callback = callback
        self.call_count = 0

    def parse_preference(
        self, *, message: str, current_state: UserPreferenceState | None,
        previous_results: list[PreviousResult], rule_update: PreferenceUpdate | None = None,
    ) -> PreferenceUpdate:
        self.call_count += 1
        if self.callback is not None:
            output = self.callback(message=message, current_state=current_state,
                                   previous_results=previous_results, rule_update=rule_update)
        else:
            if message not in self.responses:
                raise ProviderError("No mock response configured for this message")
            output = self.responses[message].model_copy(deep=True)
        if isinstance(output, StructuredPreferenceUpdate):
            return llm_output_to_preference_update(output)
        return output
