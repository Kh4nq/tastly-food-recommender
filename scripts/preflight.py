"""Read-only local setup checks. No inference, providers, downloads or benchmarks."""
from __future__ import annotations

import argparse
import importlib
import json
import os
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
COUNTS = {"restaurants": 26025, "dishes": 4000, "menu_items": 336167}
AI1_FILES = tuple(f"data/processed/{name}.parquet" for name in COUNTS) + tuple(
    f"data/embeddings/{name}" for name in (
        "restaurants_vectors.npy", "restaurants_ids.csv", "dishes_vectors.npy",
        "dishes_ids.csv", "menu_to_vectors.parquet", "metadata.json",
    )
)
ADAPTER = "models/ai2/ai2-qwen3-1.7b-lora-targeted-v3"
ADAPTER_FILES = ("adapter_config.json", "adapter_model.safetensors", "tokenizer.json",
                 "tokenizer_config.json", "special_tokens_map.json", "chat_template.jinja")
AI1_ACQUISITION = (
    "Ask the AI1 owner for ai1-demo-data.zip (demo) or ai1-v3-artifacts.zip (legacy). Place the ZIP under data/ "
    'or run: .\\setup.ps1 -AI1ArtifactZip "C:\\path\\to\\ai1-v3-artifacts.zip"'
)


def materialized(path: Path) -> bool:
    if not path.is_file() or path.stat().st_size == 0:
        return False
    with path.open("rb") as stream:
        return not stream.read(128).startswith(b"version https://git-lfs.github.com/spec/v1")


def validate_ai1(root: Path = ROOT) -> None:
    """Use the existing loader for hashes, vector shapes, IDs and menu equality."""
    missing = [name for name in AI1_FILES if not materialized(root / name)]
    if missing:
        raise ValueError("Missing/empty/unmaterialized files: " + ", ".join(missing) + ". " + AI1_ACQUISITION)
    metadata = json.loads((root / "data/embeddings/metadata.json").read_text(encoding="utf-8"))
    if metadata.get("dataset_version") != "v3-menu":
        raise ValueError("AI1 dataset_version must be v3-menu. " + AI1_ACQUISITION)
    for name in COUNTS:
        digest = metadata.get("source_files", {}).get(f"{name}.parquet", "")
        if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise ValueError(f"Missing/invalid source SHA256: {name}.parquet")
    expected = COUNTS
    if metadata.get("usage") == "synthetic_demo":
        required = ("ai1_dataset_card.json", "ai1_profile_manifest.json", "restaurant_profiles.parquet")
        for name in required:
            if not materialized(root / "data/processed" / name):
                raise ValueError(f"Incomplete demo release: {name}")
        profile_manifest = json.loads((root / "data/processed/ai1_profile_manifest.json").read_text(encoding="utf-8"))
        if not isinstance(profile_manifest, dict) or profile_manifest.get("usage") != "synthetic_demo":
            raise ValueError("Demo/profile usage mismatch")
        card = json.loads((root / "data/processed/ai1_dataset_card.json").read_text(encoding="utf-8"))
        if not isinstance(card, dict):
            raise ValueError("Demo dataset card must be an object")
        expected = {"restaurants": metadata["restaurants"]["rows"],
                    "dishes": metadata["dishes"]["rows"],
                    "menu_items": metadata["menu_mapping"]["rows"]}
        if any(type(v) is not int or v <= 0 for v in expected.values()):
            raise ValueError("Demo metadata counts must be positive integers")
        for name, count in expected.items():
            if card.get("menus" if name == "menu_items" else name) != count:
                raise ValueError(f"Demo dataset card count mismatch: {name}")
    from retrieval.retriever import Retriever

    engine = Retriever(root / "data/processed", root / "data/embeddings")
    actual = {"restaurants": len(engine.restaurants), "dishes": len(engine.dishes),
              "menu_items": len(engine.menus)}
    if actual != expected or len(engine.menu_map) != expected["menu_items"]:
        raise ValueError(f"Unexpected V3 counts: {actual}; menu map={len(engine.menu_map)}")
    if metadata["menu_mapping"]["rows"] != expected["menu_items"]:
        raise ValueError("Metadata menu count differs from validated V3 count")


def cached_model(model_id: str) -> bool:
    """Inspect cache metadata only; never ask Hugging Face to download a file."""
    from huggingface_hub import scan_cache_dir

    for repo in scan_cache_dir().repos:
        if repo.repo_id == model_id and repo.repo_type == "model":
            # Presence is not a guarantee that every shard is cached.
            return True
    return False


def torch_status() -> dict:
    """Inspect the installed build and exercise CUDA; never install or download."""
    status = {"state": "unavailable", "version": None, "cuda": None,
              "available": False, "detail": ""}
    try:
        import torch
        status.update(version=torch.__version__, cuda=torch.version.cuda)
        if torch.version.cuda is None:
            status.update(state="cpu", detail="CPU-only build detected")
            return status
        status["available"] = bool(torch.cuda.is_available())
        if not status["available"]:
            raise RuntimeError("CUDA-enabled build installed, but torch.cuda.is_available() is False; check the NVIDIA driver/runtime")
        if (torch.ones(1, device="cuda") + 1).item() != 2:
            raise RuntimeError("CUDA tensor operation failed")
        status.update(state="ready", detail=f"{torch.cuda.get_device_name(0)}; torch={torch.__version__}; CUDA={torch.version.cuda}")
    except ModuleNotFoundError as exc:
        status.update(state="missing" if exc.name == "torch" else "unavailable", detail=str(exc))
    except Exception as exc:
        status["detail"] = str(exc)
    return status


def gemini_status(root: Path) -> str:
    """Check CLI configuration presence without printing secrets or calling a provider."""
    from conversation.environment import load_env

    saved = os.environ.copy()
    try:
        load_env(root / ".env")
        if not os.environ.get("GEMINI_API_KEY", "").strip():
            return "NEEDS API KEY"
        if not os.environ.get("GEMINI_MODEL", "").strip():
            return "NEEDS MODEL"
        return "CONFIGURED"
    finally:
        # This read-only check must not enable providers in its caller.
        for key in os.environ.keys() - saved.keys():
            del os.environ[key]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--require-local-slm", action="store_true")
    parser.add_argument("--ai1-only", action="store_true")
    parser.add_argument("--torch-json", action="store_true", help="Inspect only Torch/CUDA for setup")
    parser.add_argument("--report-json", type=Path, help="Write capability statuses only (no credentials)")
    args = parser.parse_args(argv)
    if args.torch_json:
        print(json.dumps(torch_status()))
        return 0
    root = args.root.resolve()
    failures = []

    def check(label, action, required=True):
        try:
            detail = action()
            print(f"OK   {label}" + (f": {detail}" if detail else ""))
            return True
        except Exception as exc:
            print(f"{'FAIL' if required else 'WARN'} {label}: {exc}")
            if required:
                failures.append(label)
            return False

    def require(condition, message):
        if not condition:
            raise ValueError(message)

    if args.ai1_only:
        check("AI1 V3 hashes, mapping and counts", lambda: validate_ai1(root))
        return int(bool(failures))
    check("Python 3.11", lambda: require(sys.version_info[:2] == (3, 11), "Use Python 3.11 for the team environment"))
    for name in ("common", "conversation", "retrieval", "ranking", "pipeline", "database",
                 "pytest", "pydantic", "numpy", "pandas", "pyarrow", "sentence_transformers",
                 "catboost", "google.genai", "psycopg", "psycopg_pool"):
        check(f"import {name}", lambda name=name: importlib.import_module(name) and None)
    core_ready = not failures
    check(".env", lambda: require((root / ".env").is_file(), "Copy .env.example to .env; configure keys yourself"))
    ai1_ready = check("AI1 V3 hashes, mapping and counts", lambda: validate_ai1(root))
    ai3_ready = check("AI3 production model", lambda: require(materialized(root / "models/ranker/catboost_yetirank.cbm"),
          "Restore models/ranker/catboost_yetirank.cbm from Git; do not retrain"))

    def adapter():
        missing = [name for name in ADAPTER_FILES if not materialized(root / ADAPTER / name)]
        require(not missing, f"Missing optional adapter files: {missing}. Obtain a matching external bundle; see the adapter README.")
        config = json.loads((root / ADAPTER / "adapter_config.json").read_text(encoding="utf-8"))
        require(config.get("base_model_name_or_path") == "Qwen/Qwen3-1.7B", "Unexpected adapter base model")

    local_checks = [check("AI2 V3 adapter", adapter, args.require_local_slm)]
    for name in ("torch", "transformers", "peft", "accelerate", "bitsandbytes"):
        local_checks.append(check(f"Local SLM import {name}", lambda name=name: importlib.import_module(name) and None,
                                  args.require_local_slm))

    def cuda():
        status = torch_status()
        action = " Action: install CUDA-enabled PyTorch" if status["state"] in {"cpu", "missing"} else ""
        require(status["state"] == "ready", status["detail"] + action)
        return status["detail"]

    local_checks.append(check("PyTorch CUDA operation", cuda, args.require_local_slm))
    print("INFO Local SLM " + ("prerequisites available; inference was not tested." if all(local_checks)
                              else "unavailable until warnings above are resolved; Gemini fallback remains usable when configured."))
    print("INFO Keep LOCAL_SLM_ENABLED=false until explicitly enabled; recommend AI1_EMBEDDING_DEVICE=cpu alongside Qwen.")
    for model in ("Qwen/Qwen3-1.7B", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"):
        check(f"cache entry {model}", lambda model=model: require(cached_model(model),
              "No local cache entry; enabled inference may download this model. Cache presence does not prove completeness."), False)
    frontend_status = "SKIPPED"
    if (root / "src/frontend/package.json").is_file():
        frontend_ready = check("optional frontend", lambda: require(bool(shutil.which("node")) and bool(shutil.which("npm"))
              and (root / "src/frontend/node_modules").is_dir(), "Install Node/npm, then npm ci in src/frontend"), False)
        frontend_status = "READY" if frontend_ready else "UNAVAILABLE"
    else:
        print("INFO Frontend absent; skipped")
    print("INFO PostgreSQL is optional; setup.ps1 -WithDatabase checks Docker and the Compose healthcheck.")
    gemini = gemini_status(root)
    print(f"INFO Gemini fallback: {gemini}; configuration presence only, no API call. Core modules require process variables.")
    if args.report_json:
        args.report_json.write_text(json.dumps({
            "Core Python environment": "READY" if core_ready else "FAILED",
            "AI1 artifacts": "READY" if ai1_ready else "MISSING",
            "AI3 CatBoost model": "READY" if ai3_ready else "MISSING",
            "Local SLM": "READY" if all(local_checks) else "UNAVAILABLE",
            "Gemini fallback": gemini,
            "Frontend": frontend_status,
        }), encoding="utf-8")
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(main())
