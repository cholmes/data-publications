"""Rules shared by the build and stated in validation-plan.md. The validator has its own copies of
the joins and of the bounds; it imports only the Hilbert key from here, which is the rule of
scripts/release_tools/spatial_order.py."""
from __future__ import annotations

import numpy as np

BBOX_FIELDS = ["xmin", "ymin", "xmax", "ymax"]
ADDED = ["source_row", "gaz_funcstat", "popest_2023", "bbox"]
ROW_GROUP_SIZE = 512


def hilbert_distance(x: np.ndarray, y: np.ndarray, bits: int = 16) -> np.ndarray:
    x = np.asarray(x, dtype=np.uint32).copy()
    y = np.asarray(y, dtype=np.uint32).copy()
    limit = (1 << bits) - 1
    distance = np.zeros(len(x), dtype=np.uint64)
    scale = 1 << (bits - 1)
    while scale:
        rx = (x & scale) != 0
        ry = (y & scale) != 0
        distance += np.uint64(scale * scale) * ((rx.astype(np.uint64) * 3) ^ ry.astype(np.uint64))
        rotate = ~ry
        reflect = rotate & rx
        x[reflect] = np.uint32(limit) - x[reflect]
        y[reflect] = np.uint32(limit) - y[reflect]
        temp = x[rotate].copy()
        x[rotate] = y[rotate]
        y[rotate] = temp
        scale >>= 1
    return distance


def hilbert_keys(bounds: np.ndarray, bits: int = 16) -> np.ndarray:
    """Key of the centre of each row's bounds (xmin, ymin, xmax, ymax in degrees)."""
    centre_x = np.clip((bounds[:, 0] + bounds[:, 2]) * 0.5, -180.0, 180.0)
    centre_y = np.clip((bounds[:, 1] + bounds[:, 3]) * 0.5, -90.0, 90.0)
    scale = (1 << bits) - 1
    x = np.clip(np.floor((centre_x + 180.0) / 360.0 * scale), 0, scale).astype(np.uint32)
    y = np.clip(np.floor((centre_y + 90.0) / 180.0 * scale), 0, scale).astype(np.uint32)
    return hilbert_distance(x, y, bits)
