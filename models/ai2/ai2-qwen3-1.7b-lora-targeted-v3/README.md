---
base_model: Qwen/Qwen3-1.7B
library_name: peft
pipeline_tag: text-generation
---

# Optional Qwen V3 adapter configuration

This public directory retains the existing LoRA configuration and chat template. It does **not** contain adapter weights or a tokenizer bundle and uses no Git LFS pointers. OpenRouter website setup does not require these files.

Obtain the matching V3 adapter bundle separately from its maintainers. No automatic public download or redistribution license is supplied here. Review the upstream Qwen model license and the adapter's provenance before use. The AI1 demo ZIP contains data only, not these model files.

For the standard V3 layout supply `adapter_model.safetensors`, `tokenizer.json`, `tokenizer_config.json`, `special_tokens_map.json` and any other tokenizer dependencies alongside the included `adapter_config.json` and `chat_template.jinja`. Do not substitute a different adapter under the same configuration. Retain the supplied bundle's license/copyright notices locally.

Install the optional SLM dependencies, obtain/cache the `Qwen/Qwen3-1.7B` base model and validate NVIDIA/CUDA prerequisites before explicitly enabling `LOCAL_SLM_ENABLED=true`. `LOCAL_SLM_ADAPTER_PATH` can select another complete local bundle. The cloud-chain fallback has its own `LOCAL_SLM_FALLBACK_ADAPTER_PATH`; point it to a matching supplied adapter rather than relying on the undistributed experimental default.

`python scripts/preflight.py --require-local-slm` checks the standard V3 layout and CUDA dependencies without inference. Leave `LOCAL_SLM_LOCAL_FILES_ONLY=true` when loading entirely from local files. See the root README for setup and limitations. No trained-model quality claim is made.
