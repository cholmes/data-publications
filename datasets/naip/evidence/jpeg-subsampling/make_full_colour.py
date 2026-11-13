#!/usr/bin/env python3
"""Add JPEG encodes with full colour resolution (4:4:4, no chroma subsampling) to the wipe
viewer, to test whether thin coloured detail (a yellow road line) is lost to the halved
colour resolution of ordinary YCbCr JPEG (4:2:0) and not to the quality setting.

Reads every img/<area>-lossless<level>.png, encodes with Pillow at quality 65, 75 and 85 with
subsampling off, saves the decoded PNG as img/<area>-c<q><level>.png and writes
full-colour.json: bytes per pixel and PSNR for 4:4:4 and, as a control, 4:2:0 from the same
encoder, with the colour-only (Cb, Cr) PSNR of each.

    python3 make_full_colour.py
"""
import glob, io, json
import numpy as np
from PIL import Image

def psnr(a, b):
    return round(float(10 * np.log10(255 ** 2 / ((a.astype(float) - b.astype(float)) ** 2).mean())), 2)

out = {}
for path in sorted(glob.glob("img/*-lossless*.png")):
    key, level = path[4:].split("-lossless")
    level = level[:-4] or "full"
    src = Image.open(path).convert("RGB")
    a, ac = np.asarray(src), np.asarray(src.convert("YCbCr"))[..., 1:]
    for q in (65, 75, 85):
        for code, sub in (("c", 0), ("s", 2)):
            buf = io.BytesIO()
            src.save(buf, "JPEG", quality=q, subsampling=sub)
            dec = Image.open(io.BytesIO(buf.getvalue())).convert("RGB")
            out.setdefault(key, {}).setdefault(level, {})[f"{code}{q}"] = {
                "bytes_per_pixel": round(len(buf.getvalue()) / a.shape[0] / a.shape[1], 4),
                "psnr_db": psnr(a, np.asarray(dec)), "colour_psnr_db": psnr(ac, np.asarray(dec.convert("YCbCr"))[..., 1:])}
            if code == "c":
                dec.save(f"img/{key}-c{q}{'' if level == 'full' else '-' + level.lstrip('-')}.png")
json.dump(out, open("full-colour.json", "w"), indent=1)
