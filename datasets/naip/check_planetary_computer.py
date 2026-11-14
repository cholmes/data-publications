#!/usr/bin/env python3
"""Which hosted state-years does Microsoft Planetary Computer also hold?

    python3 check_planetary_computer.py <naip stac index.parquet> <out.json>

Asks the Planetary Computer STAC API, for every state, year from 2024 and pixel size, whether
its `naip` collection has at least one item, and compares the answer with the state-years in
the hosted index. It tests presence only: it does not count items, so a state-year listed as
present there may still be incomplete.
"""
import collections
import concurrent.futures
import datetime
import json
import sys
import urllib.request

import pyarrow.parquet as pq

API = "https://planetarycomputer.microsoft.com/api/stac/v1/search"
STATES = ("al ar az ca co ct de fl ga ia id il in ks ky la ma md me mi mn mo ms mt nc nd ne nh nj nm nv ny "
          "oh ok or pa ri sc sd tn tx ut va vt wa wi wv wy").split()
SIZES = (0.3, 0.6)


def present(key):
    state, year, size = key
    body = {"collections": ["naip"], "limit": 1, "filter-lang": "cql2-json",
            "datetime": f"{year}-01-01T00:00:00Z/{year}-12-31T23:59:59Z",
            "filter": {"op": "and", "args": [{"op": "=", "args": [{"property": "naip:state"}, state]},
                                             {"op": "=", "args": [{"property": "gsd"}, size]}]}}
    request = urllib.request.Request(API, data=json.dumps(body).encode(), headers={"content-type": "application/json"})
    for attempt in range(3):
        try:
            return key, bool(json.load(urllib.request.urlopen(request, timeout=90)).get("features"))
        except OSError as error:
            failure = error
    raise SystemExit(f"{key}: {failure}")


def main():
    index, out = sys.argv[1:3]
    with open(index, "rb") as f:
        rows = pq.ParquetFile(f).read(columns=["gsd", "naip:state", "naip:year"]).to_pylist()
    ours = collections.defaultdict(set)
    for r in rows:
        ours[r["naip:state"], r["naip:year"]].add(round(r["gsd"], 2))
    years = sorted({year for _, year in ours})
    keys = [(s, y, g) for s in STATES for y in years for g in SIZES]
    with concurrent.futures.ThreadPoolExecutor(6) as pool:
        answers = dict(pool.map(present, keys))
    theirs = collections.defaultdict(set)
    for (state, year, size), found in answers.items():
        if found:
            theirs[state, year].add(size)
    name = lambda k: f"{k[0]}-{k[1]}"
    result = {
        "checked": datetime.date.today().isoformat(), "api": API, "test": "at least one item per state, year and pixel size",
        "hosted_state_years": len(ours), "also_on_planetary_computer": sorted(name(k) for k in ours if k in theirs),
        "hosted_only": sorted(name(k) for k in ours if k not in theirs),
        "planetary_computer_only": sorted(name(k) for k in theirs if k not in ours),
        "different_pixel_size": {name(k): {"hosted": sorted(ours[k]), "planetary_computer": sorted(theirs[k])}
                                 for k in sorted(ours) if k in theirs and ours[k] != theirs[k]},
    }
    with open(out, "w") as f:
        json.dump(result, f, indent=1)
        f.write("\n")
    print(len(result["also_on_planetary_computer"]), "of", len(ours), "hosted state-years are also on Planetary Computer;",
          len(result["hosted_only"]), "are not;", len(result["planetary_computer_only"]), "are there and not hosted")


if __name__ == "__main__":
    main()
