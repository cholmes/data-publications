#!/usr/bin/env python3
"""Write the requests overview.py takes, one per variant, for one state-year of the hosted index.

    python3 make_overview_requests.py <naip stac index.parquet> <state> <year> <out dir> \
        [--collars dark-edge-quads.json] [--limit N] [--by-zone] [--prefix KEY_PREFIX]

With --by-zone: one request per UTM zone of the state-year, in that zone, at 9.6 m, named
<state>-<year>-utm<zone> and written to <prefix><state>/<year>/<name>.tif (the layout and
names decided 2026-11-14). Without it, the four test variants below.

Variants: the state's main UTM zone at 9.6 m and 4.8 m, and Web Mercator at zoom 14 and 15
(256-pixel zoom levels: 9.55 m and 4.78 m at the equator), which read the 4.8 m and 2.4 m
quad levels so the ground pixel is never coarser than what is read.
"""
import argparse
import collections
import json
import os

import pyarrow.parquet as pq

WEB_ZOOM_0 = 156543.03392804097          # metres per pixel at zoom 0, 256-pixel tiles
PREFIX = "_proto/grid-1/overviews/"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("index")
    p.add_argument("state")
    p.add_argument("year", type=int)
    p.add_argument("out_dir")
    p.add_argument("--collars")
    p.add_argument("--limit", type=int)
    p.add_argument("--by-zone", action="store_true")
    p.add_argument("--prefix", default=PREFIX, help="key prefix of the files and results in the work bucket")
    a = p.parse_args()
    with open(a.index, "rb") as f:
        rows = pq.ParquetFile(f).read(columns=["id", "gsd", "naip:state", "naip:year", "proj:epsg", "assets"]).to_pylist()
    quads = sorted([r["id"], r["assets"]["image"]["href"].split("data.source.coop/")[1], r["proj:epsg"], r["gsd"]]
                   for r in rows if r["naip:state"] == a.state and r["naip:year"] == a.year)[:a.limit]
    main_zone = collections.Counter(q[2] for q in quads).most_common(1)[0][0]
    collars = []
    if a.collars:
        with open(a.collars) as f:
            collars = sorted({r["id"] for r in json.load(f)["results"]} & {q[0] for q in quads})
    os.makedirs(a.out_dir, exist_ok=True)

    def write(name, epsg, res, read_m, members, folder=""):
        ids = {q[0] for q in members}
        with open(os.path.join(a.out_dir, name + "-request.json"), "w") as f:
            json.dump({"bucket": "us-west-2.opendata.source.coop", "name": name, "target_epsg": epsg, "res": res,
                       "read_m": read_m, "out_key": f"{a.prefix}{folder}{name}.tif",
                       "result_key": f"{a.prefix}{folder}{name}-result.json",
                       "quads": members, "collar_ids": [c for c in collars if c in ids]}, f)

    if a.by_zone:
        # One file per UTM zone of the state-year, in that zone: no quad is resampled into another zone.
        zones = collections.Counter(q[2] for q in quads)
        for zone, count in sorted(zones.items()):
            write(f"{a.state}-{a.year}-utm{zone % 100}", zone, 9.6, 9.6, [q for q in quads if q[2] == zone],
                  folder=f"{a.state}/{a.year}/")
        print(a.state, a.year, len(quads), "quads by zone", dict(zones), len(collars), "black-edged")
        return
    variants = {
        "utm-9.6": (main_zone, 9.6, 9.6), "utm-4.8": (main_zone, 4.8, 4.8),
        "web-14": (3857, WEB_ZOOM_0 / 2 ** 14, 4.8), "web-15": (3857, WEB_ZOOM_0 / 2 ** 15, 2.4),
    }
    for variant, (epsg, res, read_m) in variants.items():
        write(f"{a.state}-{a.year}-{variant}", epsg, res, read_m, quads)
    print(a.state, a.year, len(quads), "quads, main zone", main_zone, len(collars), "black-edged")


if __name__ == "__main__":
    main()
