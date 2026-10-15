"""Atomic UTF-8 JSONL snapshots; predictions and human labels remain separate."""

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
from uuid import uuid4

from conversation.conversation_logger import _redact
from common.schemas import PreferenceUpdate


def timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def unique_name(prefix: str) -> str:
    return f"{prefix}_{datetime.now(timezone.utc):%Y%m%d_%H%M%S_%f}_{uuid4().hex[:8]}"


class DatasetLogger:
    def __init__(self, directory: Path, *, enabled: bool, secrets=()):
        self.directory = Path(directory)
        self.enabled = enabled
        self.secrets = tuple(secrets)
        self.path = self.directory / f"{unique_name('session')}.jsonl"

    def safe(self, value):
        redacted = _redact(value, self.secrets)

        def redact_keys(item):
            if isinstance(item, dict):
                return {_redact(key, self.secrets): redact_keys(child) for key, child in item.items()}
            if isinstance(item, list):
                return [redact_keys(child) for child in item]
            return item

        return redact_keys(redacted)

    def _write(self, path: Path, records: list[dict]) -> Path:
        # Serialize before touching disk, then replace a complete snapshot atomically.
        payload = "".join(json.dumps(self.safe(record), ensure_ascii=False,
                                     allow_nan=False) + "\n" for record in records)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n",
                                             dir=path.parent, delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        return path

    def save(self, records: list[dict]) -> Path | None:
        return self._write(self.path, records) if self.enabled else None

    def export(self, records: list[dict]) -> Path:
        if not self.enabled:
            raise ValueError("Export disabled by --no-save.")
        training = []
        for record in records:
            status = record["label_status"]
            if status not in ("accepted", "corrected"):
                continue
            training.append({
                "schema_version": "0.2",
                "input": {key: record[key] for key in ("message", "old_state", "previous_results")},
                "target": PreferenceUpdate.model_validate(record["correction"] if status == "corrected" else record["preference_update"]).model_dump(mode="json"),
                "source": "interactive", "label_status": status,
            })
        return self._write(self.directory / "exports" / f"{unique_name('ai2_training')}.jsonl", training)
