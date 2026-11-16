#!/usr/bin/env python3
"""Build a STAC-GeoParquet index of converted quads from one or more runs' receipts.

One row per file, as a STAC item: footprint in longitude and latitude, the date flown, the
file's own CRS and extent (projection extension), one asset, `image`, with the file's URL,
size and checksum, and one link, `derived_from`, to the source file. The collection is kept in
the file's `stac-geoparquet` metadata (specification 1.1.0).

Layout, chosen by measuring what a map reads to open a view (index_variants.py and the explorer's
index-read-cost.mjs):

  * Rows run along a Hilbert curve through the footprint centres, newest first where rows share a
    place, so the rows of one area sit together whatever their year.
  * Row groups are large (8,192 rows), which keeps the footer a reader must fetch first small, and
    each is written as pages of 128 rows with Parquet's page index: the bounds and address of every
    page. A reader that uses the page index takes only the pages in view. One that does not takes
    whole row groups, sixteen times the rows the earlier 512-row groups gave it.
  * Only columns with few distinct values keep a dictionary. A dictionary is one block per row
    group, and a reader taking one page would have to take all of it.

--from-index writes an existing index again in this layout: the same schema and metadata.

A year in which only part of a state was flown again is not listed (partial_years.py), so a
reader that draws the newest file over a place gets one flight per state. Its files are still
at the addresses the other rows follow. --keep-partial-years lists them.

    uv run --no-project --with pyarrow==21.0.0 --with pyproj==3.7.2 \
        python build_stac_index.py <out.parquet> <receipts dir> [<receipts dir> ...] \
        [--base-url https://data.source.coop/nthh/naip/] [--row-group 8192] [--page-rows 128] \
        [--sort hilbert|yearhilbert|name] \
        [--overviews https://data.source.coop/nthh/naip/stac/naip-overviews.parquet] [--keep-partial-years]
    ... python build_stac_index.py <out.parquet> --from-index <existing index.parquet>
"""

import argparse
import datetime
import json
import os

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq
from pyproj import Transformer

from build_index import footprint, wkb_polygon
from partial_years import counts_of, partial

EXTENSIONS = [
    "https://stac-extensions.github.io/projection/v2.0.0/schema.json",
    "https://stac-extensions.github.io/file/v2.1.0/schema.json",
]


def hilbert(lon, lat, order=16):
    """Distance along a Hilbert curve of 2**order cells per side over the whole lon/lat plane."""
    n = 1 << order
    x = min(n - 1, max(0, int((lon + 180.0) / 360.0 * n)))
    y = min(n - 1, max(0, int((lat + 90.0) / 180.0 * n)))
    d, s = 0, n >> 1
    while s:
        rx, ry = int(bool(x & s)), int(bool(y & s))
        d += s * s * ((3 * rx) ^ ry)
        if ry == 0:
            if rx == 1:
                x, y = n - 1 - x, n - 1 - y
            x, y = y, x
        s >>= 1
    return d


def order(table, how):
    """The table's rows in the wanted order."""
    if how == "name":
        keys = zip(table["naip:state"].to_pylist(), table["naip:year"].to_pylist(), table["id"].to_pylist())
    else:
        bbox = table["bbox"].combine_chunks()
        lon = pc.divide(pc.add(bbox.field("xmin"), bbox.field("xmax")), 2).to_pylist()
        lat = pc.divide(pc.add(bbox.field("ymin"), bbox.field("ymax")), 2).to_pylist()
        place = [hilbert(x, y) for x, y in zip(lon, lat)]
        when = table["datetime"].cast(pa.int64()).to_pylist()
        if how == "yearhilbert":      # the layout before November 2026: one curve per year
            keys = zip(table["naip:year"].to_pylist(), place, table["id"].to_pylist())
        else:
            keys = zip(place, [-t for t in when], table["id"].to_pylist())
    keys = list(keys)
    return table.take(pa.array(sorted(range(table.num_rows), key=keys.__getitem__)))


def collection(rows, links):
    """The STAC Collection these items belong to, kept in the file's own metadata."""
    days = [r["datetime"] for r in rows]
    return {
        "type": "Collection", "stac_version": "1.1.0", "stac_extensions": [], "id": "naip",
        "title": "NAIP display copies",
        "description": "RGB JPEG Cloud-Optimized GeoTIFFs of USDA National Agriculture Imagery Program quarter "
                       "quads, one item per file, converted from the four-band files in s3://naip-analytic. "
                       "NAIP imagery is in the public domain and USDA asks for credit; these files are a format "
                       "conversion, not a USDA product.",
        "license": "other",
        "providers": [{"name": "USDA Farm Production and Conservation Business Center", "roles": ["producer", "licensor"],
                       "url": "https://naip-usdaonline.hub.arcgis.com/"}],
        "extent": {"spatial": {"bbox": [[min(r["bbox"]["xmin"] for r in rows), min(r["bbox"]["ymin"] for r in rows),
                                         max(r["bbox"]["xmax"] for r in rows), max(r["bbox"]["ymax"] for r in rows)]]},
                   "temporal": {"interval": [[min(days).strftime("%Y-%m-%dT%H:%M:%SZ"),
                                              max(days).strftime("%Y-%m-%dT%H:%M:%SZ")]]}},
        "summaries": {"gsd": sorted({r["gsd"] for r in rows}), "naip:state": sorted({r["naip:state"] for r in rows}),
                      "naip:year": sorted({r["naip:year"] for r in rows}),
                      "proj:code": sorted({r["proj:code"] for r in rows})},
        "item_assets": {"image": {"type": "image/tiff; application=geotiff; profile=cloud-optimized",
                                  "roles": ["data", "visual"], "title": "RGB JPEG Cloud-Optimized GeoTIFF"}},
        "links": links,
    }


# Leaf columns with few distinct values, which keep a dictionary in a paged file.
FEW_VALUES = ["stac_version", "stac_extensions.list.element", "collection", "gsd", "naip:state", "naip:year",
              "proj:code", "proj:epsg", "proj:shape.list.element", "links.list.element.rel",
              "links.list.element.title", "assets.image.roles.list.element", "assets.image.title",
              "assets.image.type", "naip:run"]
# Statistics only on the columns a reader filters by: on every column they are most of the
# footer, which a reader fetches whole before anything else.
STATISTICS = ["bbox.xmin", "bbox.ymin", "bbox.xmax", "bbox.ymax", "datetime", "naip:year"]


def table_of(rows, links):
    table = pa.Table.from_pylist(rows)
    # GeoParquet's bbox covering wants the struct's fields in this order; inferred structs come out
    # alphabetical.
    names = ("xmin", "ymin", "xmax", "ymax")
    bbox = pa.StructArray.from_arrays([pa.array([r["bbox"][k] for r in rows], pa.float64()) for k in names], names=names)
    table = table.set_column(table.schema.get_field_index("bbox"), "bbox", bbox)
    geo = {"version": "1.1.0", "primary_column": "geometry", "columns": {"geometry": {
        "encoding": "WKB", "geometry_types": ["Polygon"],
        "bbox": [min(r["bbox"]["xmin"] for r in rows), min(r["bbox"]["ymin"] for r in rows),
                 max(r["bbox"]["xmax"] for r in rows), max(r["bbox"]["ymax"] for r in rows)],
        "covering": {"bbox": {k: ["bbox", k] for k in ("xmin", "ymin", "xmax", "ymax")}}}}}
    stac = {"version": "1.1.0", "collections": {"naip": collection(rows, links)}}
    return table.replace_schema_metadata({"geo": json.dumps(geo), "stac-geoparquet": json.dumps(stac)})


def write(table, out, row_group, page_rows):
    paged = {} if not page_rows else {"write_page_index": True, "data_page_size": 1, "write_batch_size": page_rows,
                                      "use_dictionary": FEW_VALUES}
    pq.write_table(table, out, row_group_size=row_group, compression="zstd", write_statistics=STATISTICS, **paged)


def item(receipt, base_url, transformers):
    key = receipt["out_uri"].split("/", 3)[3]
    # <state>/<year>/<res>/rgb/<block>/m_<quad>_<quarter>_<zone>_<res>_<yyyymmdd flown>[_<yyyymmdd made>].tif
    path = "/".join(key.split("/")[-6:])
    state, year, resolution, _, _, filename = path.split("/")
    flown = filename[:-4].split("_")[5]      # a 2023 name carries a second date after it, the day the file was made
    ring, native = footprint(receipt, transformers)
    out = receipt["output"]
    sha = receipt.get("output_sha256")
    return {
        "stac_version": "1.1.0",
        "stac_extensions": EXTENSIONS,
        "id": receipt["id"],
        "collection": "naip",
        "geometry": wkb_polygon(ring),
        "bbox": {"xmin": min(p[0] for p in ring), "ymin": min(p[1] for p in ring),
                 "xmax": max(p[0] for p in ring), "ymax": max(p[1] for p in ring)},
        "datetime": datetime.datetime(int(flown[:4]), int(flown[4:6]), int(flown[6:]),
                                      tzinfo=datetime.timezone.utc),
        "gsd": int(resolution[:-2]) / 100,
        "naip:state": state,
        "naip:year": int(year),
        "proj:code": f"EPSG:{out['epsg']}",
        "proj:epsg": int(out["epsg"]),
        "proj:bbox": native,
        "proj:shape": [out["height"], out["width"]],
        "proj:transform": [out["geotransform"][i] for i in (1, 2, 0, 4, 5, 3)],
        "links": [{"rel": "derived_from", "title": "Source four-band MRF (requester pays)",
                   "href": f"s3://naip-analytic/{state}/{year}/{resolution}/rgbir/{key.split('/')[-2]}/{filename[:-4]}.mrf"}],
        "assets": {"image": {
            "href": base_url + path,
            "type": "image/tiff; application=geotiff; profile=cloud-optimized",
            "roles": ["data", "visual"],
            "title": "RGB JPEG Cloud-Optimized GeoTIFF",
            "file:size": receipt["output_bytes"],
            "file:checksum": None if not sha else "1220" + sha,
        }},
        "naip:run": receipt["run_id"],
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("out")
    p.add_argument("receipts_dirs", nargs="*")
    p.add_argument("--from-index", help="an existing index to write again in this layout, in place of receipts")
    p.add_argument("--base-url", default="https://data.source.coop/nthh/naip/")
    p.add_argument("--row-group", type=int, default=8192)
    p.add_argument("--page-rows", type=int, default=128, help="rows a page; 0 writes one page per column and no page index")
    p.add_argument("--sort", choices=["hilbert", "yearhilbert", "name"], default="hilbert")
    p.add_argument("--overviews", help="URL of the index of overview files; kept as a link in the collection")
    p.add_argument("--keep-partial-years", action="store_true", help="list the years that cover only part of a state")
    a = p.parse_args()

    left_out = {}
    if a.from_index:
        with open(a.from_index, "rb") as f:
            table = pq.ParquetFile(f).read()
        pairs = list(zip(table["naip:state"].to_pylist(), table["naip:year"].to_pylist()))
        drop = set() if a.keep_partial_years else partial(counts_of(*zip(*pairs)))
        left_out = {f"{s}-{y}": pairs.count((s, y)) for s, y in sorted(drop)}
        table = table.filter(pa.array([pair not in drop for pair in pairs]))
    else:
        rows, transformers = [], {}
        for d in a.receipts_dirs:
            for name in sorted(os.listdir(d)):
                if name.endswith(".json"):
                    with open(os.path.join(d, name)) as f:
                        rows.append(item(json.load(f), a.base_url, transformers))
        pairs = [(r["naip:state"], r["naip:year"]) for r in rows]
        drop = set() if a.keep_partial_years else partial(counts_of(*zip(*pairs)))
        left_out = {f"{s}-{y}": pairs.count((s, y)) for s, y in sorted(drop)}
        rows = [r for r, pair in zip(rows, pairs) if pair not in drop]
        links = [] if not a.overviews else [{
            "rel": "overviews", "href": a.overviews, "type": "application/vnd.apache.parquet",
            "title": "Reduced pictures of whole states and of the country, one item per file (STAC GeoParquet)"}]
        table = table_of(rows, links)
    write(order(table, a.sort), a.out, a.row_group, a.page_rows)
    with open(a.out, "rb") as f:
        f.seek(-8, os.SEEK_END)
        footer = int.from_bytes(f.read(4), "little")
    print(json.dumps({"rows": table.num_rows, "partial_years_left_out": left_out, "bytes": os.path.getsize(a.out), "footer_bytes": footer,
                      "row_groups": pq.ParquetFile(a.out).num_row_groups,
                      "epsg": sorted(set(table["proj:epsg"].to_pylist()))}))


if __name__ == "__main__":
    main()
