#!/usr/bin/env python3
"""Convert NAIP MRF quads to RGB JPEG COGs, one shard of a manifest per task.

Each quad is downloaded whole to local disk, converted with GDAL, checked, uploaded,
and recorded in one receipt object (sizes, timings, request counts, checks and the
output's SHA-256). A quad whose receipt exists is skipped, so a task stopped by a Spot
interruption is repeated by launching the same shard again. The receipt's request count
leaves out one request: the PUT of the receipt itself.

The next quad's source files download on a second thread while the current quad converts
(OVERLAP_DOWNLOADS=0 turns that off). Conversion is single-threaded and the first run spent a
quarter of its task time waiting on downloads with the CPU idle.

Reads are whole-object downloads, not GDAL range reads, so the request count per quad
is fixed by the part size and not by GDAL's read pattern. Requests were 38% of the first
run's bill, so the data file comes down in 128 MiB parts, the two small files in one
request each, and the output goes up in one request.

Local check, no S3:  convert.py --local <source raster> <output.tif>
"""

import collections
import concurrent.futures
import hashlib
import json
import os
import resource
import shutil
import socket
import sys
import tempfile
import time

import numpy as np
from osgeo import gdal

gdal.UseExceptions()

QUALITY = int(os.environ.get("QUALITY", "85"))
BLOCKSIZE = int(os.environ.get("BLOCKSIZE", "512"))
OVERVIEW_RESAMPLING = os.environ.get("OVERVIEW_RESAMPLING", "AVERAGE")
DOWNLOAD_PART_BYTES = 128 * 1024 * 1024
SINGLE_PUT_BYTES = 1024 * 1024 * 1024  # an output below this goes up in one request
OVERLAP_DOWNLOADS = os.environ.get("OVERLAP_DOWNLOADS", "1") != "0"


def cpu_seconds():
    usage = resource.getrusage(resource.RUSAGE_SELF)
    return usage.ru_utime + usage.ru_stime


def convert(source, target):
    """Write bands 1 to 3 of `source` as a JPEG COG. Returns wall and CPU seconds."""
    wall, cpu = time.monotonic(), cpu_seconds()
    gdal.Translate(
        target,
        source,
        format="COG",
        bandList=[1, 2, 3],
        creationOptions=[
            "COMPRESS=JPEG",
            f"QUALITY={QUALITY}",
            f"BLOCKSIZE={BLOCKSIZE}",
            f"OVERVIEW_RESAMPLING={OVERVIEW_RESAMPLING}",
            "NUM_THREADS=1",
        ],
    )
    return time.monotonic() - wall, cpu_seconds() - cpu


def describe(path):
    ds = gdal.Open(path)
    band = ds.GetRasterBand(1)
    structure = ds.GetMetadata("IMAGE_STRUCTURE")
    return {
        "width": ds.RasterXSize,
        "height": ds.RasterYSize,
        "bands": ds.RasterCount,
        "geotransform": list(ds.GetGeoTransform()),
        "epsg": ds.GetSpatialRef().GetAuthorityCode(None) if ds.GetSpatialRef() else None,
        "block": list(band.GetBlockSize()),
        "overviews": band.GetOverviewCount(),
        "compression": structure.get("COMPRESSION"),
        "layout": structure.get("LAYOUT"),
        "jpeg_quality": structure.get("JPEG_QUALITY"),
    }


def check(source, target):
    """Reasons the output is not a faithful COG of the source; empty when it is."""
    problems = []
    for field in ("width", "height", "geotransform", "epsg"):
        if source[field] != target[field]:
            problems.append(f"{field}: source {source[field]} output {target[field]}")
    if target["bands"] != 3:
        problems.append(f"bands: {target['bands']}")
    if target["layout"] != "COG":
        problems.append(f"layout: {target['layout']}")
    if target["compression"] != "YCbCr JPEG":
        problems.append(f"compression: {target['compression']}")
    if target["block"] != [BLOCKSIZE, BLOCKSIZE]:
        problems.append(f"block: {target['block']}")
    if target["overviews"] < 1:
        problems.append("no overviews")
    return problems


def psnr(reference_path, candidate_path, rows=512):
    """Peak signal-to-noise ratio in dB per band (red, green, blue) at full resolution."""
    reference, candidate = gdal.Open(reference_path), gdal.Open(candidate_path)
    width, height = reference.RasterXSize, reference.RasterYSize
    squares = np.zeros(3, dtype=np.float64)
    for top in range(0, height, rows):
        count = min(rows, height - top)
        a = reference.ReadAsArray(0, top, width, count, band_list=[1, 2, 3]).astype(np.int32)
        b = candidate.ReadAsArray(0, top, width, count, band_list=[1, 2, 3]).astype(np.int32)
        difference = a - b
        squares += (difference * difference).sum(axis=(1, 2), dtype=np.float64)
    mean = squares / (width * height)
    return [None if m == 0 else round(float(10 * np.log10(255.0 * 255.0 / m)), 3) for m in mean]


def local(source, target):
    wall, cpu = convert(source, target)
    before, after = describe(source), describe(target)
    megapixels = before["width"] * before["height"] / 1e6
    print(json.dumps({
        "source": before,
        "output": after,
        "output_bytes": os.path.getsize(target),
        "problems": check(before, after),
        "convert_wall_s": round(wall, 3),
        "convert_cpu_s": round(cpu, 3),
        "megapixels_per_cpu_s": round(megapixels / cpu, 2),
        "psnr_db": psnr(source, target),
        "max_rss_kb": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "gdal": gdal.__version__,
    }, indent=1))


class Store:
    """S3 access that counts every HTTP request by operation."""

    def __init__(self):
        import boto3
        from boto3.s3.transfer import TransferConfig

        self.client = boto3.client("s3")
        self.requests = collections.Counter()
        self.client.meta.events.register("before-send.s3.*", self._count)
        self.download = TransferConfig(
            multipart_threshold=DOWNLOAD_PART_BYTES, multipart_chunksize=DOWNLOAD_PART_BYTES,
            max_concurrency=4,
        )
        self.upload = TransferConfig(
            multipart_threshold=SINGLE_PUT_BYTES, multipart_chunksize=DOWNLOAD_PART_BYTES,
            max_concurrency=4,
        )

    def _count(self, event_name, **_):
        self.requests[event_name.rsplit(".", 1)[-1]] += 1

    def exists(self, bucket, key):
        from botocore.exceptions import ClientError

        try:
            self.client.head_object(Bucket=bucket, Key=key)
            return True
        except ClientError as error:
            if error.response["Error"]["Code"] in ("404", "NoSuchKey", "NotFound"):
                return False
            raise

    def fetch(self, bucket, key, path):
        """Download a requester-pays object; returns its size."""
        self.client.download_file(
            bucket, key, path, ExtraArgs={"RequestPayer": "requester"}, Config=self.download
        )
        return os.path.getsize(path)

    def fetch_small(self, bucket, key, path):
        """Download a small requester-pays object in one request; returns its size."""
        body = self.client.get_object(Bucket=bucket, Key=key, RequestPayer="requester")["Body"]
        with open(path, "wb") as out:
            shutil.copyfileobj(body, out)
        return os.path.getsize(path)

    def put_file(self, bucket, key, path):
        self.client.upload_file(
            path, bucket, key, ExtraArgs={"ContentType": "image/tiff"}, Config=self.upload
        )

    def put_json(self, bucket, key, value):
        self.client.put_object(
            Bucket=bucket, Key=key, Body=json.dumps(value, indent=1).encode(),
            ContentType="application/json",
        )

    def read_lines(self, bucket, key):
        body = self.client.get_object(Bucket=bucket, Key=key)["Body"].read().decode()
        return [json.loads(line) for line in body.splitlines() if line.strip()]


def sha256_of(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def fetch_quad(fetcher, work_bucket, receipt_key, quad):
    """Download one quad's source files. Returns None when its receipt already exists.

    Runs on the download thread with its own Store, so its request count is this quad's alone.
    """
    fetcher.requests.clear()
    if fetcher.exists(work_bucket, receipt_key):
        return None
    workdir = tempfile.mkdtemp(prefix="quad-")
    try:
        mark, sizes = time.monotonic(), {}
        for part in ("mrf", "idx", "lrc"):
            path = os.path.join(workdir, os.path.basename(quad[part]))
            fetch = fetcher.fetch if part == "lrc" else fetcher.fetch_small
            sizes[part] = fetch(quad["src_bucket"], quad[part], path)
        return {"workdir": workdir, "sizes": sizes, "download_s": time.monotonic() - mark,
                "requests": collections.Counter(fetcher.requests)}
    except BaseException:
        shutil.rmtree(workdir, ignore_errors=True)
        raise


def one_quad(store, out_bucket, out_prefix, quad, sample, fetched, wait_s):
    """Convert one downloaded quad and return its receipt. `sample` adds the pixel comparison.

    `wait_s` is how long the main thread waited for the download; with overlap it is less than
    `download_s`, and `total_s` counts only the wait.
    """
    workdir, sizes = fetched["workdir"], fetched["sizes"]
    timing = {"download_s": fetched["download_s"], "download_wait_s": wait_s}
    started = time.monotonic() - wait_s
    store.requests.clear()
    source = os.path.join(workdir, os.path.basename(quad["mrf"]))

    target = os.path.join(workdir, "out.tif")
    timing["convert_wall_s"], timing["convert_cpu_s"] = convert(source, target)
    before, after = describe(source), describe(target)
    problems = check(before, after)
    megapixels = before["width"] * before["height"] / 1e6

    receipt = {
        "schema": "folia.naip-display-pilot-receipt@1",
        "id": quad["id"],
        "out_uri": f"s3://{out_bucket}/{out_prefix}{quad['out_key']}",
        "source_bytes": sizes,
        "output_bytes": os.path.getsize(target),
        "output_sha256": sha256_of(target),
        "megapixels": round(megapixels, 3),
        "source": before,
        "output": after,
        "problems": problems,
    }

    if sample:
        mark = time.monotonic()
        receipt["psnr_db"] = psnr(source, target)
        timing["pixel_check_s"] = time.monotonic() - mark

    if quad.get("display_key"):
        # Control quads: the published display copy of the same quad, measured the same way.
        mark = time.monotonic()
        published = os.path.join(workdir, "published.tif")
        published_bytes = store.fetch(quad["display_bucket"], quad["display_key"], published)
        receipt["published"] = {
            "key": quad["display_key"],
            "bytes": published_bytes,
            "describe": describe(published),
            "psnr_db": psnr(source, published),
        }
        timing["published_compare_s"] = time.monotonic() - mark

    if problems:
        raise ValueError(f"output failed its checks: {problems}")

    mark = time.monotonic()
    store.put_file(out_bucket, out_prefix + quad["out_key"], target)
    timing["upload_s"] = time.monotonic() - mark

    timing["total_s"] = time.monotonic() - started
    receipt["seconds"] = {name: round(value, 3) for name, value in timing.items()}
    receipt["megapixels_per_cpu_s"] = round(megapixels / timing["convert_cpu_s"], 2)
    receipt["requests"] = dict(fetched["requests"] + store.requests)
    receipt["max_rss_kb"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return receipt


def main():
    # Converted files go to OUT_BUCKET/OUT_PREFIX. The manifest, receipts and error records
    # stay in WORK_BUCKET, which is ours, so the published tree holds only data.
    out_bucket = os.environ["OUT_BUCKET"]
    out_prefix = os.environ.get("OUT_PREFIX", "")
    work_bucket = os.environ.get("WORK_BUCKET", out_bucket)
    run_id = os.environ["RUN_ID"]
    shard_index = int(os.environ.get("SHARD_INDEX", "0"))
    shard_count = int(os.environ.get("SHARD_COUNT", "1"))
    limit = int(os.environ.get("LIMIT", "0"))
    sample_every = int(os.environ.get("SAMPLE_EVERY", "0"))
    deadline = time.monotonic() + int(os.environ.get("DEADLINE_SECONDS", "10800"))

    store = Store()
    manifest = store.read_lines(work_bucket, os.environ["MANIFEST_KEY"])
    mine = [(n, quad) for n, quad in enumerate(manifest) if n % shard_count == shard_index]
    if limit:
        mine = mine[:limit]
    host = socket.gethostname()
    print(f"run {run_id} shard {shard_index}/{shard_count}: {len(mine)} quads, gdal {gdal.__version__}",
          flush=True)

    # One download runs ahead of the conversion, on its own client and request counter.
    fetcher = Store()
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    queue = iter(mine)

    def start_next():
        following = next(queue, None)
        if following is None:
            return None
        position, quad = following
        receipt_key = f"_receipts/{run_id}/{quad['id']}.json"
        return position, quad, receipt_key, pool.submit(
            fetch_quad, fetcher, work_bucket, receipt_key, quad)

    done = skipped = failed = 0
    out_of_time = False
    current = start_next()
    while current:
        position, quad, receipt_key, download = current
        if time.monotonic() > deadline:
            print("deadline reached, stopping", flush=True)
            out_of_time = True
            break
        current = None
        workdir = None
        try:
            mark = time.monotonic()
            fetched = download.result()
            wait_s = time.monotonic() - mark
            if OVERLAP_DOWNLOADS:
                current = start_next()
            if fetched is None:
                skipped += 1
                continue
            workdir = fetched["workdir"]
            sample = bool(sample_every) and position % sample_every == 0
            receipt = one_quad(store, out_bucket, out_prefix, quad, sample, fetched, wait_s)
            receipt.update({"run_id": run_id, "shard": shard_index, "host": host,
                            "gdal": gdal.__version__, "quality": QUALITY,
                            "overlap_downloads": OVERLAP_DOWNLOADS,
                            "finished_unix": round(time.time(), 3)})
            store.put_json(work_bucket, receipt_key, receipt)
            done += 1
            print(f"ok {quad['id']} {receipt['output_bytes']} bytes "
                  f"{receipt['seconds']['total_s']} s", flush=True)
        except Exception as error:  # one bad quad must not stop the shard
            failed += 1
            print(f"FAILED {quad['id']}: {error!r}", flush=True)
            store.put_json(work_bucket, f"_errors/{run_id}/{quad['id']}.json",
                           {"id": quad["id"], "run_id": run_id, "shard": shard_index,
                            "error": repr(error)})
        finally:
            if workdir:
                shutil.rmtree(workdir, ignore_errors=True)
            if current is None and not out_of_time:
                current = start_next()

    if current:  # stopped at the deadline with a download under way: let it end, then drop it
        try:
            unused = current[3].result()
            if unused:
                shutil.rmtree(unused["workdir"], ignore_errors=True)
        except Exception:
            pass
    pool.shutdown()

    print(f"shard {shard_index} finished: {done} converted, {skipped} already done, {failed} failed",
          flush=True)
    # Exit 0 only when the whole shard is done; 3 tells the dispatcher to launch it again.
    if out_of_time:
        return 3
    return 1 if failed else 0


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "--local":
        local(sys.argv[2], sys.argv[3])
    else:
        sys.exit(main())
