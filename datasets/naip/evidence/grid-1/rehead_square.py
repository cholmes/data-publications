#!/usr/bin/env python3
"""Rewrite the front of an assembled square so the small tag values (JPEG tables,
georeferencing) come before the block tables, without moving any block.

The first assembly wrote each level's values in tag order, which put the JPEG tables after
the block tables, about 1.7 MB in. GDAL reads that; the browser reader (@cogeotiff/core) only
looks in the header bytes it fetches first. The assembler now writes the order used here.
The values take the same space in either order, so every block stays where it is and only
the front of the object changes: it is uploaded as part 1, and the rest is copied inside S3.

    python3 rehead_square.py <worker dir> <bucket> <old key> <new key>
"""
import struct, sys
sys.path.insert(0, sys.argv[1])
import boto3
import mosaic as m

bucket, old, new = sys.argv[2:5]
s3 = boto3.client("s3", region_name="us-west-2")
size = s3.head_object(Bucket=bucket, Key=old)["ContentLength"]
PART1 = 8 << 20
head = s3.get_object(Bucket=bucket, Key=old, Range=f"bytes=0-{PART1 - 1}")["Body"].read()
open("/tmp/.square-head.bin", "wb").write(head)
_, ghost, ifds = m.read_tiff("/tmp/.square-head.bin")
first_block = min(min(m.numbers(t, m.TILE_OFFSETS)) for t in ifds) - 4
assert first_block < PART1, first_block

entries = [sorted(t.items()) for t in ifds]
at = 16 + len(ghost); at += -at % 8
first_ifd, ifd_at = at, []
for tags in entries:
    ifd_at.append(at); at += 8 + 20 * len(tags) + 8
tables = (m.TILE_OFFSETS, m.TILE_COUNTS)
order = [(i, tag) for i, tags in enumerate(entries) for tag, _ in tags if tag not in tables]
order += [(i, tag) for i in reversed(range(len(entries))) for tag in tables]
fields = {(i, tag): v for i, tags in enumerate(entries) for tag, v in tags}
value_at = {}
for key in order:
    kind, count, _ = fields[key]
    if m.TYPE_BYTES[kind] * count > 8:
        value_at[key] = at; at += m.TYPE_BYTES[kind] * count; at += -at % 8
assert at <= first_block, (at, first_block)
front = bytearray(first_block)
front[:16] = b"II" + struct.pack("<HHHQ", 43, 8, 0, first_ifd)
front[16:16 + len(ghost)] = ghost
for i, tags in enumerate(entries):
    p = ifd_at[i]
    front[p:p + 8] = struct.pack("<Q", len(tags)); p += 8
    for tag, (kind, count, data) in tags:
        n = m.TYPE_BYTES[kind] * count
        field = data.ljust(8, b"\0") if n <= 8 else struct.pack("<Q", value_at[(i, tag)])
        front[p:p + 20] = struct.pack("<HHQ", tag, kind, count) + field; p += 20
    front[p:p + 8] = struct.pack("<Q", ifd_at[i + 1] if i + 1 < len(entries) else 0)
for key, where in value_at.items():
    data = fields[key][2]
    front[where:where + len(data)] = data
print("front", first_block, "bytes; values end at", at, "; JPEG tables of level 0 at", value_at[(0, m.JPEG_TABLES)])

upload = s3.create_multipart_upload(Bucket=bucket, Key=new, ContentType="image/tiff")["UploadId"]
parts = [s3.upload_part(Bucket=bucket, Key=new, UploadId=upload, PartNumber=1, Body=bytes(front) + head[first_block:])["ETag"]]
start, step = PART1, 1 << 30
while start < size:
    end = min(start + step, size) - 1
    r = s3.upload_part_copy(Bucket=bucket, Key=new, UploadId=upload, PartNumber=len(parts) + 1,
                            CopySource={"Bucket": bucket, "Key": old}, CopySourceRange=f"bytes={start}-{end}")
    parts.append(r["CopyPartResult"]["ETag"]); start = end + 1
s3.complete_multipart_upload(Bucket=bucket, Key=new, UploadId=upload,
                             MultipartUpload={"Parts": [{"PartNumber": i + 1, "ETag": e} for i, e in enumerate(parts)]})
print("wrote", new, s3.head_object(Bucket=bucket, Key=new)["ContentLength"], "bytes; old", size)
