#!/usr/bin/env python3
"""Find the places in the wipe viewer's crops where halved colour resolution loses the most.

For every area, the colour error (distance in Cb, Cr from lossless) of ordinary JPEG 65 minus
that of full-colour JPEG 65, on pixels of fine coloured detail, is averaged over 32 px windows; the windows where the difference
is largest are where subsampling, and not the quality setting, is what costs colour. Writes
colour-loss.json (ranked spots) and colour-loss.png: one row per spot, 96 px crops at 4x of
lossless, JPEG 65, JPEG 85 and JPEG 65 with full colour resolution.

    python3 find_colour_loss.py
"""
import glob, json
import numpy as np
from PIL import Image, ImageDraw

WIN, CROP, ZOOM, PER_AREA, ROWS, DETAIL = 32, 96, 4, 2, 14, 14
def cbcr(key, code):
    return np.asarray(Image.open(f"img/{key}-{code}.png").convert("YCbCr"))[..., 1:].astype(float)
def box(a, n):
    c = np.cumsum(np.cumsum(np.pad(a, ((1, 0), (1, 0))), 0), 1)
    return (c[n:, n:] - c[:-n, n:] - c[n:, :-n] + c[:-n, :-n]) / n / n

spots, areas = [], {}
for path in sorted(glob.glob("img/*-lossless.png")):
    key = path[4:-13]
    ref = cbcr(key, "lossless")
    err = {c: np.sqrt(((cbcr(key, c) - ref) ** 2).sum(-1)) for c in ("q65", "q85", "c65")}
    # Count only fine coloured detail: pixels whose colour differs from the 7 px local mean by
    # more than DETAIL. That keeps thin saturated things (paint, cars, roofs' edges) and drops
    # the diffuse error of forest texture, which is large on average but not seen as lost colour.
    local = np.stack([np.pad(box(ref[..., k], 7), 3, mode="edge") for k in (0, 1)], -1)
    fine = np.sqrt(((ref - local) ** 2).sum(-1)) > DETAIL
    gain = box((err["q65"] - err["c65"]) * fine, WIN)
    areas[key] = {c: round(float(e.mean()), 2) for c, e in err.items()}
    g = gain.copy()
    for _ in range(PER_AREA):
        y, x = np.unravel_index(g.argmax(), g.shape)
        w = (slice(y, y + WIN), slice(x, x + WIN))
        spots.append({"area": key, "x": int(x + WIN // 2), "y": int(y + WIN // 2), "gain": round(float(g[y, x]), 2),
                      **{c: round(float(err[c][w].mean()), 2) for c in err}})
        g[max(0, y - WIN):y + WIN, max(0, x - WIN):x + WIN] = -1
spots.sort(key=lambda s: -s["gain"])
json.dump({"window_px": WIN, "areas_mean_colour_error": areas, "spots": spots}, open("colour-loss.json", "w"), indent=1)

codes = ("lossless", "q65", "q85", "c65")
cell = CROP * ZOOM
sheet = Image.new("RGB", (len(codes) * (cell + 8) + 200, ROWS * (cell + 8) + 24), "white")
d = ImageDraw.Draw(sheet)
for i, t in enumerate(("lossless", "JPEG 65", "JPEG 85", "JPEG 65 full colour")):
    d.text((200 + i * (cell + 8), 6), t, fill="black")
for r, s in enumerate(spots[:ROWS]):
    y0 = 24 + r * (cell + 8)
    d.text((4, y0 + 4), f"{s['area']}\nx {s['x']} y {s['y']}\ncolour error\n65: {s['q65']}\n85: {s['q85']}\n65 full: {s['c65']}", fill="black")
    for i, c in enumerate(codes):
        im = Image.open(f"img/{s['area']}-{c}.png").convert("RGB")
        x, y = min(max(s["x"] - CROP // 2, 0), im.width - CROP), min(max(s["y"] - CROP // 2, 0), im.height - CROP)
        sheet.paste(im.crop((x, y, x + CROP, y + CROP)).resize((cell, cell), Image.NEAREST), (200 + i * (cell + 8), y0))
sheet.save("colour-loss.png")
