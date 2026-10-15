"""Safe fallback for the frozen backend."""
from conversation.slm.base import SLMInput, SLMParseResult
from common.schemas import PreferenceUpdate


class DisabledSLMProvider:
    def parse(self, request: SLMInput) -> SLMParseResult:
        return SLMParseResult(update=PreferenceUpdate(), confidence=0, should_fallback=True,
                              metadata={"error": "disabled_backend"})
