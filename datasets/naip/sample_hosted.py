#!/usr/bin/env python3
"""Read sample files of the published product from inside its region.

check_hosted.py hashes every Nth file and opens it in place. From a laptop that is a
download of every sample; from a task beside the bucket it is minutes. This does only those
two reads, for a list of keys, and writes what it found. check_hosted.py decides pass or
fail from it (`--samples`), against the receipts, exactly as when it does the reads itself.

Every read of the product is anonymous: plain HTTPS for the hash, GDAL with
AWS_NO_SIGN_REQUEST for the open. The task's own credentials are used only for the request
and result objects in the work bucket.

    WORK_BUCKET=<bucket> REQUEST_KEY=_hosted-samples/<name>-request.json \
    RESULT_KEY=_hosted-samples/<name>-result.json [THREADS=8] [DEADLINE_SECONDS=3000] \
        python3 sample_hosted.py

Request: {"bucket": "<product bucket>", "keys": ["nthh/naip/...tif", ...]}.
Result:  {"gdal": "...", "files": {key: {"sha256": "...", "bytes": n, "problems": [...]}},
          "errors": {key: "..."}, "not_read": [keys left when the deadline came]}.

Needs boto3 and GDAL's Python bindings, both in the converter image.
"""
import concurrent.futures
import hashlib
import json
import os
import time
import urllib.request


def sha256_of(url):
    """SHA-256 and length of what an anonymous reader gets."""
    h, n = hashlib.sha256(), 0
    with urllib.request.urlopen(url, timeout=120) as resp:
        while chunk := resp.read(1 << 22):
            h.update(chunk)
            n += len(chunk)
    return h.hexdigest(), n


def open_in_place(gdal, bucket, key):
    """Problems found opening the file over /vsis3/; an empty list is a pass."""
    problems = []
    ds = gdal.Open(f"/vsis3/{bucket}/{key}")
    structure = ds.GetMetadata("IMAGE_STRUCTURE")
    if structure.get("LAYOUT") != "COG":
        problems.append(f"layout {structure.get('LAYOUT')}")
    if structure.get("COMPRESSION") not in ("JPEG", "YCbCr JPEG"):
        problems.append(f"compression {structure.get('COMPRESSION')}")
    band = ds.GetRasterBand(1)
    if band.GetOverviewCount() < 1:
        problems.append("no overview")
    else:
        ov = band.GetOverview(band.GetOverviewCount() - 1)
        if ov.ReadRaster(0, 0, min(512, ov.XSize), min(512, ov.YSize)) is None:
            problems.append("overview read failed")
    if ds.ReadRaster(ds.RasterXSize // 2, ds.RasterYSize // 2, 512, 512) is None:
        problems.append("full-resolution read failed")
    return problems


def main():
    import boto3
    from osgeo import gdal

    gdal.UseExceptions()
    gdal.SetConfigOption("AWS_NO_SIGN_REQUEST", "YES")
    gdal.SetConfigOption("AWS_REGION", "us-west-2")
    work = os.environ["WORK_BUCKET"]
    deadline = time.monotonic() + int(os.environ.get("DEADLINE_SECONDS", "3000"))
    s3 = boto3.client("s3")
    request = json.loads(s3.get_object(Bucket=work, Key=os.environ["REQUEST_KEY"])["Body"].read())
    bucket, keys = request["bucket"], request["keys"]
    print(f"{len(keys)} files to read from {bucket}", flush=True)

    def one(key):
        if time.monotonic() > deadline:
            return key, None, None
        try:
            digest, size = sha256_of(f"https://s3.us-west-2.amazonaws.com/{bucket}/{key}")
            return key, {"sha256": digest, "bytes": size, "problems": open_in_place(gdal, bucket, key)}, None
        except Exception as error:  # recorded per file; one bad read must not hide the rest
            return key, None, repr(error)

    files, errors, not_read = {}, {}, []
    with concurrent.futures.ThreadPoolExecutor(int(os.environ.get("THREADS", "8"))) as pool:
        for done, (key, found, error) in enumerate(pool.map(one, keys), 1):
            if found:
                files[key] = found
            elif error:
                errors[key] = error
            else:
                not_read.append(key)
            if done % 50 == 0:
                print(f"{done} of {len(keys)}", flush=True)
    result = {"gdal": gdal.__version__, "bucket": bucket, "files": files, "errors": errors,
              "not_read": not_read, "bytes_read": sum(f["bytes"] for f in files.values())}
    s3.put_object(Bucket=work, Key=os.environ["RESULT_KEY"], Body=json.dumps(result).encode())
    print(f"read {len(files)}, errors {len(errors)}, not read {len(not_read)}", flush=True)


if __name__ == "__main__":
    main()
