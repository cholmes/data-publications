#!/usr/bin/env python3
"""Cold GDAL reads of the same three views from each layout, counting requests and bytes.
Each read is its own gdal_translate process, so nothing is cached between them.

    python3 gdal_reads.py > gdal-reads.jsonl

Layouts: a VRT over the 320 published quads, the published STAC index opened as a tile index
(GTI), a VRT over the 121 grid tiles, and the assembled 100 km file.
`python3 gdal_reads.py equal` gives the quads and tiles a separate overview file (4.8 m per
pixel and coarser) named in a VRT or .gti file, so every layout has the same overview depth.
Views (NAD83 UTM 12N), each read to a 1024 px wide image with average resampling:
street is 614 m around Sandy at full resolution, switch is 4.8 km around Alta (4.7 m per
pixel, just finer than the overview file), canyon is 15 km around Alta, region is the
whole square.
"""
import json, os, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
P = "https://private-work-bucket.s3.us-west-2.amazonaws.com/_proto/grid-1"
OV_LAYOUTS = [("quads-vrt+overview", f"{HERE}/quads-ov.vrt", []), ("quads-stac-index+overview", f"{HERE}/quads-stac-ov.gti", []),
              ("tiles-vrt+overview", f"{HERE}/tiles-ov.vrt", []), ("square", f"/vsicurl/{P}/square2/utm12_e400_n4400.tif", [])]
if len(sys.argv) > 2:   # one layout only
    OV_LAYOUTS = [l for l in OV_LAYOUTS if l[0] == sys.argv[2]]
LAYOUTS = [("quads-vrt", f"{HERE}/quads.vrt", []),
           ("quads-stac-index", f"GTI:{HERE}/../index/naip-stac.parquet", ["-oo", "FILTER=\"naip:state\" = 'ut'"]),
           ("tiles-vrt", f"{HERE}/tiles.vrt", []),
           ("square", f"/vsicurl/{P}/square/utm12_e400_n4400.tif", [])]
VIEWS = [("street", [432006, 4494969, 432621, 4494355]), ("switch", [443436, 4495848, 448249, 4491035]), ("canyon", [438343, 4500000, 453343, 4485941]),
         ("region", [400000.2, 4500000, 500000, 4400000])]
if len(sys.argv) > 1 and sys.argv[1] == 'equal':   # every layout with the same overview depth
    LAYOUTS = OV_LAYOUTS
env = dict(os.environ, GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", CPL_VSIL_SHOW_NETWORK_STATS="YES")
for view, win in VIEWS:
    for label, path, options in LAYOUTS:
        out = f"{HERE}/out-{view}-{label}.png"
        start = time.time()
        run = subprocess.run(["gdal_translate", "-q", "-of", "PNG", "-outsize", "1024", "0", "-r", "average",
                              "-projwin", *map(str, win), *options, path, out], env=env, capture_output=True, text=True)
        seconds, text = time.time() - start, run.stderr + run.stdout
        row = {"view": view, "layout": label, "seconds": round(seconds, 2), "exit": run.returncode}
        if "{" in text:
            stats = json.loads(text[text.find("{"):text.rfind("}") + 1])["handlers"].get("vsicurl", {})
            methods = stats.get("methods", {})
            row.update(requests=sum(m["count"] for m in methods.values()),
                       bytes=sum(m.get("downloaded_bytes", 0) for m in methods.values()),
                       files_touched=len(stats.get("files", {})))
        else:
            row["error"] = text[-300:]
        print(json.dumps(row), flush=True)
