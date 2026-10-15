"""Inspect V3/V4 artifacts; optionally run one cache-only, network-blocked probe."""

import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import socket
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]

from conversation.config import ConversationConfig
from conversation.rule_parser import parse_by_rules_detailed
from conversation.slm.base import SLMInput
from conversation.slm.qwen_lora import QwenLoRAProvider

EXPECTED = {
    "v3": "f255d954a9c2ea5cc8ecf203e255355045ff179fdb415ed848fe8628a8f3974f",
    "v4": "a4711ce7a33236e31dfc3bc6ad48033fd4df9a80f40a60d11cc56ba6854aa6f1",
}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", choices=EXPECTED, required=True)
    parser.add_argument("--run-model", action="store_true", help="Run one local GPU inference; never cloud or training")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error("Choose a new output path; existing reports are preserved")

    # A fresh process per adapter releases its GPU memory before the next run.
    os.environ["LOCAL_SLM_ADAPTER_VERSION"] = args.version
    os.environ.pop("LOCAL_SLM_ADAPTER_PATH", None)
    os.environ["HF_HUB_OFFLINE"] = os.environ["TRANSFORMERS_OFFLINE"] = "1"
    def forbidden(*args, **kwargs):
        raise AssertionError("Network is forbidden in the local adapter smoke test")
    socket.socket.connect = forbidden
    socket.create_connection = forbidden

    config = ConversationConfig.from_env()
    adapter = ROOT / config.local_slm_adapter_path
    weights = adapter / "adapter_model.safetensors"
    with weights.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    if digest != EXPECTED[args.version]:
        raise ValueError("Adapter weights differ from the supplied integration handoff")
    for name in ("adapter_config.json", "tokenizer_config.json", "tokenizer.json", "chat_template.jinja"):
        if not (adapter / name).is_file():
            raise ValueError(f"Missing adapter file: {name}")
    report = {"version": args.version, "selected_path": str(adapter), "resolved_path": str(adapter.resolve()),
              "weights_sha256": digest, "base_model": config.local_slm_base_model,
              "dependencies": {name: importlib.metadata.version(name) for name in
                  ("torch", "transformers", "peft", "accelerate", "bitsandbytes")},
              "external_api_calls": 0, "model_inference": args.run_model,
              "limitation": "One authored structural probe; no model quality or production readiness claim."}
    status = 0
    if args.run_model:
        local = QwenLoRAProvider(config.local_slm_base_model, str(adapter), local_files_only=True)
        message = "Mình dị ứng sữa và đậu phộng, ưu tiên có wifi."
        result = local.parse(SLMInput(message=message, rule_result=parse_by_rules_detailed(message)))
        report.update(load_summary=local.load_summary, result=result.model_dump(mode="json"),
                      raw_response=local.last_response, load_error=local.last_load_error)
        status = 0 if not result.should_fallback and local.load_summary else 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"version": args.version, "passed": status == 0, "model_inference": args.run_model,
                      "report": str(args.output)}))
    return status


if __name__ == "__main__":
    raise SystemExit(main())
