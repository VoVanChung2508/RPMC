from __future__ import annotations

import base64
import hashlib
from io import BytesIO

from PIL import ImageGrab


class ScreenCaptureService:
    TILE_WIDTH = 64
    TILE_HEIGHT = 64

    def __init__(self) -> None:
        self._dimensions: tuple[int, int] | None = None
        self._previous_hashes: dict[tuple[int, int], str] = {}

    def capture_delta_tiles(self, force_full: bool = False) -> tuple[int, int, list[dict]]:
        image = ImageGrab.grab().convert("RGB")
        image.thumbnail((1600, 1200))
        width, height = image.size
        if self._dimensions != (width, height):
            self._dimensions = (width, height)
            self._previous_hashes.clear()
            force_full = True

        current_hashes: dict[tuple[int, int], str] = {}
        changed_tiles = []
        for y in range(0, height, self.TILE_HEIGHT):
            for x in range(0, width, self.TILE_WIDTH):
                tile = image.crop(
                    (x, y, min(x + self.TILE_WIDTH, width), min(y + self.TILE_HEIGHT, height))
                )
                digest = hashlib.sha256(tile.tobytes()).hexdigest()
                key = (x, y)
                current_hashes[key] = digest
                if not force_full and self._previous_hashes.get(key) == digest:
                    continue
                buffer = BytesIO()
                tile.save(buffer, format="JPEG", quality=65, optimize=True)
                changed_tiles.append(
                    {
                        "x": x,
                        "y": y,
                        "width": tile.width,
                        "height": tile.height,
                        "hash": digest,
                        "jpeg_base64": base64.b64encode(buffer.getvalue()).decode("ascii"),
                    }
                )
        self._previous_hashes = current_hashes
        return width, height, changed_tiles

    def stop(self) -> None:
        self._dimensions = None
        self._previous_hashes.clear()
