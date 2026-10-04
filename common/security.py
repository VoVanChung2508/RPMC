from __future__ import annotations

import hashlib
import ipaddress
import os
from pathlib import Path


class PathValidator:
    """Protect against path traversal leaks and enforce root-scoped file access."""

    @staticmethod
    def validate(root_dir: str, target_path: str) -> Path:
        root = Path(root_dir).expanduser().resolve()
        target = (root / target_path).resolve()
        if root not in target.parents and target != root:
            raise SecurityError(f"Path traversal blocked: {target_path!r} is outside {root_dir!r}")
        return target


class SecurityError(RuntimeError):
    pass


def require_loopback(host: str) -> None:
    try:
        if ipaddress.ip_address(host).is_loopback:
            return
    except ValueError:
        if host.lower() == "localhost":
            return
    raise ValueError("RPMC demo connections are restricted to loopback; remote TLS is not implemented")


class ChecksumUtil:
    @staticmethod
    def sha256_bytes(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    @staticmethod
    def sha256_file(path: str | os.PathLike[str]) -> str:
        digest = hashlib.sha256()
        with open(path, "rb") as handle:
            for chunk in iter(lambda: handle.read(8192), b""):
                digest.update(chunk)
        return digest.hexdigest()


class HashChainAuditLogger:
    def __init__(self) -> None:
        self._last_hash = "0" * 64

    def append(self, entry: str) -> str:
        current = hashlib.sha256(f"{self._last_hash}:{entry}".encode("utf-8")).hexdigest()
        self._last_hash = current
        return current

    @property
    def last_hash(self) -> str:
        return self._last_hash
