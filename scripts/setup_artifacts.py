"""Offline, validated AI1 ZIP provisioning for setup.ps1."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import stat
import tempfile
import traceback
import zipfile

from scripts import preflight

OPTIONAL_FILES = (
    "processed/quality_report.json", "processed/restaurant_profiles.parquet",
    "processed/ai1_profile_manifest.json", "processed/ai1_profile_quality_report.json",
    "processed/ai1_dataset_card.json", "dataset_manifest.json",
)


def _check_package_paths(root: Path) -> None:
    """Reject redirects before opening even metadata or checking file contents."""
    paths = ("data", "data/processed", "data/embeddings", *preflight.AI1_FILES,
             *("data/" + name for name in OPTIONAL_FILES))
    for name in paths:
        path = root / name
        if path.is_symlink() or path.resolve() != path.absolute():
            raise ValueError(f"AI1 provisioning refuses linked destination: {path}")


def _validate_metadata(root: Path) -> None:
    """Check the V3 loader's input structure and bind every reference to the ZIP.

    Only canonical basenames are accepted, including every source_files key.
    No metadata-controlled path is opened here. Hashes, shapes, identities and
    production counts are still checked by the existing preflight validator.
    """
    _check_package_paths(root)
    missing = [name for name in preflight.AI1_FILES if not preflight.materialized(root / name)]
    if missing:
        raise ValueError("Missing/empty/unmaterialized files: " + ", ".join(missing))
    metadata = json.loads((root / "data/embeddings/metadata.json").read_text(encoding="utf-8"))

    def object_value(value, label):
        if not isinstance(value, dict):
            raise ValueError(f"AI1 metadata {label} must be an object")
        return value

    def digest(value, label):
        if (not isinstance(value, str) or len(value) != 64
                or any(c not in "0123456789abcdef" for c in value)):
            raise ValueError(f"AI1 metadata {label} must be a SHA256 digest")

    def positive_integer(value, label):
        if type(value) is not int or value <= 0:
            raise ValueError(f"AI1 metadata {label} must be a positive integer")

    def reference(value, expected, label):
        # Exact string comparison also rejects absolute, drive-relative, UNC,
        # traversal and alternate-separator paths on every host platform.
        if not isinstance(value, str) or value != expected:
            raise ValueError(f"AI1 metadata {label} must reference canonical file {expected}")

    object_value(metadata, "root")
    sources = object_value(metadata.get("source_files"), "source_files")
    expected_sources = {f"{name}.parquet" for name in preflight.COUNTS}
    if set(sources) != expected_sources:
        raise ValueError("AI1 metadata source_files must reference exactly the canonical processed files")
    for name, value in sources.items():
        digest(value, f"source_files.{name}")
    for name in ("restaurants", "dishes"):
        info = object_value(metadata.get(name), name)
        positive_integer(info.get("rows"), f"{name}.rows")
        positive_integer(info.get("dimension"), f"{name}.dimension")
        for key, suffix in (("vectors", "vectors.npy"), ("ids", "ids.csv")):
            reference(info.get(key), f"{name}_{suffix}", f"{name}.{key}")
            digest(info.get(f"{key}_sha256"), f"{name}.{key}_sha256")
    mapping = object_value(metadata.get("menu_mapping"), "menu_mapping")
    reference(mapping.get("file"), "menu_to_vectors.parquet", "menu_mapping.file")
    positive_integer(mapping.get("rows"), "menu_mapping.rows")
    digest(mapping.get("sha256"), "menu_mapping.sha256")


def _validate_ai1(root: Path) -> None:
    try:
        _validate_metadata(root)
        preflight.validate_ai1(root)
    except Exception as exc:
        # The loader uses NumPy memmaps. Failed validation retains them in
        # traceback locals, locking Windows files during cleanup/replacement.
        # Release completed frames while preserving the original diagnostic.
        traceback.clear_frames(exc.__traceback__)
        raise


def provision_ai1(root: Path, archive: Path | None = None) -> bool:
    """Keep valid active data; stage and validate replacements before publishing.

    Ordinary installation failures restore every touched file. Backups are kept
    with their location reported if the filesystem also prevents rollback.
    """
    root = root.resolve()
    try:
        _validate_ai1(root)
    except ValueError as exc:
        active_error = str(exc)
    else:
        print("AI1 artifacts: READY; active V3 package valid, ZIP ignored.")
        return True

    explicit = archive is not None
    if not explicit:
        demo_archive = root / "data/ai1-demo-data.zip"
        archive = demo_archive if demo_archive.is_file() else root / "data/ai1-v3-artifacts.zip"
    archive = Path(archive)
    if not archive.is_file():
        if explicit:
            raise ValueError(f"AI1 artifact ZIP not found: {archive}")
        print(f"AI1 artifacts unavailable: {active_error}\n{preflight.AI1_ACQUISITION}")
        return False  # Full preflight reports all missing capabilities afterward.

    data = root / "data"
    names = [str(Path(name).relative_to("data")).replace("\\", "/") for name in preflight.AI1_FILES]
    # Reject redirected destinations before making any change.
    _check_package_paths(root)
    data.mkdir(exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".ai1-provision-", dir=data))
    cleanup = True
    try:
        staged_data = stage / "data"
        with zipfile.ZipFile(archive) as bundle:
            allowed = set(names) | set(OPTIONAL_FILES)
            seen = set()
            for info in bundle.infolist():
                name = info.filename
                if stat.S_ISLNK(info.external_attr >> 16):
                    raise ValueError(f"Linked AI1 ZIP entry: {name}")
                if info.is_dir() and name in {"processed/", "embeddings/"}:
                    continue
                if name not in allowed or name in seen:
                    raise ValueError(f"Unexpected/duplicate/linked AI1 ZIP entry: {name}")
                seen.add(name)
                target = staged_data / name
                target.parent.mkdir(parents=True, exist_ok=True)
                with bundle.open(info) as source, target.open("wb") as destination:
                    shutil.copyfileobj(source, destination)
        if (staged_data / "dataset_manifest.json").is_file():
            from scripts.kaggle_setup import verify_manifest
            manifest = verify_manifest(staged_data, "dataset_manifest.json")
            if set(manifest["sha256"]) != seen - {"dataset_manifest.json"}:
                raise ValueError("Dataset manifest must cover exactly the ZIP payload")
            metadata = json.loads((staged_data / "embeddings/metadata.json").read_text(encoding="utf-8"))
            if manifest.get("usage") != metadata.get("usage"):
                raise ValueError("Dataset manifest usage mismatch")
        _validate_ai1(stage)
        names.extend(name for name in OPTIONAL_FILES if (staged_data / name).is_file())
        obsolete = [name for name in OPTIONAL_FILES if name not in names and (data / name).is_file()]

        # Back up only corresponding files; preserve unrelated historical files.
        backup = stage / "backup"
        existing = set()
        for name in names + obsolete:
            target = data / name
            if target.exists():
                saved = backup / name
                saved.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(target, saved)
                existing.add(name)
        touched = []
        created_dirs = []
        try:
            for name in names:
                target = data / name
                if not target.parent.exists():
                    target.parent.mkdir()
                    created_dirs.append(target.parent)
                os.replace(staged_data / name, target)
                touched.append(name)
            for name in obsolete:
                (data / name).unlink()
                touched.append(name)
        except OSError:
            try:
                for name in reversed(touched):
                    if name in existing:
                        os.replace(backup / name, data / name)
                    else:
                        (data / name).unlink()
                for directory in reversed(created_dirs):
                    directory.rmdir()
            except OSError as rollback_error:
                cleanup = False
                raise RuntimeError(f"AI1 installation and rollback failed; recovery files retained at {stage}") from rollback_error
            raise
        print("AI1 artifacts: READY; validated V3 ZIP provisioned.")
        return True
    finally:
        if cleanup:
            # stage is exclusively ours, created directly under resolved data.
            if stage.resolve().parent != data.resolve() or stage.is_symlink():
                raise RuntimeError(f"Refusing cleanup of redirected staging directory: {stage}")
            shutil.rmtree(stage)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=preflight.ROOT)
    parser.add_argument("--zip", type=Path)
    args = parser.parse_args(argv)
    try:
        provision_ai1(args.root, args.zip)
    except Exception as exc:
        parser.exit(1, f"AI1 ZIP provisioning failed: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
