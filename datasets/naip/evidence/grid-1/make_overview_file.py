#!/usr/bin/env python3
"""Make an overview-only COG for a square from the coarse levels of its assembled 100 km
file, without decoding: level `first` becomes the new file's full resolution and the levels
below it its overviews. The assembled file stores blocks coarsest level first, so the blocks
wanted are one run of bytes, copied inside S3; only the header is written new.

    python3 make_overview_file.py <worker dir> <bucket> <square key> <new key> <first level>
"""
import struct, sys
sys.path.insert(0, sys.argv[1])
import boto3
import mosaic as m

bucket, old, new, first = sys.argv[2], sys.argv[3], sys.argv[4], int(sys.argv[5])
s3 = boto3.client("s3", region_name="us-west-2")
head = s3.get_object(Bucket=bucket, Key=old, Range=f"bytes=0-{(8 << 20) - 1}")["Body"].read()
tmp = sys.argv[6]
open(tmp, "wb").write(head)
_, ghost, ifds = m.read_tiff(tmp)
keep = [dict(t) for t in ifds[first:]]
start = min(min(m.numbers(t, m.TILE_OFFSETS)) for t in keep) - 4
last = max(o + c + 4 for t in keep for o, c in zip(m.numbers(t, m.TILE_OFFSETS), m.numbers(t, m.TILE_COUNTS)))
# georeferencing: the new full resolution takes level 0's tags with the pixel size scaled
for tag in m.GEO_TAGS:
    if tag in ifds[0]:
        keep[0][tag] = ifds[0][tag]
kind, count, data = ifds[0][33550]                                    # ModelPixelScale
sx, sy, sz = struct.unpack("<3d", data)
w0, h0 = m.numbers(ifds[0], m.WIDTH)[0], m.numbers(ifds[0], m.LENGTH)[0]
w, h = m.numbers(keep[0], m.WIDTH)[0], m.numbers(keep[0], m.LENGTH)[0]
keep[0][33550] = (kind, count, struct.pack("<3d", sx * w0 / w, sy * h0 / h, sz))
keep[0].pop(m.NEW_SUBFILE, None)

entries = [sorted(t.items()) for t in keep]
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
PART = 5 << 20                                # S3's smallest part; the gap is zero padding
front_len = max(at, PART)
shift = front_len - start                     # every block moves by this much
front = bytearray(front_len)
front[:16] = b"II" + struct.pack("<HHHQ", 43, 8, 0, first_ifd)
front[16:16 + len(ghost)] = ghost
for i, tags in enumerate(entries):
    p = ifd_at[i]
    front[p:p + 8] = struct.pack("<Q", len(tags)); p += 8
    for tag, (kind, count, data) in tags:
        if tag == m.TILE_OFFSETS:
            data = struct.pack(f"<{count}Q", *[o + shift for o in m.numbers(keep[i], tag)])
            fields[(i, tag)] = (kind, count, data)
        n = m.TYPE_BYTES[kind] * count
        field = data.ljust(8, b"\0") if n <= 8 else struct.pack("<Q", value_at[(i, tag)])
        front[p:p + 20] = struct.pack("<HHQ", tag, kind, count) + field; p += 20
    front[p:p + 8] = struct.pack("<Q", ifd_at[i + 1] if i + 1 < len(entries) else 0)
for key, where in value_at.items():
    data = fields[key][2]
    front[where:where + len(data)] = data
upload = s3.create_multipart_upload(Bucket=bucket, Key=new, ContentType="image/tiff")["UploadId"]
parts = [s3.upload_part(Bucket=bucket, Key=new, UploadId=upload, PartNumber=1, Body=bytes(front))["ETag"]]
r = s3.upload_part_copy(Bucket=bucket, Key=new, UploadId=upload, PartNumber=2,
                        CopySource={"Bucket": bucket, "Key": old}, CopySourceRange=f"bytes={start}-{last - 1}")
parts.append(r["CopyPartResult"]["ETag"])
s3.complete_multipart_upload(Bucket=bucket, Key=new, UploadId=upload,
                             MultipartUpload={"Parts": [{"PartNumber": i + 1, "ETag": e} for i, e in enumerate(parts)]})
print("levels kept", len(keep), "size", w, "x", h, "bytes", s3.head_object(Bucket=bucket, Key=new)["ContentLength"])
