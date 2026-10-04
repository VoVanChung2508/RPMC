from __future__ import annotations

import hashlib
import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class AuditLogger:
    def __init__(self, file_path: str | None = None) -> None:
        self.path = Path(
            file_path or os.environ.get("RPMC_AUDIT_FILE", "data/audit.jsonl")
        ).expanduser()
        self._lock = threading.Lock()
        self._entries: list[dict[str, Any]] = []
        self._last_hash = "0" * 64
        self._integrity_error: str | None = None
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            self._load()

    def _load(self) -> None:
        with self.path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                try:
                    entry = json.loads(line)
                    expected = self._hash_entry(
                        entry["previous_hash"],
                        entry["timestamp"],
                        entry["actor"],
                        entry["action"],
                        entry["result"],
                        entry["metadata"],
                    )
                    if entry["previous_hash"] != self._last_hash or entry["current_hash"] != expected:
                        raise ValueError("Hash-chain mismatch")
                    self._last_hash = expected
                    self._entries.append(entry)
                except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                    self._integrity_error = f"Invalid audit record at line {line_number}: {exc}"
                    break

    @staticmethod
    def _hash_entry(previous: str, timestamp: str, actor: str, action: str, result: str, metadata: dict) -> str:
        body = json.dumps(
            [timestamp, actor, action, result, metadata],
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(f"{previous}:{body}".encode("utf-8")).hexdigest()

    def log(self, actor: str, action: str, result: str, metadata: dict[str, Any] | None = None) -> str:
        with self._lock:
            if self._integrity_error:
                raise RuntimeError(f"Audit chain is invalid: {self._integrity_error}")
            timestamp = datetime.now(timezone.utc).isoformat()
            safe_metadata = metadata or {}
            current_hash = self._hash_entry(
                self._last_hash, timestamp, actor, action, result, safe_metadata
            )
            entry = {
                "timestamp": timestamp,
                "actor": actor,
                "action": action,
                "result": result,
                "metadata": safe_metadata,
                "previous_hash": self._last_hash,
                "current_hash": current_hash,
            }
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry, sort_keys=True) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            self._entries.append(entry)
            self._last_hash = current_hash
            return current_hash

    def list_entries(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._entries)

    def verify(self) -> tuple[bool, str]:
        with self._lock:
            if self._integrity_error:
                return False, self._integrity_error
            previous = "0" * 64
            for index, entry in enumerate(self._entries, start=1):
                expected = self._hash_entry(
                    previous,
                    entry["timestamp"],
                    entry["actor"],
                    entry["action"],
                    entry["result"],
                    entry["metadata"],
                )
                if entry["previous_hash"] != previous or entry["current_hash"] != expected:
                    return False, f"Hash-chain mismatch at entry {index}"
                previous = expected
            return True, f"Verified {len(self._entries)} audit entries"
