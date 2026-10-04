from __future__ import annotations

import os
from pathlib import Path

from common.security import PathValidator


class FileService:
    def __init__(self, root_dir: str):
        self.root_dir = root_dir

    def list_files(self, relative_path: str = "."):
        root = Path(self.root_dir).expanduser().resolve()
        target = PathValidator.validate(str(root), relative_path)
        if not target.is_dir():
            raise NotADirectoryError(relative_path)
        entries = []
        for item in sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
            entries.append(
                {
                    "path": str(item.relative_to(root)),
                    "name": item.name,
                    "is_dir": item.is_dir(),
                    "size": item.stat().st_size if item.is_file() else 0,
                    "modified": item.stat().st_mtime,
                }
            )
        return entries

    def read_bytes(self, relative_path: str, max_bytes: int = 8 * 1024 * 1024) -> bytes:
        target = PathValidator.validate(self.root_dir, relative_path)
        if not target.is_file():
            raise FileNotFoundError(relative_path)
        size = target.stat().st_size
        if size > max_bytes:
            raise ValueError(f"File exceeds the {max_bytes}-byte transfer limit")
        return target.read_bytes()
