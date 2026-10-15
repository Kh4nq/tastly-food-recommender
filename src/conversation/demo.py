"""Offline MVP examples: python -m conversation.demo [--output path.json]."""

import argparse
import json
from pathlib import Path
import sys

from common.schemas import PreferenceUpdate, PreviousResult, UserPreferenceState, UserRequest
from conversation.config import ConversationConfig
from conversation.providers import MockProvider
from conversation.service import process_user_request


def example_cases() -> list[tuple[str, UserRequest, MockProvider]]:
    """Use explicit fixtures so the demo cannot call an external provider."""
    simple = "Tìm ramen dưới 150k trong vòng 3km, không ăn cay"
    complex_message = "Muốn một chỗ vừa đẹp để đi với bạn nhưng không quá ồn."
    partial = "Tìm ramen dưới 150k, quán đẹp nhưng đừng quá ồn"
    feedback = "Cái thứ hai ổn nhưng hơi xa, tìm giống nó mà gần hơn"
    results = [PreviousResult(rank=1, restaurant_id="R001", restaurant_name="A"),
               PreviousResult(rank=2, restaurant_id="R002", restaurant_name="B")]
    return [
        ("Demo 1 — rule only", UserRequest(session_id="S001", message=simple), MockProvider()),
        ("Demo 2 — complex mock", UserRequest(session_id="S002", message=complex_message),
         MockProvider({complex_message: PreferenceUpdate(
             add_semantic_preferences=["beautiful ambience", "quiet"],
             add_soft_preferences={"occasion": "friends"})})),
        ("A — simple", UserRequest(session_id="A", message="Tìm ramen dưới 150k trong 2km"), MockProvider()),
        ("B — partial / hybrid", UserRequest(session_id="B", message=partial),
         MockProvider({partial: PreferenceUpdate(add_semantic_preferences=["quiet"])})),
        ("C — removal", UserRequest(session_id="C", message="Không cần quán đẹp nữa",
            current_state=UserPreferenceState(session_id="C", semantic_preferences=["beautiful ambience"])),
         MockProvider()),
        ("Demo 3 / D — feedback", UserRequest(session_id="D", message=feedback, previous_results=results),
         MockProvider({feedback: PreferenceUpdate(
             references=[{"rank": 2, "mention": "cái thứ hai", "sentiment": "positive", "similar_to": True}],
             relative_updates={"distance": "decrease"})})),
    ]


def run_examples() -> list[dict]:
    records = []
    for label, request, provider in example_cases():
        result = process_user_request(request, provider, config=ConversationConfig())
        records.append({
            "example": label, "UserRequest": request.model_dump(mode="json"),
            "RuleParseResult": result.rule_result.model_dump(mode="json"),
            "LLM called?": result.metadata.llm_called,
            "mock_call_count": provider.call_count, "external_llm_calls": 0,
            "PreferenceUpdate": result.preference_update.model_dump(mode="json"),
            "UserPreferenceState": result.state.model_dump(mode="json"),
            "metadata": result.metadata.model_dump(mode="json"),
        })
    return records


def main() -> None:
    # Windows redirected stdout can default to cp1252, which cannot print Vietnamese.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Also save the full JSON traces")
    args = parser.parse_args()
    payload = json.dumps(run_examples(), ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
    print(payload)


if __name__ == "__main__":
    main()
