"""Render the PNG app icons (same design as static/favicon.svg).

    ../.venv/bin/python scripts/make_icons.py      (from web/; needs numpy)

Writes static/icons/icon-192.png, icon-512.png and icon-maskable-512.png.
Rendered with 4x supersampling; PNGs encoded with the standard library.
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

import numpy as np

BG = (0x11, 0x14, 0x18)
INK = (0xE8, 0xB0, 0x6A)
# Rings in the favicon's 64-unit space: (cx, cy, r); stroke width 4.5.
RINGS = ((31, 33, 20), (33.5, 31.5, 12.5), (35.5, 30, 5.5))
STROKE = 4.5
OUT = Path(__file__).resolve().parents[1] / "static" / "icons"


def render(size: int, *, scale: float, rounded: bool) -> np.ndarray:
    ss = 4
    n = size * ss
    # Pixel centers in favicon units, art scaled around the center (maskable: safe zone).
    coords = (np.arange(n) + 0.5) / n * 64
    x, y = np.meshgrid(coords, coords)
    x = 32 + (x - 32) / scale
    y = 32 + (y - 32) / scale
    ink = np.zeros((n, n), bool)
    for cx, cy, r in RINGS:
        d = np.hypot(x - cx, y - cy)
        ink |= np.abs(d - r) <= STROKE / 2
    alpha = np.ones((n, n), bool)
    if rounded:  # rounded-square background, radius 14/64
        px = (np.arange(n) + 0.5) / n * 64
        gx, gy = np.meshgrid(px, px)
        dx = np.maximum(np.abs(gx - 32) - (32 - 14), 0)
        dy = np.maximum(np.abs(gy - 32) - (32 - 14), 0)
        alpha = np.hypot(dx, dy) <= 14
    rgb = np.where(ink[..., None], INK, BG).astype(float)
    rgba = np.concatenate([rgb, alpha[..., None] * 255.0], axis=-1)
    # Downsample (box filter), premultiplied so transparent corners don't darken edges.
    a = rgba[..., 3:4] / 255
    premul = np.concatenate([rgba[..., :3] * a, rgba[..., 3:4]], axis=-1)
    small = premul.reshape(size, ss, size, ss, 4).mean(axis=(1, 3))
    out_a = small[..., 3:4] / 255
    rgb_out = np.where(out_a > 0, small[..., :3] / np.maximum(out_a, 1e-6), 0)
    return np.concatenate([rgb_out, small[..., 3:4]], axis=-1).round().astype(np.uint8)


def write_png(path: Path, img: np.ndarray) -> None:
    h, w, _ = img.shape
    raw = b"".join(b"\x00" + img[row].tobytes() for row in range(h))

    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
        )

    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(raw, 9))
    png += chunk(b"IEND", b"")
    path.write_bytes(png)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    write_png(OUT / "icon-192.png", render(192, scale=1.0, rounded=True))
    write_png(OUT / "icon-512.png", render(512, scale=1.0, rounded=True))
    # Maskable: full-bleed background, art inside the central 80% safe zone.
    write_png(OUT / "icon-maskable-512.png", render(512, scale=0.78, rounded=False))
    print(f"wrote icons to {OUT}")


if __name__ == "__main__":
    main()
