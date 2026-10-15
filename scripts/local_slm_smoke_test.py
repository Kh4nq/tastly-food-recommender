"""Opt-in real Qwen diagnostic. No model is loaded unless --run is supplied."""
import argparse
import json
from pathlib import Path
import sys
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from common.schemas import UserRequest
from conversation.config import ConversationConfig
from conversation.rule_parser import parse_by_rules_detailed
from conversation.service import process_user_request
from conversation.slm.base import SLMInput
from conversation.slm.router import create_slm_provider


# Authored diagnostics, independent of benchmarks and sealed evaluation data.
CASES = {
    "food": {"message": "Muốn ăn bánh cuốn, không phải chọn ẩm thực Trung Quốc."},
    "cuisine": {"message": "Muốn thử ẩm thực Mexico, chưa chọn món cụ thể."},
    "budget_distance": {"message": "Tìm ramen dưới 120k trong vòng 2km."},
    "soft_facility": {"message": "Có wifi thì tốt, không bắt buộc."},
    "hard_facility": {"message": "Quán bắt buộc phải có máy lạnh."},
    "semantic": {"message": "Cần không gian dễ trò chuyện, đừng quá ồn."},
    "negative": {"message": "Mình không thích món quá ngọt."},
    "correction": {"message": "Bỏ giới hạn ngân sách, đổi món sang bánh cuốn.",
                   "current_state": {"session_id": "smoke", "food": ["ramen"],
                                     "hard_constraints": {"budget_max": 120000}}},
    "relative": {"message": "Tìm gần hơn, đắt hơn chút cũng được.",
                 "current_state": {"session_id": "smoke",
                                   "hard_constraints": {"budget_max": 120000, "max_distance_km": 3}}},
    "reference": {"message": "Quán thứ hai hợp ý, tìm giống nó mà gần hơn.",
                  "previous_results": [{"rank": 1, "restaurant_id": "smoke-A", "restaurant_name": "Mẫu A"},
                                       {"rank": 2, "restaurant_id": "smoke-B", "restaurant_name": "Mẫu B"}]},
    "complex": {"message": "Nhóm 3 người đi xe máy, muốn món Thái dưới 180k, bắt buộc có chỗ gửi xe, wifi thì tốt, không thích cay và muốn không gian dễ nói chuyện."},
}


def show(label, value):
    print(label)
    print(json.dumps(value, ensure_ascii=False, indent=2))


def main(argv=None):
    defaults = ConversationConfig.from_env()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", help="Load real weights; may download the base model")
    parser.add_argument("--case", choices=list(CASES), help="Default: all diagnostic cases")
    parser.add_argument("--base-model", default=defaults.local_slm_base_model)
    parser.add_argument("--adapter-path", default=defaults.local_slm_adapter_path)
    parser.add_argument("--max-new-tokens", type=int, default=defaults.local_slm_max_new_tokens)
    args = parser.parse_args(argv)
    if not args.run:
        parser.error("Real inference requires explicit --run")
    config = ConversationConfig(
        local_slm_enabled=True, local_slm_backend="qwen_lora",
        local_slm_base_model=args.base_model, local_slm_adapter_path=args.adapter_path,
        local_slm_max_new_tokens=args.max_new_tokens, llm_provider="none", log_enabled=False,
    )
    provider = create_slm_provider(config)
    failed = False
    for name in ([args.case] if args.case else CASES):
        request = UserRequest(session_id="smoke", **CASES[name])
        show("CASE", name)
        show("INPUT", request.message)
        show("STATE", request.current_state.model_dump(mode="json") if request.current_state else None)
        show("PREVIOUS RESULTS", [r.model_dump(mode="json") for r in request.previous_results])
        # Diagnose the model on every case, including inputs rules can resolve.
        # Replay its result into the unchanged pipeline without a second generation.
        raw = provider.parse(SLMInput(message=request.message,
            current_state=request.current_state, previous_results=request.previous_results,
            rule_result=parse_by_rules_detailed(request.message)))
        show("SLM LOAD PLACEMENT", provider.load_summary)
        if provider.last_gpu_load_error:
            print("SLM GPU LOAD ERROR (CPU fallback attempted)")
            print(provider.last_gpu_load_error)
        if provider.last_load_error:
            print("SLM LOAD ERROR")
            print(provider.last_load_error)
        print("RAW SLM UPDATE")
        print(provider.last_response or "<no generated response>")
        result = process_user_request(request, config=config,
                                      slm_provider=SimpleNamespace(parse=lambda _: raw))
        show("NORMALIZED UPDATE", result.preference_update.model_dump(mode="json"))
        show("UPDATED STATE", result.state.model_dump(mode="json"))
        show("SLM STATUS", raw.metadata)
        show("PIPELINE STATUS", result.metadata.model_dump(mode="json"))
        failed |= raw.should_fallback or result.metadata.partial_result
    return int(failed)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
