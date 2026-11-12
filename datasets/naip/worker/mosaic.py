#!/usr/bin/env python3
"""Cut tiles on a shared pixel grid from NAIP MRF quads, and assemble them into one file.

Two modes, chosen by MODE:

  tiles     One shard of a tile manifest per task. A tile is a window of TILE_BLOCKS by
            TILE_BLOCKS blocks on the grid of a larger square, cut from the source quads that
            cover it and written as a JPEG COG with log2(TILE_BLOCKS) overview levels. Source
            quads are downloaded whole, as in convert.py, and kept on disk while the next
            tile still needs them.

  assemble  Builds the square's file from its tiles without decoding them: because every
            block of a tile is a block of the square, at full resolution and at each of the
            tile's overview levels, the compressed blocks are copied byte for byte. Only the
            levels coarser than a tile's last one are computed, from the decoded last level.

Local check, no S3:  mosaic.py --selftest <dir>
"""

import collections
import json
import math
import os
import resource
import shutil
import socket
import struct
import sys
import tempfile
import time

import numpy as np
from osgeo import gdal

from convert import Store, cpu_seconds, overview_edges, sha256_of

gdal.UseExceptions()

QUALITY = int(os.environ.get("QUALITY", "75"))
BLOCK = 512
TILE_BLOCKS = int(os.environ.get("TILE_BLOCKS", "32"))
TILE_LEVELS = int(math.log2(TILE_BLOCKS))
OVERVIEW_EDGE_FLOOR = float(os.environ.get("OVERVIEW_EDGE_FLOOR", "0.7"))
assert 2 ** TILE_LEVELS == TILE_BLOCKS, "TILE_BLOCKS must be a power of two"


# ── tiles ────────────────────────────────────────────────────────────────────────────────

def cut_tile(sources, tile, target, threads=1):
    """Write one tile from local source rasters. Returns the VRT path and its window."""
    vrt_path = target + ".vrt"
    vrt = gdal.BuildVRT(vrt_path, sources, bandList=[1, 2, 3])
    gt = vrt.GetGeoTransform()
    res = tile["res"]
    if abs(gt[1] - res) > 1e-9 or abs(gt[5] + res) > 1e-9:
        raise ValueError(f"source pixel size {gt[1]}, {gt[5]} is not {res}")
    xoff, yoff = (tile["col0"] * res - gt[0]) / res, (gt[3] - tile["row0"] * res) / res
    if abs(xoff - round(xoff)) > 1e-6 or abs(yoff - round(yoff)) > 1e-6:
        raise ValueError(f"sources are not on the tile's pixel grid: offsets {xoff}, {yoff}")
    window = [int(round(xoff)), int(round(yoff)), tile["width"], tile["height"]]
    if window[0] < 0 or window[1] < 0 or window[0] + window[2] > vrt.RasterXSize or window[1] + window[3] > vrt.RasterYSize:
        raise ValueError(f"tile window {window} is outside its sources {vrt.RasterXSize} x {vrt.RasterYSize}")
    gdal.Translate(target, vrt, format="COG", srcWin=window, creationOptions=[
        "COMPRESS=JPEG", f"QUALITY={QUALITY}", f"BLOCKSIZE={BLOCK}",
        "OVERVIEW_RESAMPLING=AVERAGE", "OVERVIEWS=IGNORE_EXISTING",
        f"OVERVIEW_COUNT={TILE_LEVELS}", f"NUM_THREADS={threads}"])
    vrt = None
    return vrt_path, window


def describe_tile(path):
    ds = gdal.Open(path)
    band = ds.GetRasterBand(1)
    structure = ds.GetMetadata("IMAGE_STRUCTURE")
    return {"width": ds.RasterXSize, "height": ds.RasterYSize, "bands": ds.RasterCount,
            "geotransform": list(ds.GetGeoTransform()),
            "epsg": ds.GetSpatialRef().GetAuthorityCode(None) if ds.GetSpatialRef() else None,
            "block": list(band.GetBlockSize()), "overviews": band.GetOverviewCount(),
            "compression": structure.get("COMPRESSION"), "layout": structure.get("LAYOUT"),
            "overview_edges": overview_edges(band)}


def check_tile(tile, found):
    problems = []
    res = tile["res"]
    if [found["width"], found["height"]] != [tile["width"], tile["height"]]:
        problems.append(f"size {found['width']} x {found['height']}")
    gt = found["geotransform"]
    if abs(gt[0] - tile["col0"] * res) > 1e-6 or abs(gt[3] - tile["row0"] * res) > 1e-6:
        problems.append(f"origin {gt[0]}, {gt[3]}")
    if str(found["epsg"]) != str(tile["epsg"]):
        problems.append(f"epsg {found['epsg']}")
    if found["layout"] != "COG" or found["compression"] != "YCbCr JPEG" or found["block"] != [BLOCK, BLOCK]:
        problems.append(f"layout {found['layout']} compression {found['compression']} block {found['block']}")
    if found["overviews"] != TILE_LEVELS:
        problems.append(f"overviews {found['overviews']}")
    for level, ratios in enumerate(found["overview_edges"]):
        if min(ratios) < OVERVIEW_EDGE_FLOOR:
            problems.append(f"overview {level + 1} edge darkened: {ratios}")
    return problems


def psnr_window(reference_path, window, candidate_path, rows=512):
    """PSNR in dB per band between a window of the reference and the whole candidate."""
    reference, candidate = gdal.Open(reference_path), gdal.Open(candidate_path)
    x, y, width, height = window
    squares = np.zeros(3, dtype=np.float64)
    for top in range(0, height, rows):
        count = min(rows, height - top)
        a = reference.ReadAsArray(x, y + top, width, count, band_list=[1, 2, 3]).astype(np.int32)
        b = candidate.ReadAsArray(0, top, width, count, band_list=[1, 2, 3]).astype(np.int32)
        d = a - b
        squares += (d * d).sum(axis=(1, 2), dtype=np.float64)
    mean = squares / (width * height)
    return [None if m == 0 else round(float(10 * np.log10(255.0 * 255.0 / m)), 3) for m in mean]


class QuadCache:
    """Source quads on local disk, dropped once no tile still to come needs them."""

    def __init__(self, store):
        self.store, self.dirs, self.bytes, self.seconds = store, {}, 0, 0.0

    def get(self, quad):
        if quad["mrf"] not in self.dirs:
            mark = time.monotonic()
            workdir = tempfile.mkdtemp(prefix="quad-")
            for part in ("mrf", "idx", "lrc"):
                path = os.path.join(workdir, os.path.basename(quad[part]))
                fetch = self.store.fetch if part == "lrc" else self.store.fetch_small
                self.bytes += fetch(quad["src_bucket"], quad[part], path)
            self.dirs[quad["mrf"]] = workdir
            self.seconds += time.monotonic() - mark
        return os.path.join(self.dirs[quad["mrf"]], os.path.basename(quad["mrf"]))

    def keep_only(self, wanted):
        for key in [k for k in self.dirs if k not in wanted]:
            shutil.rmtree(self.dirs.pop(key), ignore_errors=True)


def run_tiles():
    out_bucket, out_prefix = os.environ["OUT_BUCKET"], os.environ.get("OUT_PREFIX", "")
    work_bucket, run_id = os.environ.get("WORK_BUCKET", out_bucket), os.environ["RUN_ID"]
    shard_index, shard_count = int(os.environ.get("SHARD_INDEX", "0")), int(os.environ.get("SHARD_COUNT", "1"))
    limit, sample_every = int(os.environ.get("LIMIT", "0")), int(os.environ.get("SAMPLE_EVERY", "0"))
    deadline = time.monotonic() + int(os.environ.get("DEADLINE_SECONDS", "10800"))
    threads = int(os.environ.get("THREADS", "1"))

    store = Store()
    manifest = store.read_lines(work_bucket, os.environ["MANIFEST_KEY"])
    mine = [(n, t) for n, t in enumerate(manifest) if n % shard_count == shard_index]
    if limit:
        mine = mine[:limit]
    host = socket.gethostname()
    print(f"run {run_id} shard {shard_index}/{shard_count}: {len(mine)} tiles, gdal {gdal.__version__}", flush=True)

    cache = QuadCache(store)
    done = skipped = failed = 0
    for at, (position, tile) in enumerate(mine):
        if time.monotonic() > deadline:
            print("deadline reached, stopping", flush=True)
            return 3
        receipt_key = f"_receipts/{run_id}/{tile['id']}.json"
        workdir = tempfile.mkdtemp(prefix="tile-")
        try:
            store.requests.clear()
            if store.exists(work_bucket, receipt_key):
                skipped += 1
                continue
            started, before_bytes, before_s = time.monotonic(), cache.bytes, cache.seconds
            following = mine[at + 1][1]["sources"] if at + 1 < len(mine) else []
            cache.keep_only({q["mrf"] for q in tile["sources"]} | {q["mrf"] for q in following})
            sources = [cache.get(q) for q in tile["sources"]]
            target = os.path.join(workdir, "out.tif")
            wall, cpu = time.monotonic(), cpu_seconds()
            vrt_path, window = cut_tile(sources, tile, target, threads)
            timing = {"download_s": cache.seconds - before_s, "convert_wall_s": time.monotonic() - wall,
                      "convert_cpu_s": cpu_seconds() - cpu}
            found = describe_tile(target)
            problems = check_tile(tile, found)
            megapixels = tile["width"] * tile["height"] / 1e6
            receipt = {"schema": "folia.naip-grid-tile-receipt@1", "id": tile["id"],
                       "out_uri": f"s3://{out_bucket}/{out_prefix}{tile['out_key']}",
                       "tile": {k: tile[k] for k in ("col0", "row0", "width", "height", "res", "epsg")},
                       "sources": len(tile["sources"]), "source_bytes_downloaded": cache.bytes - before_bytes,
                       "output_bytes": os.path.getsize(target), "output_sha256": sha256_of(target),
                       "megapixels": round(megapixels, 3), "output": found, "problems": problems}
            if sample_every and position % sample_every == 0:
                mark = time.monotonic()
                receipt["psnr_db"] = psnr_window(vrt_path, window, target)
                timing["pixel_check_s"] = time.monotonic() - mark
            if problems:
                raise ValueError(f"tile failed its checks: {problems}")
            mark = time.monotonic()
            store.put_file(out_bucket, out_prefix + tile["out_key"], target)
            timing["upload_s"] = time.monotonic() - mark
            timing["total_s"] = time.monotonic() - started
            receipt.update({"seconds": {k: round(v, 3) for k, v in timing.items()},
                            "megapixels_per_cpu_s": round(megapixels / timing["convert_cpu_s"], 2),
                            "requests": dict(store.requests),
                            "max_rss_kb": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                            "run_id": run_id, "shard": shard_index, "host": host, "gdal": gdal.__version__,
                            "quality": QUALITY, "finished_unix": round(time.time(), 3)})
            store.put_json(work_bucket, receipt_key, receipt)
            done += 1
            print(f"ok {tile['id']} {receipt['output_bytes']} bytes {receipt['seconds']['total_s']} s", flush=True)
        except Exception as error:  # one bad tile must not stop the shard
            failed += 1
            print(f"FAILED {tile['id']}: {error!r}", flush=True)
            store.put_json(work_bucket, f"_errors/{run_id}/{tile['id']}.json",
                           {"id": tile["id"], "run_id": run_id, "shard": shard_index, "error": repr(error)})
        finally:
            shutil.rmtree(workdir, ignore_errors=True)
    print(f"shard {shard_index} finished: {done} converted, {skipped} already done, {failed} failed", flush=True)
    return 1 if failed else 0


# ── assemble ─────────────────────────────────────────────────────────────────────────────

TYPE_BYTES = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 6: 1, 7: 1, 8: 2, 9: 4, 10: 8, 11: 4, 12: 8, 16: 8, 17: 8, 18: 8}
TYPE_CODE = {3: "H", 4: "I", 16: "Q"}
NEW_SUBFILE, WIDTH, LENGTH, TILE_OFFSETS, TILE_COUNTS, JPEG_TABLES = 254, 256, 257, 324, 325, 347
GEO_TAGS = (33550, 33922, 34264, 34735, 34736, 34737)


def read_tiff(path):
    """Header length, the bytes between the header and the first IFD, and every IFD as
    {tag: (type, count, raw bytes)}. Classic TIFF and BigTIFF, little-endian."""
    with open(path, "rb") as f:
        head = f.read(16)
        if head[:2] != b"II":
            raise ValueError(f"{path}: not a little-endian TIFF")
        big = struct.unpack("<H", head[2:4])[0] == 43
        header = 16 if big else 8
        first = struct.unpack("<Q", head[8:16])[0] if big else struct.unpack("<I", head[4:8])[0]
        f.seek(header)
        ghost = f.read(first - header)
        ifds, at = [], first
        while at:
            f.seek(at)
            if big:
                count = struct.unpack("<Q", f.read(8))[0]
                raw, entry = f.read(count * 20 + 8), 20
            else:
                count = struct.unpack("<H", f.read(2))[0]
                raw, entry = f.read(count * 12 + 4), 12
            tags = {}
            for i in range(count):
                e = raw[i * entry:(i + 1) * entry]
                tag, kind = struct.unpack("<HH", e[:4])
                n = struct.unpack("<Q", e[4:12])[0] if big else struct.unpack("<I", e[4:8])[0]
                inline = e[12:20] if big else e[8:12]
                size = TYPE_BYTES[kind] * n
                if size <= len(inline):
                    data = inline[:size]
                else:
                    f.seek(struct.unpack("<Q" if big else "<I", inline)[0])
                    data = f.read(size)
                tags[tag] = (kind, n, data)
            at = struct.unpack("<Q" if big else "<I", raw[count * entry:])[0]
            ifds.append(tags)
    return header, ghost, ifds


def numbers(tags, tag):
    kind, count, data = tags[tag]
    return list(struct.unpack(f"<{count}{TYPE_CODE[kind]}", data))


def halve(a):
    """2 by 2 average of a (bands, rows, cols) array; an odd last row or column is dropped,
    which is the size GDAL gives an overview."""
    bands, rows, cols = a.shape
    even = a[:, :rows - rows % 2, :cols - cols % 2].astype(np.uint16)
    out = even.reshape(bands, rows // 2, 2, cols // 2, 2).sum(axis=(2, 4))
    return ((out + 2) // 4).astype(np.uint8)


def assemble(square, tile_paths, target, workdir):
    """Write the square's COG from its tiles. `tile_paths` maps (row, col) to a local file.

    Returns counts for the receipt. Raises when a tile does not fit the grid.
    """
    width, height, tb = square["width"], square["height"], square["tile_blocks"]
    tile_levels = int(math.log2(tb))
    dims = [(width, height)]
    while max(dims[-1]) > BLOCK:
        dims.append((max(1, dims[-1][0] // 2), max(1, dims[-1][1] // 2)))   # GDAL rounds down
    parsed = {rc: read_tiff(path) for rc, path in tile_paths.items()}
    first = parsed[(0, 0)]

    # levels[k] = {"size", "tags" (to copy), "blocks": [(path, offset, bytes)] row-major}
    levels = []
    for k in range(min(tile_levels, len(dims) - 1) + 1):
        w, h = dims[k]
        across, down, span = math.ceil(w / BLOCK), math.ceil(h / BLOCK), tb >> k
        blocks = [None] * (across * down)
        tables = first[2][k].get(JPEG_TABLES)
        for (row, col), (_, _, ifds) in parsed.items():
            if len(ifds) != tile_levels + 1:
                raise ValueError(f"tile {row},{col}: {len(ifds)} image directories, expected {tile_levels + 1}")
            tags = ifds[k]
            if tags.get(JPEG_TABLES) != tables:
                raise ValueError(f"tile {row},{col} level {k}: JPEG tables differ from tile 0,0")
            tw, th = numbers(tags, WIDTH)[0], numbers(tags, LENGTH)[0]
            want = (min(w - col * span * BLOCK, span * BLOCK), min(h - row * span * BLOCK, span * BLOCK))
            if (tw, th) != want:
                raise ValueError(f"tile {row},{col} level {k}: {tw} x {th}, the grid needs {want[0]} x {want[1]}")
            ta = math.ceil(tw / BLOCK)
            offsets, counts = numbers(tags, TILE_OFFSETS), numbers(tags, TILE_COUNTS)
            for i, (offset, count) in enumerate(zip(offsets, counts)):
                by, bx = row * span + i // ta, col * span + i % ta
                blocks[by * across + bx] = (tile_paths[(row, col)], offset, count)
        if any(b is None for b in blocks):
            raise ValueError(f"level {k}: {sum(b is None for b in blocks)} blocks have no tile")
        levels.append({"size": (w, h), "tags": dict(first[2][k]), "blocks": blocks})

    # Coarser levels: average down from the decoded last tile level, encode with GDAL, copy blocks.
    computed = 0
    if len(dims) - 1 > tile_levels:
        w, h = dims[tile_levels]
        last = np.zeros((3, h, w), dtype=np.uint8)
        span = BLOCK  # a full tile is exactly one block at its last level
        for (row, col), path in tile_paths.items():
            ds = gdal.Open(path)
            ov = [ds.GetRasterBand(b).GetOverview(tile_levels - 1) if tile_levels else ds.GetRasterBand(b) for b in (1, 2, 3)]
            a = np.stack([o.ReadAsArray() for o in ov])
            last[:, row * span:row * span + a.shape[1], col * span:col * span + a.shape[2]] = a
        for k in range(tile_levels + 1, len(dims)):
            last = halve(last)
            if (last.shape[2], last.shape[1]) != dims[k]:
                raise ValueError(f"level {k}: averaged to {last.shape[2]} x {last.shape[1]}, expected {dims[k]}")
            path = os.path.join(workdir, f"level-{k}.tif")
            mem = gdal.GetDriverByName("MEM").Create("", last.shape[2], last.shape[1], 3, gdal.GDT_Byte)
            for b in range(3):
                mem.GetRasterBand(b + 1).WriteArray(last[b])
            gdal.GetDriverByName("GTiff").CreateCopy(path, mem, options=[
                "TILED=YES", f"BLOCKXSIZE={BLOCK}", f"BLOCKYSIZE={BLOCK}", "COMPRESS=JPEG",
                "PHOTOMETRIC=YCBCR", f"JPEG_QUALITY={QUALITY}"])
            _, _, ifds = read_tiff(path)
            tags = {t: v for t, v in ifds[0].items() if t not in GEO_TAGS}
            tags[NEW_SUBFILE] = (4, 1, struct.pack("<I", 1))
            offsets, counts = numbers(tags, TILE_OFFSETS), numbers(tags, TILE_COUNTS)
            levels.append({"size": dims[k], "tags": tags, "blocks": [(path, o, c) for o, c in zip(offsets, counts)]})
            computed += 1

    # Layout: header, GDAL's note on the block layout, every IFD, their long values, then the
    # blocks from the coarsest level to full resolution, each between a 4-byte size and a
    # copy of its last 4 bytes (what GDAL's COG driver writes, and what the note declares).
    ghost = first[1]
    if b"BLOCK_LEADER=SIZE_AS_UINT4" not in ghost or b"BLOCK_TRAILER=LAST_4_BYTES_REPEATED" not in ghost:
        raise ValueError("tile 0,0 does not declare GDAL's block leader and trailer")
    entries = []
    for level in levels:
        tags = dict(level["tags"])
        w, h = level["size"]
        tags[WIDTH], tags[LENGTH] = (4, 1, struct.pack("<I", w)), (4, 1, struct.pack("<I", h))
        n = len(level["blocks"])
        tags[TILE_OFFSETS] = (16, n, None)
        tags[TILE_COUNTS] = (16, n, struct.pack(f"<{n}Q", *[c for _, _, c in level["blocks"]]))
        entries.append(sorted(tags.items()))
    at = 16 + len(ghost)
    at += -at % 8
    first_ifd, ifd_at = at, []
    for tags in entries:
        ifd_at.append(at)
        at += 8 + 20 * len(tags) + 8
    value_at = {}
    for i, tags in enumerate(entries):
        for tag, (kind, count, data) in tags:
            if TYPE_BYTES[kind] * count > 8:
                value_at[(i, tag)] = at
                at += TYPE_BYTES[kind] * count
                at += -at % 8
    block_at = [None] * len(levels)
    for i in reversed(range(len(levels))):
        placed = []
        for _, _, count in levels[i]["blocks"]:
            placed.append(at + 4)
            at += 4 + count + 4
        block_at[i] = placed
    total = at

    handles = {}
    with open(target, "wb") as out:
        out.write(b"II" + struct.pack("<HHHQ", 43, 8, 0, first_ifd))
        out.write(ghost)
        out.write(b"\0" * (first_ifd - out.tell()))
        for i, tags in enumerate(entries):
            out.write(struct.pack("<Q", len(tags)))
            for tag, (kind, count, data) in tags:
                if tag == TILE_OFFSETS:
                    data = struct.pack(f"<{count}Q", *block_at[i])
                size = TYPE_BYTES[kind] * count
                field = data.ljust(8, b"\0") if size <= 8 else struct.pack("<Q", value_at[(i, tag)])
                out.write(struct.pack("<HHQ", tag, kind, count) + field)
            out.write(struct.pack("<Q", ifd_at[i + 1] if i + 1 < len(entries) else 0))
        for i, tags in enumerate(entries):
            for tag, (kind, count, data) in tags:
                if (i, tag) in value_at:
                    if tag == TILE_OFFSETS:
                        data = struct.pack(f"<{count}Q", *block_at[i])
                    out.write(b"\0" * (value_at[(i, tag)] - out.tell()))
                    out.write(data)
        for i in reversed(range(len(levels))):
            for (path, offset, count), where in zip(levels[i]["blocks"], block_at[i]):
                out.write(b"\0" * (where - 4 - out.tell()))
                handle = handles.get(path) or handles.setdefault(path, open(path, "rb"))
                handle.seek(offset)
                payload = handle.read(count)
                out.write(struct.pack("<I", count) + payload + payload[-4:])
        if out.tell() != total:
            raise ValueError(f"wrote {out.tell()} bytes, laid out {total}")
    for handle in handles.values():
        handle.close()
    return {"levels": len(levels), "copied_levels": len(levels) - computed, "computed_levels": computed,
            "blocks": sum(len(l["blocks"]) for l in levels), "bytes": total}


def compare_levels(big_path, tile_path, row, col, tb, rows=BLOCK):
    """Largest absolute pixel difference between a tile and the same window of the big file,
    at full resolution and each of the tile's overview levels."""
    big, tile = gdal.Open(big_path), gdal.Open(tile_path)
    worst = []
    for k in range(int(math.log2(tb)) + 1):
        get = (lambda ds, b: ds.GetRasterBand(b)) if k == 0 else (lambda ds, b: ds.GetRasterBand(b).GetOverview(k - 1))
        span = (tb >> k) * BLOCK
        width, height = get(tile, 1).XSize, get(tile, 1).YSize
        level_worst = 0
        for top in range(0, height, rows):
            count = min(rows, height - top)
            for b in (1, 2, 3):
                a = get(tile, b).ReadAsArray(0, top, width, count).astype(np.int16)
                c = get(big, b).ReadAsArray(col * span, row * span + top, width, count).astype(np.int16)
                level_worst = max(level_worst, int(np.abs(a - c).max()))
        worst.append(level_worst)
    return worst


def validate_cog(path):
    """GDAL's own COG validator when it is installed: (errors, warnings), or None."""
    try:
        from osgeo_utils.samples import validate_cloud_optimized_geotiff as v
    except Exception:
        return None
    warnings, errors, _ = v.validate(path, full_check=True)
    return {"errors": list(errors), "warnings": list(warnings)}


def run_assemble():
    out_bucket, out_prefix = os.environ["OUT_BUCKET"], os.environ.get("OUT_PREFIX", "")
    work_bucket, run_id = os.environ.get("WORK_BUCKET", out_bucket), os.environ["RUN_ID"]
    store = Store()
    square = json.loads(store.client.get_object(Bucket=work_bucket, Key=os.environ["SQUARE_KEY"])["Body"].read())
    receipt_key = f"_receipts/{run_id}/{square['id']}.json"
    if store.exists(work_bucket, receipt_key):
        print("already assembled", flush=True)
        return 0
    workdir = tempfile.mkdtemp(prefix="square-")
    timing, mark = {}, time.monotonic()
    paths, tile_bytes = {}, 0
    for t in square["tiles"]:
        path = os.path.join(workdir, f"t-{t['row']}-{t['col']}.tif")
        store.client.download_file(t["bucket"], t["key"], path, Config=store.download)
        paths[(t["row"], t["col"])] = path
        tile_bytes += os.path.getsize(path)
    timing["download_s"] = time.monotonic() - mark
    target = os.path.join(workdir, "square.tif")
    wall, cpu = time.monotonic(), cpu_seconds()
    counts = assemble(square, paths, target, workdir)
    timing["assemble_wall_s"], timing["assemble_cpu_s"] = time.monotonic() - wall, cpu_seconds() - cpu

    mark = time.monotonic()
    ds = gdal.Open(target)
    found = {"width": ds.RasterXSize, "height": ds.RasterYSize, "geotransform": list(ds.GetGeoTransform()),
             "epsg": ds.GetSpatialRef().GetAuthorityCode(None) if ds.GetSpatialRef() else None,
             "overviews": ds.GetRasterBand(1).GetOverviewCount(),
             "layout": ds.GetMetadata("IMAGE_STRUCTURE").get("LAYOUT"),
             "compression": ds.GetMetadata("IMAGE_STRUCTURE").get("COMPRESSION")}
    ds = None
    every = max(1, len(paths) // int(os.environ.get("COMPARE_TILES", "12")))
    compared = {f"{r}-{c}": compare_levels(target, paths[(r, c)], r, c, square["tile_blocks"])
                for r, c in sorted(paths)[::every]}
    timing["compare_s"] = time.monotonic() - mark
    mark = time.monotonic()
    validator = validate_cog(target)
    timing["validate_s"] = time.monotonic() - mark
    problems = []
    if [found["width"], found["height"]] != [square["width"], square["height"]]:
        problems.append(f"size {found['width']} x {found['height']}")
    if found["layout"] != "COG":
        problems.append(f"layout {found['layout']}")
    if any(max(v) for v in compared.values()):
        problems.append("copied levels differ from the tiles")
    if validator and validator["errors"]:
        problems.append(f"validator: {validator['errors']}")
    receipt = {"schema": "folia.naip-grid-square-receipt@1", "id": square["id"], "run_id": run_id,
               "out_uri": f"s3://{out_bucket}/{out_prefix}{square['out_key']}", "tiles": len(paths),
               "tile_bytes": tile_bytes, "output_bytes": os.path.getsize(target), "assembled": counts,
               "output": found, "compared_max_abs_difference": compared, "validator": validator,
               "problems": problems, "quality": QUALITY, "gdal": gdal.__version__,
               "max_rss_kb": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
    if not problems:
        mark = time.monotonic()
        receipt["output_sha256"] = sha256_of(target)
        store.put_file(out_bucket, out_prefix + square["out_key"], target)
        timing["upload_s"] = time.monotonic() - mark
    receipt["seconds"] = {k: round(v, 3) for k, v in timing.items()}
    receipt["finished_unix"] = round(time.time(), 3)
    store.put_json(work_bucket, receipt_key if not problems else f"_errors/{run_id}/{square['id']}.json", receipt)
    print(json.dumps({k: receipt[k] for k in ("output_bytes", "assembled", "problems", "seconds")}), flush=True)
    shutil.rmtree(workdir, ignore_errors=True)
    return 1 if problems else 0


# ── local self-test ──────────────────────────────────────────────────────────────────────

def selftest(workdir):
    """Cut a synthetic mosaic into tiles, assemble, and compare with the tiles and with a
    COG that GDAL builds directly from the same pixels."""
    os.makedirs(workdir, exist_ok=True)
    rng = np.random.default_rng(7)
    tb, res = TILE_BLOCKS, 0.6
    width, height = tb * BLOCK * 2 + 300, tb * BLOCK + 813          # 3 by 2 tiles, partial edges
    col0, row0 = 1000, 9000000
    yy, xx = np.mgrid[0:height, 0:width]
    base = np.stack([(np.sin(xx / 37.0) + np.cos(yy / 53.0)) * 60 + 120, (np.sin((xx + yy) / 91.0)) * 80 + 110,
                     (np.cos(xx / 11.0) * np.sin(yy / 17.0)) * 50 + 100])
    data = np.clip(base + rng.normal(0, 6, base.shape), 0, 255).astype(np.uint8)
    source = os.path.join(workdir, "source.tif")
    ds = gdal.GetDriverByName("GTiff").Create(source, width, height, 3, gdal.GDT_Byte, options=["TILED=YES", "COMPRESS=DEFLATE"])
    ds.SetGeoTransform([col0 * res, res, 0, row0 * res, 0, -res])
    from osgeo import osr
    srs = osr.SpatialReference(); srs.ImportFromEPSG(26912); ds.SetProjection(srs.ExportToWkt())
    for b in range(3):
        ds.GetRasterBand(b + 1).WriteArray(data[b])
    ds = None
    span = tb * BLOCK
    paths = {}
    for row in range(math.ceil(height / span)):
        for col in range(math.ceil(width / span)):
            tile = {"col0": col0 + col * span, "row0": row0 - row * span, "res": res, "epsg": 26912,
                    "width": min(span, width - col * span), "height": min(span, height - row * span)}
            path = os.path.join(workdir, f"t-{row}-{col}.tif")
            vrt, window = cut_tile([source], tile, path)
            problems = check_tile(tile, describe_tile(path))
            assert not problems, problems
            paths[(row, col)] = path
    square = {"width": width, "height": height, "tile_blocks": tb}
    target = os.path.join(workdir, "square.tif")
    counts = assemble(square, paths, target, workdir)
    worst = {f"{r}-{c}": compare_levels(target, p, r, c, tb) for (r, c), p in paths.items()}
    direct = os.path.join(workdir, "direct.tif")
    gdal.Translate(direct, source, format="COG", creationOptions=[
        "COMPRESS=JPEG", f"QUALITY={QUALITY}", f"BLOCKSIZE={BLOCK}", "OVERVIEW_RESAMPLING=AVERAGE", "BIGTIFF=YES"])
    a, b = gdal.Open(target), gdal.Open(direct)
    against_direct = []
    for k in range(a.GetRasterBand(1).GetOverviewCount() + 1):
        get = (lambda ds: ds.GetRasterBand(1)) if k == 0 else (lambda ds: ds.GetRasterBand(1).GetOverview(k - 1))
        if k > b.GetRasterBand(1).GetOverviewCount():
            against_direct.append(None)
            continue
        x, y = get(a).ReadAsArray().astype(np.int16), get(b).ReadAsArray().astype(np.int16)
        against_direct.append(None if x.shape != y.shape else int(np.abs(x - y).max()))
    print(json.dumps({"assembled": counts, "layout": a.GetMetadata("IMAGE_STRUCTURE").get("LAYOUT"),
                      "overviews": [a.GetRasterBand(1).GetOverviewCount(), b.GetRasterBand(1).GetOverviewCount()],
                      "sizes": [os.path.getsize(target), os.path.getsize(direct), sum(os.path.getsize(p) for p in paths.values())],
                      "max_abs_difference_from_tiles": worst, "max_abs_difference_from_direct_by_level": against_direct,
                      "geotransform_equal": a.GetGeoTransform() == b.GetGeoTransform(),
                      "validator": validate_cog(target)}, indent=1))


def main():
    return run_assemble() if os.environ.get("MODE") == "assemble" else run_tiles()


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--selftest":
        selftest(sys.argv[2])
    else:
        sys.exit(main())
