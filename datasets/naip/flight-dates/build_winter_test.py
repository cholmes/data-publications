#!/usr/bin/env python3
"""Test of a winter layer for one area: snow where Sentinel-2 sees it, with trees showing through.

Three public inputs, all read anonymously:

- snow or not: the scene classification of the most recent Sentinel-2 passes (20 m), fetched as
  tiles from Microsoft Planetary Computer;
- how tall the vegetation is: Meta and WRI Canopy Height Maps v2 (about 1.2 m, metres), on AWS;
- how deep the snow is: NOAA SNODAS daily snow depth (about 1 km), from NSIDC.

Rule, per pixel of the web map's zoom 15 grid (about 3.6 m on the ground at 40 N):

1. Snow is present where Sentinel-2 marks snow, or where it does not but the pixel is forest
   surrounded by snow (the satellite cannot see snow under conifers).
2. Where snow is present, the pixel is drawn white in proportion to the share of it whose
   vegetation is no taller than the snow depth. Taller vegetation stays as the imagery below.

    python3 build_winter_test.py <out dir> [--bbox W S E N] [--snodas YYYYMMDD] [--days 21]

Writes <out dir>/winter-<row><col>.png (four images) and winter.json with their corners and the
figures used. Needs numpy, scipy, Pillow and GDAL's Python bindings.
"""
import argparse
import datetime
import gzip
import io
import json
import math
import os
import re
import tarfile
import urllib.parse
import urllib.request

import numpy as np
from osgeo import gdal
from PIL import Image
from scipy import ndimage

EARTH = 40075016.685578488
CANOPY = "/vsis3/dataforgood-fb-data/forests/v2/global/dinov3_global_chm_v2_ml3/chm/{key}.tif"
TILE_API = "https://planetarycomputer.microsoft.com/api/data/v1"
STAC_API = "https://planetarycomputer.microsoft.com/api/stac/v1/search"
SNODAS = "https://noaadata.apps.nsidc.org/NOAA/G02158/masked/{y}/{m:02d}_{mon}/SNODAS_{ymd}.tar"
ZOOM, SNOW_ZOOM = 15, 13                 # output grid; Sentinel-2 tiles (20 m data)
FOREST_M, FOREST_SHARE, FILL_M = 2, 0.3, 90
SNOW_RGB = (244, 248, 255)


def get(url, data=None, tries=5):
    for attempt in range(tries):
        try:
            request = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"} if data else {})
            with urllib.request.urlopen(request, timeout=120) as r:
                return r.read()
        except Exception:
            if attempt == tries - 1:
                raise


def merc(lon, lat):
    return lon / 360 * EARTH, math.asinh(math.tan(math.radians(lat))) / (2 * math.pi) * EARTH


def lonlat(x, y):
    return x / EARTH * 360, math.degrees(math.atan(math.sinh(y / EARTH * 2 * math.pi)))


def pixel_window(bbox, zoom):
    """Whole pixels of the zoom's world grid covering the box: column and row of the corner, size."""
    size = EARTH / (256 * 2 ** zoom)
    (x0, y0), (x1, y1) = merc(bbox[0], bbox[3]), merc(bbox[2], bbox[1])
    col0, row0 = math.floor((x0 + EARTH / 2) / size), math.floor((EARTH / 2 - y0) / size)
    col1, row1 = math.ceil((x1 + EARTH / 2) / size), math.ceil((EARTH / 2 - y1) / size)
    return col0, row0, col1 - col0, row1 - row0, size


def canopy(col0, row0, cols, rows, size):
    """Canopy height in metres on a grid twice as fine as the output grid."""
    keys = set()
    for col in (col0, col0 + cols - 1):
        for row in (row0, row0 + rows - 1):
            x, y = col >> (ZOOM + 8 - 10), row >> (ZOOM + 8 - 10)
            keys.add("".join(str(((x >> i) & 1) + 2 * ((y >> i) & 1)) for i in range(9, -1, -1)))
    vrt = gdal.BuildVRT("/vsimem/canopy.vrt", [CANOPY.format(key=k) for k in sorted(keys)])
    ulx, uly = col0 * size - EARTH / 2, EARTH / 2 - row0 * size
    out = gdal.Translate("/vsimem/canopy.tif", vrt, projWin=[ulx, uly, ulx + cols * size, uly - rows * size],
                         width=cols * 2, height=rows * 2, resampleAlg="nearest")
    return out.GetRasterBand(1).ReadAsArray(), sorted(keys)


def sentinel_snow(bbox, days):
    """Snow and cloud masks on the Sentinel tile grid, cut to the box, plus the dates behind them."""
    end = datetime.datetime.now(datetime.timezone.utc)
    start = end - datetime.timedelta(days=days)
    when = {"op": "anyinteracts", "args": [{"property": "datetime"}, {"interval": [start.isoformat(), end.isoformat()]}]}
    clear = {"op": "<=", "args": [{"property": "eo:cloud_cover"}, 40]}
    search = {"collections": ["sentinel-2-l2a"], "filter-lang": "cql2-json", "filter": {"op": "and", "args": [when, clear]},
              "sortby": [{"field": "datetime", "direction": "desc"}]}
    mosaic = json.loads(get(f"{TILE_API}/mosaic/register", json.dumps(search).encode()))["searchid"]
    colours = urllib.parse.quote(json.dumps({"11": [255, 255, 255, 255], "8": [100, 100, 100, 255],
                                             "9": [100, 100, 100, 255], "10": [100, 100, 100, 255]}))
    col0, row0, cols, rows, _ = pixel_window(bbox, SNOW_ZOOM)
    tx0, ty0, tx1, ty1 = col0 // 256, row0 // 256, (col0 + cols - 1) // 256, (row0 + rows - 1) // 256
    sheet = np.zeros(((ty1 - ty0 + 1) * 256, (tx1 - tx0 + 1) * 256, 4), np.uint8)
    for ty in range(ty0, ty1 + 1):
        for tx in range(tx0, tx1 + 1):
            png = get(f"{TILE_API}/mosaic/{mosaic}/tiles/WebMercatorQuad/{SNOW_ZOOM}/{tx}/{ty}@1x.png"
                      f"?collection=sentinel-2-l2a&assets=SCL&nodata=0&colormap={colours}")
            sheet[(ty - ty0) * 256:(ty - ty0 + 1) * 256, (tx - tx0) * 256:(tx - tx0 + 1) * 256] = \
                np.asarray(Image.open(io.BytesIO(png)).convert("RGBA"))
    cut = sheet[row0 - ty0 * 256:row0 - ty0 * 256 + rows, col0 - tx0 * 256:col0 - tx0 * 256 + cols]
    opaque = cut[..., 3] > 0
    stac = {"collections": ["sentinel-2-l2a"], "bbox": bbox, "limit": 20, "datetime": f"{start:%Y-%m-%dT%H:%M:%SZ}/{end:%Y-%m-%dT%H:%M:%SZ}",
            "query": {"eo:cloud_cover": {"lte": 40}}, "sortby": [{"field": "datetime", "direction": "desc"}]}
    dates = sorted({f["properties"]["datetime"][:10] for f in json.loads(get(STAC_API, json.dumps(stac).encode()))["features"]}, reverse=True)
    return opaque & (cut[..., 0] > 200), opaque & (cut[..., 0] < 200), dates


def snow_depth(day, lon, lat):
    """SNODAS snow depth in metres at the given longitudes and latitudes (arrays), nearest cell."""
    date = datetime.datetime.strptime(day, "%Y%m%d")
    blob = get(SNODAS.format(y=date.year, m=date.month, mon=date.strftime("%b"), ymd=day))
    with tarfile.open(fileobj=io.BytesIO(blob)) as tar:
        names = {m.name: m for m in tar.getmembers()}
        data_name = next(n for n in names if "ssmv11036tS" in n and n.endswith(".dat.gz"))
        header = gzip.decompress(tar.extractfile(names[data_name.replace(".dat.gz", ".txt.gz")]).read()).decode("latin-1")
        raw = gzip.decompress(tar.extractfile(names[data_name]).read())
    field = lambda label: float(re.search(rf"{label}:\s*([-\d.eE]+)", header).group(1))
    cols, rows = int(field("Number of columns")), int(field("Number of rows"))
    west, north = field("Minimum x-axis coordinate"), field("Maximum y-axis coordinate")
    step, missing = field("X-axis resolution"), field("No data value")
    grid = np.frombuffer(raw, ">i2").reshape(rows, cols)
    c = np.clip(((lon - west) / step).astype(int), 0, cols - 1)
    r = np.clip(((north - lat) / step).astype(int), 0, rows - 1)
    values = grid[r[:, None], c[None, :]].astype(np.float32)
    return np.where(values == missing, 0, values) / 1000


def main():
    p = argparse.ArgumentParser()
    p.add_argument("out")
    p.add_argument("--bbox", type=float, nargs=4, default=[-111.85, 40.50, -111.45, 40.72], metavar=("W", "S", "E", "N"))
    p.add_argument("--snodas", default=(datetime.date.today() - datetime.timedelta(days=1)).strftime("%Y%m%d"))
    p.add_argument("--days", type=int, default=21)
    a = p.parse_args()
    gdal.UseExceptions()
    gdal.SetConfigOption("AWS_NO_SIGN_REQUEST", "YES")
    gdal.SetConfigOption("AWS_REGION", "us-east-1")
    os.makedirs(a.out, exist_ok=True)

    col0, row0, cols, rows, size = pixel_window(a.bbox, ZOOM)
    cols, rows = cols - cols % 4, rows - rows % 4          # whole Sentinel-grid pixels and two equal halves
    fine, keys = canopy(col0, row0, cols, rows, size)       # 2 x 2 canopy samples per output pixel

    lon = np.array([lonlat((col0 + i + 0.5) * size - EARTH / 2, 0)[0] for i in range(cols)])
    lat = np.array([lonlat(0, EARTH / 2 - (row0 + j + 0.5) * size)[1] for j in range(rows)])
    depth = snow_depth(a.snodas, lon, lat)

    blocks = fine.reshape(rows, 2, cols, 2)
    showing = (blocks > depth[:, None, :, None]).mean(axis=(1, 3))        # share of the pixel with vegetation above the snow
    forest = (blocks >= FOREST_M).mean(axis=(1, 3)) > FOREST_SHARE

    snow13, cloud13, dates = sentinel_snow(a.bbox, a.days)
    factor = 2 ** (ZOOM - SNOW_ZOOM)
    scol0, srow0, _, _, _ = pixel_window(a.bbox, SNOW_ZOOM)
    # the Sentinel cut starts on its own pixel grid; place the output grid inside it
    dx, dy = col0 - scol0 * factor, row0 - srow0 * factor
    grow = lambda mask: np.repeat(np.repeat(mask, factor, 0), factor, 1)[dy:dy + rows, dx:dx + cols]
    seen = grow(snow13)
    reach = max(1, round(FILL_M / (size * math.cos(math.radians((a.bbox[1] + a.bbox[3]) / 2)) * factor)))
    y, x = np.ogrid[-reach:reach + 1, -reach:reach + 1]
    around = grow(ndimage.binary_closing(snow13, structure=x * x + y * y <= reach * reach))
    present = seen | (around & forest)

    alpha = np.where(present, 240 * (1 - showing), 0).astype(np.uint8)
    rgba = np.dstack([np.full_like(alpha, c) for c in SNOW_RGB] + [alpha])
    images = []
    for r in range(2):
        for c in range(2):
            y0, y1, x0, x1 = r * rows // 2, (r + 1) * rows // 2, c * cols // 2, (c + 1) * cols // 2
            name = f"winter-{r}{c}.png"
            Image.fromarray(rgba[y0:y1, x0:x1], "RGBA").save(os.path.join(a.out, name), optimize=True)
            corner = lambda i, j: [round(v, 6) for v in lonlat((col0 + i) * size - EARTH / 2, EARTH / 2 - (row0 + j) * size)]
            images.append({"file": name, "corners": [corner(x0, y0), corner(x1, y0), corner(x1, y1), corner(x0, y1)]})

    area = lambda mask: round(float(mask.mean()) * 100, 1)
    info = {"schema": "winter-layer-test@1", "bbox": a.bbox, "zoom": ZOOM, "pixels": [cols, rows], "images": images,
            "sentinel_passes": dates, "sentinel_window_days": a.days, "snodas_day": a.snodas, "canopy_tiles": keys,
            "snow_depth_m": {"lowest": round(float(depth.min()), 2), "median": round(float(np.median(depth)), 2), "highest": round(float(depth.max()), 2)},
            "percent_of_area": {"snow_seen_by_sentinel": area(seen), "snow_added_under_forest": area(present & ~seen),
                                "forest": area(forest), "cloud": area(grow(cloud13)),
                                "drawn_white_at_least_half": area(alpha >= 120)},
            "rule": f"snow present where Sentinel-2 marks snow, or in forest (canopy {FOREST_M} m or more over {int(FOREST_SHARE * 100)}% of the pixel) "
                    f"within {FILL_M} m of snow on all sides; drawn white by the share of the pixel whose canopy is no taller than the snow depth"}
    with open(os.path.join(a.out, "winter.json"), "w") as f:
        json.dump(info, f, indent=1)
    print(json.dumps({k: v for k, v in info.items() if k != "images"}, indent=1))


if __name__ == "__main__":
    main()
