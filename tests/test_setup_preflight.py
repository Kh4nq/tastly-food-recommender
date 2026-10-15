"""Setup checks use synthetic files; never production artifacts or providers."""
import importlib.util
import hashlib
import json
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import zipfile
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest

from scripts import preflight
from scripts import setup_artifacts
from retrieval.embedder import build_embeddings


def test_missing_artifacts_are_listed_without_loading_models(tmp_path):
    with pytest.raises(ValueError) as error:
        preflight.validate_ai1(tmp_path)
    for name in preflight.AI1_FILES:
        assert name in str(error.value)
    assert "Ask the AI1 owner" in str(error.value)


def test_lfs_pointer_is_not_a_materialized_artifact(tmp_path):
    path = tmp_path / "model"
    path.write_bytes(b"version https://git-lfs.github.com/spec/v1\noid sha256:123\n")
    assert not preflight.materialized(path)
    path.write_bytes(b"materialized fixture")
    assert preflight.materialized(path)


@pytest.fixture
def package(tmp_path, monkeypatch):
    source = tmp_path / "data/processed"
    output = tmp_path / "data/embeddings"
    source.mkdir(parents=True)
    pd.DataFrame([{"food_place_id": "r1", "name": "A"}]).to_parquet(source / "restaurants.parquet")
    pd.DataFrame([{"dish_id": "d1", "dish_name": "B"}]).to_parquet(source / "dishes.parquet")
    pd.DataFrame([{"menu_item_id": "m1", "food_place_id": "r1", "dish_id": "d1"}]).to_parquet(source / "menu_items.parquet")

    class Encoder:
        def encode(self, texts, **kwargs):
            return np.array([[1.0, 0.0] for _ in texts], dtype=np.float32)

    metadata = build_embeddings(source, output, model=Encoder())
    metadata["dataset_version"] = "v3-menu"
    (output / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
    monkeypatch.setattr(preflight, "COUNTS", dict.fromkeys(preflight.COUNTS, 1))
    return tmp_path


def test_valid_synthetic_package_passes_without_inference(package):
    preflight.validate_ai1(package)


@pytest.mark.parametrize("relative", ["data/processed/dishes.parquet", "data/embeddings/dishes_vectors.npy"])
def test_corruption_is_rejected_by_existing_loader(package, relative):
    path = package / relative
    if path.suffix == ".parquet":
        frame = pd.read_parquet(path)
        frame["dish_name"] = "changed fixture"
        frame.to_parquet(path)
    else:
        with path.open("ab") as stream:
            stream.write(b"corrupt")
    with pytest.raises(ValueError, match="differs|checksum"):
        preflight.validate_ai1(package)


@pytest.mark.parametrize("change,match", [
    ({"dataset_version": "v2-original-ids"}, "v3-menu"),
    ({"source_files": {}}, "source SHA256"),
    ({"menu_mapping": {"rows": 2}}, "menu count"),
])
def test_incomplete_or_stale_metadata_is_rejected(package, change, match):
    path = package / "data/embeddings/metadata.json"
    metadata = json.loads(path.read_text())
    for key, value in change.items():
        if isinstance(value, dict) and value:
            metadata[key].update(value)
        else:
            metadata[key] = value
    path.write_text(json.dumps(metadata))
    with pytest.raises(ValueError, match=match):
        preflight.validate_ai1(package)


def test_setup_seed_preserves_existing_rows(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://unused")
    spec = importlib.util.spec_from_file_location("setup_seed_test", preflight.ROOT / "scripts/seed_database.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    connection = MagicMock()
    connection.cursor.return_value.__enter__.return_value.fetchone.return_value = (True,)
    connect = MagicMock()
    connect.return_value.__enter__.return_value = connection
    monkeypatch.setattr(module.psycopg, "connect", connect)
    monkeypatch.setattr(module, "expected_row_counts", lambda: dict.fromkeys(module.TABLES, 1))
    monkeypatch.setattr(module, "load_table", lambda *args: pytest.fail("Existing data must not be replaced"))
    module.main(if_empty=True)
    statements = [call.args[0] for call in connection.cursor.return_value.__enter__.return_value.execute.call_args_list]
    assert any("LOCK TABLE" in sql for sql in statements)
    assert not any("TRUNCATE" in sql for sql in statements)


def test_seed_accepts_new_release_counts_and_rejects_bad_card(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://unused")
    spec = importlib.util.spec_from_file_location("setup_seed_counts", preflight.ROOT / "scripts/seed_database.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for table, count in (("restaurants", 2), ("dishes", 3), ("menu_items", 4)):
        pd.DataFrame({"id": range(count)}).to_parquet(tmp_path / f"{table}.parquet")
    card = tmp_path / "ai1_dataset_card.json"
    card.write_text(json.dumps({"restaurants": 2, "dishes": 3, "menus": 4}))
    assert module.expected_row_counts(tmp_path) == {"restaurants": 2, "dishes": 3, "menu_items": 4}
    card.write_text(json.dumps({"restaurants": 2, "dishes": 3, "menus": 5}))
    with pytest.raises(ValueError, match="count mismatch"):
        module.expected_row_counts(tmp_path)


@pytest.mark.parametrize("key,model,expected", [
    ("", "", "NEEDS API KEY"),
    ("fixture-secret", "", "NEEDS MODEL"),
    ("fixture-secret", "fixture-model", "CONFIGURED"),
])
def test_gemini_configuration_is_read_only(tmp_path, monkeypatch, key, model, expected):
    import os

    (tmp_path / ".env").write_text(f"GEMINI_API_KEY={key}\nGEMINI_MODEL={model}\n")
    assert preflight.gemini_status(tmp_path) == expected
    assert "GEMINI_API_KEY" not in os.environ
    monkeypatch.setenv("GEMINI_API_KEY", "")
    assert preflight.gemini_status(tmp_path) == "NEEDS API KEY"


@pytest.mark.parametrize("cuda_available,operation_fails,slm_missing,ready", [
    (False, False, False, False),
    (True, True, False, False),
    (True, False, True, False),
    (True, False, False, True),
])
def test_preflight_capabilities_require_working_cuda(
    tmp_path, monkeypatch, capsys, cuda_available, operation_fails, slm_missing, ready
):
    (tmp_path / ".env").write_text("")
    config = tmp_path / preflight.ADAPTER / "adapter_config.json"
    config.parent.mkdir(parents=True)
    config.write_text('{"base_model_name_or_path": "Qwen/Qwen3-1.7B"}')
    monkeypatch.setattr(preflight, "validate_ai1", lambda root: None)
    monkeypatch.setattr(preflight, "materialized", lambda path: True)
    monkeypatch.setattr(preflight, "cached_model", lambda model: True)
    monkeypatch.setattr(preflight.sys, "version_info", (3, 11))
    tensor = MagicMock()
    tensor.__add__.return_value.item.return_value = 2
    torch = SimpleNamespace(
        cuda=SimpleNamespace(is_available=lambda: cuda_available, get_device_name=lambda i: "fixture GPU"),
        ones=MagicMock(return_value=tensor, side_effect=RuntimeError("incompatible CUDA") if operation_fails else None),
        __version__="fixture", version=SimpleNamespace(cuda="fixture"),
    )
    monkeypatch.setitem(sys.modules, "torch", torch)
    imported = []

    def fake_import(name):
        imported.append(name)
        if name == "peft" and slm_missing:
            raise ImportError("No SLM stack")
        return object()

    monkeypatch.setattr(preflight.importlib, "import_module", fake_import)
    report = tmp_path / "report.json"
    assert preflight.main(["--root", str(tmp_path), "--report-json", str(report)]) == 0
    statuses = json.loads(report.read_text())
    assert statuses["Core Python environment"] == "READY"
    assert statuses["Local SLM"] == ("READY" if ready else "UNAVAILABLE")
    assert statuses["Gemini fallback"] == "NEEDS API KEY"
    assert "openai" not in imported
    assert torch.ones.call_count == int(cuda_available)
    assert preflight.main(["--root", str(tmp_path), "--require-local-slm"]) == int(not ready)
    assert "OpenAI" not in capsys.readouterr().out


@pytest.mark.parametrize("scenario", [
    "no_gpu", "query_failed", "empty_query", "cuda_missing", "gpu_ready",
    "slm_install_failed", "core_failed", "artifacts_missing", "frontend_failed",
    "frontend_required_failed", "database", "verify_only",
    "cpu_torch", "missing_torch", "verify_cpu", "torch_install_failed",
    "torch_validation_failed", "artifact_zip",
])
def test_powershell_setup_paths_are_offline_and_report_capabilities(tmp_path, scenario):
    shell = shutil.which("powershell") or shutil.which("pwsh")
    if not shell or sys.platform != "win32":
        pytest.skip("Windows PowerShell setup harness")
    shutil.copyfile(preflight.ROOT / "setup.ps1", tmp_path / "setup.ps1")
    (tmp_path / ".env.example").write_text("LLM_PROVIDER=gemini\nLOCAL_SLM_ENABLED=false\n")
    (tmp_path / ".env").write_text("preserve this configuration\n")
    venv = tmp_path / ".venv"
    (venv / "Scripts").mkdir(parents=True)
    (venv / "Scripts/python.exe").touch()
    (venv / "pyvenv.cfg").touch()
    (venv / ".mlai-setup").write_text(str(tmp_path))
    frontend = tmp_path / "src/frontend"
    frontend.mkdir(parents=True)
    (frontend / "package.json").write_text("{}")
    (frontend / "package-lock.json").write_text("{}")
    # Every external command is replaced in this child PowerShell process.
    # Run the actual script twice to cover reruns and preserved configuration.
    harness = r'''
$ErrorActionPreference = 'Stop'
$scenario = '__SCENARIO__'
$global:LASTEXITCODE = 0
$global:cudaInstalled = $false
function Get-Command {
    param($Name, $ErrorAction)
    if ($Name -eq 'git') { return $null }
    if ($Name -eq 'nvidia-smi' -and $scenario -in @('no_gpu', 'verify_only')) { return $null }
    Microsoft.PowerShell.Core\Get-Command $Name -ErrorAction SilentlyContinue
}
function py { $global:LASTEXITCODE = 0 }
function nvidia-smi {
    Write-Host 'EVENT NVIDIA query'
    $global:LASTEXITCODE = 0
    if ($scenario -eq 'query_failed') { $global:LASTEXITCODE = 1; return }
    if ($scenario -ne 'empty_query') { 'Fixture NVIDIA' }
}
function node {}
function npm.cmd {
    Write-Host "EVENT npm $args"
    $global:LASTEXITCODE = 0
    if ($scenario -in @('frontend_failed', 'frontend_required_failed')) { $global:LASTEXITCODE = 1 }
}
function docker {
    Write-Host "EVENT docker $args"
    $global:LASTEXITCODE = 0
    if ('config' -in $args) {
        '{"services":{"postgres":{"environment":{"POSTGRES_USER":"fixture","POSTGRES_PASSWORD":"fixture","POSTGRES_DB":"fixture"}}}}'
    }
    if ('port' -in $args) { '127.0.0.1:5432' }
}
Set-Item -LiteralPath "Function:$(Join-Path $PSScriptRoot '.venv/Scripts/python.exe')" -Value {
    Write-Host "EVENT python $args"
    $global:LASTEXITCODE = 0
    if ('--torch-json' -in $args) {
        $state = 'ready'; $detail = 'working CUDA'
        if ($scenario -eq 'cuda_missing' -or ($scenario -eq 'torch_validation_failed' -and $global:cudaInstalled)) {
            $state = 'unavailable'; $detail = 'CUDA operation failed'
        } elseif (-not $global:cudaInstalled -and $scenario -in @('cpu_torch', 'verify_cpu', 'torch_install_failed', 'torch_validation_failed')) {
            $state = 'cpu'; $detail = 'CPU-only build detected'
        } elseif (-not $global:cudaInstalled -and $scenario -eq 'missing_torch') {
            $state = 'missing'; $detail = 'No module named torch'
        }
        @{state=$state; detail=$detail} | ConvertTo-Json -Compress
        return
    }
    if ('torch==2.14.1+cu130' -in $args) {
        if ($scenario -eq 'torch_install_failed') {
            Write-Host 'original pip wheel failure'; $global:LASTEXITCODE = 1
        } else { $global:cudaInstalled = $true }
    }
    if ('scripts.setup_artifacts' -in $args -and $scenario -eq 'artifact_zip') {
        if ($args[-1] -ne 'C:\Downloads with spaces\ai1-v3-artifacts.zip') { throw 'ZIP path was split' }
    }
    if ('.[slm]' -in $args -and $scenario -eq 'slm_install_failed') { $global:LASTEXITCODE = 1 }
    if ('check' -in $args -and $scenario -eq 'core_failed') { $global:LASTEXITCODE = 1 }
    if ('scripts/preflight.py' -in $args) {
        $statuses = @{
            'Core Python environment' = 'READY'; 'AI1 artifacts' = 'READY';
            'AI3 CatBoost model' = 'READY'; 'Local SLM' = 'READY';
            'Gemini fallback' = 'NEEDS API KEY'; 'Frontend' = 'UNAVAILABLE'
        }
        if ($scenario -in @('cuda_missing', 'verify_cpu')) { $statuses['Local SLM'] = 'UNAVAILABLE' }
        if ($scenario -eq 'artifacts_missing') {
            $statuses['AI1 artifacts'] = 'MISSING'; $global:LASTEXITCODE = 1
        }
        $statuses | ConvertTo-Json | Set-Content -LiteralPath $args[-1]
    }
}
if ($scenario -eq 'database') {
    New-Item -ItemType Directory -Path (Join-Path $PSScriptRoot 'data/processed') | Out-Null
    foreach ($name in @('restaurants', 'dishes', 'menu_items')) {
        New-Item -ItemType File -Path (Join-Path $PSScriptRoot "data/processed/$name.parquet") | Out-Null
    }
}
$options = @{}
if ($scenario -eq 'database') { $options.WithDatabase = $true }
if ($scenario -eq 'frontend_required_failed') { $options.WithFrontend = $true }
if ($scenario -in @('verify_only', 'verify_cpu')) { $options.VerifyOnly = $true; $options.SkipFrontend = $true }
if ($scenario -in @('artifact_zip', 'verify_cpu')) { $options.AI1ArtifactZip = 'C:\Downloads with spaces\ai1-v3-artifacts.zip' }
$failed = $false
foreach ($attempt in 1..2) {
    try { & (Join-Path $PSScriptRoot 'setup.ps1') @options }
    catch { Write-Host "SETUP ERROR: $_"; $failed = $true }
}
if ($failed) { exit 1 }
'''.replace("__SCENARIO__", scenario)
    script = tmp_path / "harness.ps1"
    script.write_text(harness)
    result = subprocess.run([shell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
                            capture_output=True, text=True, timeout=60)
    output = result.stdout + result.stderr
    assert result.returncode == int(scenario in {"core_failed", "artifacts_missing", "frontend_required_failed",
                                               "torch_install_failed", "torch_validation_failed"}), output
    assert output.count("Setup capability summary") == 2, output
    assert "Gemini fallback: NEEDS API KEY" in output
    assert "openai" not in output.lower()
    assert (tmp_path / ".env").read_text() == "preserve this configuration\n"
    cuda_installs = output.count("EVENT python -m pip install torch==2.14.1+cu130 --index-url https://download.pytorch.org/whl/cu130")
    if scenario in {"torch_install_failed", "torch_validation_failed"}:
        assert "original pip wheel failure" in output if scenario == "torch_install_failed" else "CUDA Torch validation failed" in output
        assert cuda_installs == (2 if scenario == "torch_install_failed" else 1)
        return
    assert cuda_installs == int(scenario in {"cpu_torch", "missing_torch"}), output
    if scenario in {"cpu_torch", "missing_torch"}:
        assert output.index("pip install torch==") < output.index("pip install -e")
    if scenario == "verify_cpu":
        assert "PyTorch: CPU-only build detected" in output
        assert "Action: install CUDA-enabled PyTorch" in output
    if scenario in {"verify_only", "verify_cpu"}:
        assert "pip install" not in output
        assert "EVENT npm" not in output
        assert "scripts.setup_artifacts" not in output
    else:
        assert "pip install -e .[test,ai1,ai3,gemini,db,backend]" in output
        assert "EVENT npm ci" in output
        assert "EVENT python -m scripts.setup_artifacts" in output
    if scenario in {"no_gpu", "query_failed", "empty_query", "verify_only", "verify_cpu"}:
        assert ".[slm]" not in output
    else:
        assert output.index("EVENT NVIDIA query") < output.index(".[slm]")
    unavailable = scenario in {"no_gpu", "query_failed", "empty_query", "verify_only", "verify_cpu", "cuda_missing", "slm_install_failed"}
    assert f"Local SLM: {'UNAVAILABLE' if unavailable else 'READY'}" in output
    assert f"Core Python environment: {'FAILED' if scenario == 'core_failed' else 'READY'}" in output
    if scenario == "artifacts_missing":
        assert "AI1 artifacts: MISSING" in output
    if scenario == "database":
        assert "scripts/seed_database.py --if-empty" in output
        assert "PostgreSQL: READY" in output
    else:
        assert "EVENT docker" not in output
        assert "PostgreSQL: SKIPPED" in output
    expected_frontend = "SKIPPED" if scenario in {"verify_only", "verify_cpu"} else (
        "UNAVAILABLE" if scenario in {"frontend_failed", "frontend_required_failed"} else "READY")
    assert f"Frontend: {expected_frontend}" in output


def make_artifact_zip(package, archive):
    archive.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive, "w") as bundle:
        for directory in ("processed", "embeddings"):
            for path in (package / "data" / directory).iterdir():
                bundle.write(path, f"{directory}/{path.name}")
    return archive


@pytest.fixture
def demo_package(package, monkeypatch):
    from retrieval.profiles import PROFILE_FIELDS
    processed = package / 'data/processed'
    metadata_path = package / 'data/embeddings/metadata.json'
    metadata = json.loads(metadata_path.read_text())
    metadata['usage'] = 'synthetic_demo'
    metadata_path.write_text(json.dumps(metadata))
    profile = pd.DataFrame({'food_place_id': ['r1'], 'demo_only': [True],
                            'profile_evidence': ['{}'], 'capacity': pd.array([None], dtype='Int64')})
    for key in PROFILE_FIELDS:
        profile[key] = pd.array([None], dtype='boolean')
    profile.to_parquet(processed / 'restaurant_profiles.parquet', index=False)
    manifest = {'version': 'ai1-profile-v1', 'usage': 'synthetic_demo',
                'baseline_sha256': metadata['source_files'], 'files': {'restaurant_profiles.parquet':
                    hashlib.sha256((processed / 'restaurant_profiles.parquet').read_bytes()).hexdigest()}}
    (processed / 'ai1_profile_manifest.json').write_text(json.dumps(manifest))
    (processed / 'ai1_dataset_card.json').write_text(json.dumps({'restaurants': 1, 'dishes': 1, 'menus': 1}))
    # Demo must work independently of the old fixed production counts.
    monkeypatch.setattr(preflight, 'COUNTS', {'restaurants': 26025, 'dishes': 4000, 'menu_items': 336167})
    return package


def test_demo_preflight_accepts_release_counts(demo_package):
    preflight.validate_ai1(demo_package)


@pytest.mark.parametrize('missing', ['restaurant_profiles.parquet', 'ai1_profile_manifest.json', 'ai1_dataset_card.json'])
def test_demo_preflight_requires_complete_sidecars(demo_package, missing):
    (demo_package / 'data/processed' / missing).unlink()
    with pytest.raises(ValueError, match='Incomplete demo release'):
        preflight.validate_ai1(demo_package)


def test_demo_preflight_rejects_wrong_card(demo_package):
    (demo_package / 'data/processed/ai1_dataset_card.json').write_text(json.dumps({'restaurants': 1, 'dishes': 1, 'menus': 9}))
    with pytest.raises(ValueError, match='card count mismatch'):
        preflight.validate_ai1(demo_package)


def test_demo_zip_provisions_fresh_windows_clone(demo_package, tmp_path):
    active = tmp_path / 'fresh demo clone'
    (active / 'data').mkdir(parents=True)
    payload = {str(p.relative_to(demo_package / 'data')).replace('\\', '/'):
               hashlib.sha256(p.read_bytes()).hexdigest()
               for p in (demo_package / 'data').rglob('*') if p.is_file()}
    archive = make_artifact_zip(demo_package, active / 'data/ai1-demo-data.zip')
    with zipfile.ZipFile(archive, 'a') as z:
        z.writestr('dataset_manifest.json', json.dumps({'usage': 'synthetic_demo', 'sha256': payload}))
    assert setup_artifacts.provision_ai1(active)
    preflight.validate_ai1(active)
    assert (active / 'data/processed/restaurant_profiles.parquet').is_file()
    assert (active / 'data/dataset_manifest.json').is_file()
    assert not list((active / 'data').glob('.ai1-provision-*'))


def test_demo_zip_manifest_corruption_does_not_publish(demo_package, tmp_path):
    archive = make_artifact_zip(demo_package, tmp_path / 'delivery/demo.zip')
    with zipfile.ZipFile(archive, 'a') as z:
        z.writestr('dataset_manifest.json', json.dumps({'usage': 'synthetic_demo', 'sha256': {'processed/dishes.parquet': '0' * 64}}))
    active = tmp_path / 'failed clone'
    active.mkdir()
    with pytest.raises(ValueError, match='checksum'):
        setup_artifacts.provision_ai1(active, archive)
    assert not (active / 'data/processed/dishes.parquet').exists()


def test_legacy_recovery_removes_stale_profiles_only(package, tmp_path):
    active = tmp_path / 'stale profile clone'
    shutil.copytree(package / 'data', active / 'data')
    (active / 'data/processed/restaurant_profiles.parquet').write_bytes(b'stale profile')
    (active / 'data/processed/ai1_profile_manifest.json').write_text('{}')
    (active / 'data/processed/history.txt').write_text('keep history')
    archive = make_artifact_zip(package, tmp_path / 'delivery/legacy.zip')
    assert setup_artifacts.provision_ai1(active, archive)
    preflight.validate_ai1(active)
    assert not (active / 'data/processed/restaurant_profiles.parquet').exists()
    assert not (active / 'data/processed/ai1_profile_manifest.json').exists()
    assert (active / 'data/processed/history.txt').read_text() == 'keep history'


def file_snapshot(root):
    return {str(path.relative_to(root)): path.read_bytes() for path in root.rglob("*") if path.is_file()}


@pytest.mark.parametrize("explicit", [False, True])
@pytest.mark.parametrize("quality_report", [False, True])
def test_zip_provisions_and_rerun_ignores_zip(package, tmp_path, monkeypatch, explicit, quality_report):
    active = tmp_path / "fresh clone with spaces"
    active.mkdir()
    if quality_report:
        (package / "data/processed/quality_report.json").write_text('{"fixture": true}')
    archive = make_artifact_zip(package, (tmp_path / "Downloads with spaces" if explicit else active / "data") / "ai1-v3-artifacts.zip")
    arguments = ["--root", str(active)] + (["--zip", str(archive)] if explicit else [])
    assert setup_artifacts.main(arguments) == 0
    preflight.validate_ai1(active)
    if quality_report:
        assert (active / "data/processed/quality_report.json").read_text() == '{"fixture": true}'
    assert not list((active / "data").glob(".ai1-provision-*"))
    before = file_snapshot(active)
    timestamps = {p: p.stat().st_mtime_ns for p in (active / "data").rglob("*") if p.is_file()}
    monkeypatch.setattr(setup_artifacts.zipfile, "ZipFile", lambda *a: pytest.fail("Valid active package must skip ZIP"))
    assert setup_artifacts.main(arguments) == 0
    assert file_snapshot(active) == before
    assert {p: p.stat().st_mtime_ns for p in timestamps} == timestamps


def test_valid_active_package_ignores_even_missing_explicit_zip(package, monkeypatch):
    monkeypatch.setattr(setup_artifacts.tempfile, "mkdtemp", lambda **k: pytest.fail("Must not stage valid active data"))
    assert setup_artifacts.provision_ai1(package, package / "nonexistent.zip")


def test_invalid_active_package_repaired_without_retaining_vector_file_locks(package, tmp_path):
    archive = make_artifact_zip(package, tmp_path / "delivery/ai1-v3-artifacts.zip")
    active = tmp_path / "existing clone"
    shutil.copytree(package / "data", active / "data")
    metadata_path = active / "data/embeddings/metadata.json"
    metadata = json.loads(metadata_path.read_text())
    metadata["source_files"]["dishes.parquet"] = "0" * 64
    metadata_path.write_text(json.dumps(metadata))
    historical = active / "data/processed/history.txt"
    historical.write_bytes(b"preserve unrelated file")
    assert setup_artifacts.provision_ai1(active, archive)
    preflight.validate_ai1(active)
    assert historical.read_bytes() == b"preserve unrelated file"
    assert not list((active / "data").glob(".ai1-provision-*"))


@pytest.mark.parametrize("damage", ["version", "source_hash", "vector_hash", "missing", "mapping",
                                    "traversal", "not_zip", "metadata_list", "sources_null", "mapping_null"])
def test_invalid_zip_preserves_active_files_and_cleans_stage(package, tmp_path, capsys, damage):
    metadata_path = package / "data/embeddings/metadata.json"
    metadata = json.loads(metadata_path.read_text())
    if damage == "version":
        metadata["dataset_version"] = "v2-original-ids"
    elif damage == "source_hash":
        metadata["source_files"]["dishes.parquet"] = "0" * 64
    elif damage == "mapping":
        metadata["menu_mapping"]["rows"] = 2
    elif damage == "metadata_list":
        metadata = []
    elif damage == "sources_null":
        metadata["source_files"] = None
    elif damage == "mapping_null":
        metadata["menu_mapping"] = None
    metadata_path.write_text(json.dumps(metadata))
    if damage == "vector_hash":
        with (package / "data/embeddings/dishes_vectors.npy").open("ab") as stream:
            stream.write(b"corrupt")
    elif damage == "missing":
        (package / "data/processed/dishes.parquet").unlink()
    archive = make_artifact_zip(package, tmp_path / "delivery/ai1-v3-artifacts.zip")
    if damage == "traversal":
        with zipfile.ZipFile(archive, "a") as bundle:
            bundle.writestr("../escaped.txt", "must not extract")
    elif damage == "not_zip":
        archive.write_bytes(b"invalid ZIP")
    active = tmp_path / "fresh clone"
    (active / "data/processed").mkdir(parents=True)
    (active / "data/processed/restaurants.parquet").write_bytes(b"preserve incomplete active data")
    (active / "data/processed/history.txt").write_bytes(b"preserve unrelated file")
    before = file_snapshot(active)
    with pytest.raises(SystemExit) as error:
        setup_artifacts.main(["--root", str(active), "--zip", str(archive)])
    assert error.value.code == 1
    diagnostic = capsys.readouterr().err
    assert "AI1 ZIP provisioning failed:" in diagnostic
    assert "WinError 32" not in diagnostic
    if damage == "version":
        assert "v3-menu" in diagnostic
    elif damage == "vector_hash":
        assert "checksum" in diagnostic
    elif damage == "source_hash":
        assert "differs" in diagnostic
    assert file_snapshot(active) == before
    assert not list((active / "data").glob(".ai1-provision-*"))


def test_zip_publish_failure_rolls_back_partial_replacement(package, tmp_path, monkeypatch):
    archive = make_artifact_zip(package, tmp_path / "delivery/ai1-v3-artifacts.zip")
    active = tmp_path / "fresh clone"
    (active / "data/processed").mkdir(parents=True)
    (active / "data/processed/restaurants.parquet").write_bytes(b"old incomplete package")
    before = file_snapshot(active)
    replace = setup_artifacts.os.replace

    def fail_third_file(source, destination):
        if source.name == "menu_items.parquet":
            raise OSError("fixture disk failure")
        return replace(source, destination)

    monkeypatch.setattr(setup_artifacts.os, "replace", fail_third_file)
    with pytest.raises(OSError, match="fixture disk failure"):
        setup_artifacts.provision_ai1(active, archive)
    assert file_snapshot(active) == before
    assert not list((active / "data").glob(".ai1-provision-*"))


def test_no_artifacts_or_zip_reports_both_provisioning_options(tmp_path, capsys):
    assert not setup_artifacts.provision_ai1(tmp_path)
    output = capsys.readouterr().out
    assert "ai1-demo-data.zip (demo)" in output
    assert "ai1-v3-artifacts.zip (legacy)" in output
    assert "Place the ZIP under data/" in output
    assert '.\\setup.ps1 -AI1ArtifactZip "C:\\path\\to\\ai1-v3-artifacts.zip"' in output
    assert not (tmp_path / "data").exists()


@pytest.mark.parametrize("section,key", [
    ("restaurants", "vectors"), ("restaurants", "ids"),
    ("dishes", "vectors"), ("dishes", "ids"), ("menu_mapping", "file"),
    ("source_files", "restaurants.parquet"), ("source_files", "dishes.parquet"),
    ("source_files", "menu_items.parquet"),
])
@pytest.mark.parametrize("path_kind", ["traversal", "backslash", "absolute", "windows", "unc", "other_file"])
def test_zip_metadata_paths_rejected_before_loader_reads(
    package, tmp_path, monkeypatch, section, key, path_kind
):
    metadata_path = package / "data/embeddings/metadata.json"
    metadata = json.loads(metadata_path.read_text())
    basename = key if section == "source_files" else metadata[section][key]
    # Absolute targets exist and have the expected hash. Merely relying on the
    # loader's hash checks would accept them, bypassing the ZIP's own payload.
    outside = package / "data" / ("processed" if section == "source_files" else "embeddings") / basename
    bad_path = {
        "traversal": f"../../../embeddings/{basename}",
        "backslash": f"..\\..\\..\\embeddings\\{basename}",
        "absolute": str(outside.resolve()),
        "windows": f"C:\\outside\\{basename}",
        "unc": f"\\\\server\\share\\{basename}",
        "other_file": "unexpected.bin",
    }[path_kind]
    if section == "source_files":
        # Keep all required keys: the loader also follows additional keys.
        metadata[section][bad_path] = metadata[section][key]
    else:
        metadata[section][key] = bad_path
    metadata_path.write_text(json.dumps(metadata))
    archive = make_artifact_zip(package, tmp_path / "delivery/unsafe.zip")
    active = tmp_path / "active"
    (active / "data/embeddings").mkdir(parents=True)
    # This reproduces the staging-relative bypass against an active vector.
    shutil.copyfile(package / "data/embeddings/restaurants_vectors.npy",
                    active / "data/embeddings/restaurants_vectors.npy")
    before = file_snapshot(active)
    monkeypatch.setattr(preflight, "validate_ai1", lambda root: pytest.fail("Unsafe metadata reached loader"))
    with pytest.raises(ValueError, match="canonical"):
        setup_artifacts.provision_ai1(active, archive)
    assert file_snapshot(active) == before
    assert not list((active / "data").glob(".ai1-provision-*"))


@pytest.mark.parametrize("entry", ["embeddings/restaurants_vectors.npy", "processed/"])
def test_zip_symlinks_rejected_without_touching_active_data(package, tmp_path, entry):
    archive = tmp_path / "linked.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        link = zipfile.ZipInfo(entry)
        link.create_system = 3
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        bundle.writestr(link, str(package / "data/embeddings/restaurants_vectors.npy"))
        for name in preflight.AI1_FILES:
            relative = name.removeprefix("data/")
            if relative != entry:
                bundle.write(package / name, relative)
    active = tmp_path / "active"
    active.mkdir()
    with pytest.raises(ValueError, match="Linked AI1 ZIP entry"):
        setup_artifacts.provision_ai1(active, archive)
    assert file_snapshot(active) == {}
    assert not list((active / "data").glob(".ai1-provision-*"))


@pytest.mark.parametrize("relative", ["data/embeddings", "data/embeddings/metadata.json",
                                     "data/embeddings/restaurants_vectors.npy"])
def test_redirected_package_paths_rejected_before_read(package, monkeypatch, relative):
    redirected = package / relative
    resolve = Path.resolve

    def redirected_resolve(path, *args, **kwargs):
        if path == redirected:
            return package / "outside"
        return resolve(path, *args, **kwargs)

    def guarded_open(path, *args, **kwargs):
        pytest.fail("Redirected package must be rejected before opening any file")

    monkeypatch.setattr(Path, "resolve", redirected_resolve)
    monkeypatch.setattr(Path, "open", guarded_open)
    with pytest.raises(ValueError, match="linked destination"):
        setup_artifacts._validate_ai1(package)


@pytest.mark.parametrize("damage", [
    "list", "null", "invalid_json", "sources_null", "source_digest_null",
    "restaurants_list", "dishes_null", "missing_section", "vectors_list",
    "ids_null", "rows_string", "dimension_bool", "mapping_list", "mapping_rows_null",
])
@pytest.mark.parametrize("valid_replacement", [True, False])
def test_malformed_active_metadata_recovery(package, tmp_path, damage, valid_replacement):
    archive = make_artifact_zip(package, tmp_path / "delivery/replacement.zip")
    active = tmp_path / "active"
    shutil.copytree(package / "data", active / "data")
    metadata_path = active / "data/embeddings/metadata.json"
    metadata = json.loads(metadata_path.read_text())
    if damage == "list":
        metadata = []
    elif damage == "null":
        metadata = None
    elif damage == "sources_null":
        metadata["source_files"] = None
    elif damage == "source_digest_null":
        metadata["source_files"]["dishes.parquet"] = None
    elif damage == "restaurants_list":
        metadata["restaurants"] = []
    elif damage == "dishes_null":
        metadata["dishes"] = None
    elif damage == "missing_section":
        del metadata["restaurants"]
    elif damage == "vectors_list":
        metadata["restaurants"]["vectors"] = []
    elif damage == "ids_null":
        metadata["dishes"]["ids"] = None
    elif damage == "rows_string":
        metadata["restaurants"]["rows"] = "1"
    elif damage == "dimension_bool":
        metadata["dishes"]["dimension"] = True
    elif damage == "mapping_list":
        metadata["menu_mapping"] = []
    elif damage == "mapping_rows_null":
        metadata["menu_mapping"]["rows"] = None
    metadata_path.write_text("{" if damage == "invalid_json" else json.dumps(metadata))
    before = file_snapshot(active)
    if valid_replacement:
        assert setup_artifacts.provision_ai1(active, archive)
        preflight.validate_ai1(active)
        assert file_snapshot(active / "data") == file_snapshot(package / "data")
    else:
        archive.write_bytes(b"invalid replacement ZIP")
        with pytest.raises(zipfile.BadZipFile):
            setup_artifacts.provision_ai1(active, archive)
        assert file_snapshot(active) == before
    assert not list((active / "data").glob(".ai1-provision-*"))


def test_valid_active_package_ignores_invalid_replacement(package, tmp_path):
    archive = tmp_path / "invalid.zip"
    archive.write_bytes(b"invalid replacement ZIP")
    before = file_snapshot(package / "data")
    assert setup_artifacts.provision_ai1(package, archive)
    assert file_snapshot(package / "data") == before


@pytest.mark.parametrize("error_type", [AttributeError, KeyError, TypeError, RuntimeError,
                                       PermissionError, OSError, FileNotFoundError])
def test_unexpected_validation_errors_stop_without_provisioning(package, monkeypatch, error_type):
    def broken_validator(root):
        raise error_type("unexpected failure")

    before = file_snapshot(package)
    monkeypatch.setattr(preflight, "validate_ai1", broken_validator)
    monkeypatch.setattr(setup_artifacts.tempfile, "mkdtemp", lambda **k: pytest.fail("Must not provision"))
    with pytest.raises(error_type, match="unexpected failure"):
        setup_artifacts.provision_ai1(package)
    assert file_snapshot(package) == before


def test_rollback_failure_retains_backups_and_existing_recovery(package, tmp_path, monkeypatch):
    archive = make_artifact_zip(package, tmp_path / "delivery/valid.zip")
    active = tmp_path / "active"
    processed = active / "data/processed"
    processed.mkdir(parents=True)
    original = b"original incomplete data"
    (processed / "restaurants.parquet").write_bytes(original)
    previous = active / "data/.ai1-provision-previous/backup"
    previous.mkdir(parents=True)
    (previous / "keep.txt").write_bytes(b"older manual recovery")
    previous_snapshot = file_snapshot(previous)
    replace = setup_artifacts.os.replace

    def fail_publish_and_restore(source, destination):
        if source.name == "dishes.parquet":
            raise OSError("publish failure")
        if "backup" in source.parts:
            raise PermissionError("rollback failure")
        return replace(source, destination)

    with monkeypatch.context() as patch:
        patch.setattr(setup_artifacts.os, "replace", fail_publish_and_restore)
        with pytest.raises(RuntimeError, match="recovery files retained at") as error:
            setup_artifacts.provision_ai1(active, archive)
    recovery, = [p for p in (active / "data").glob(".ai1-provision-*") if p != previous.parent]
    assert str(recovery) in str(error.value)
    assert isinstance(error.value.__cause__, PermissionError)
    assert (recovery / "backup/processed/restaurants.parquet").read_bytes() == original
    assert (recovery / "data/processed/dishes.parquet").is_file()
    retained = file_snapshot(recovery)
    # A later successful run may clean only its own stage, never earlier recovery.
    assert setup_artifacts.provision_ai1(active, archive)
    assert file_snapshot(recovery) == retained
    assert file_snapshot(previous) == previous_snapshot


def test_git_ignores_provisioning_staging_and_recovery(tmp_path):
    git = shutil.which("git")
    if not git:
        pytest.skip("Git is needed to verify ignore semantics")
    subprocess.run([git, "init", "--quiet", str(tmp_path)], check=True, capture_output=True)
    shutil.copyfile(preflight.ROOT / ".gitignore", tmp_path / ".gitignore")
    paths = ["data/.ai1-provision-stage/data/processed/restaurants.parquet",
             "data/.ai1-provision-stage/data/embeddings/restaurants_vectors.npy",
             "data/.ai1-provision-recovery/backup/processed/restaurants.parquet",
             "data/.ai1-provision-recovery/backup/embeddings/metadata.json"]
    for relative in paths:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"synthetic artifact")
    result = subprocess.run([git, "check-ignore", "--stdin", "-z", "--verbose"], cwd=tmp_path,
                            input=("\0".join(paths) + "\0").encode(), capture_output=True, check=True)
    fields = result.stdout.decode().split("\0")[:-1]
    assert set(fields[3::4]) == set(paths)
    assert set(fields[0::4]) == {".gitignore"}
    assert set(fields[2::4]) == {"/data/.ai1-provision-*/"}


@pytest.mark.parametrize("state", ["cpu", "missing", "ready", "unavailable", "operation_failed"])
def test_torch_probe_reports_build_and_executes_only_cuda_operation(monkeypatch, capsys, state):
    tensor = MagicMock()
    tensor.__add__.return_value.item.return_value = 2
    torch = SimpleNamespace(
        __version__="2.14.1+cpu" if state == "cpu" else "2.14.1+cu130",
        version=SimpleNamespace(cuda=None if state == "cpu" else "13.0"),
        cuda=SimpleNamespace(is_available=MagicMock(return_value=state != "unavailable"),
                             get_device_name=lambda i: "fixture NVIDIA"),
        ones=MagicMock(return_value=tensor, side_effect=RuntimeError("fixture operation failure") if state == "operation_failed" else None),
    )
    monkeypatch.setitem(sys.modules, "torch", None if state == "missing" else torch)
    assert preflight.main(["--torch-json"]) == 0
    status = json.loads(capsys.readouterr().out)
    assert status["state"] == ("unavailable" if state == "operation_failed" else state)
    assert torch.ones.call_count == int(state in {"ready", "operation_failed"})
    if state == "cpu":
        assert status["cuda"] is None
        assert "CPU-only build detected" in status["detail"]
    elif state == "ready":
        assert status["available"] and status["cuda"] == "13.0"
