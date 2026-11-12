#!/usr/bin/env python3
"""Copy the square's rows of the published STAC-GeoParquet index into a Parquet file whose
layer metadata tells GDAL's GTI driver the mosaic's CRS, grid and extent and where the
overview file and its levels are. `GTI:<file>` then opens full resolution and overviews
with no other file.

    python3 make_gti_parquet.py <naip-stac.parquet> <out.parquet>
"""
import sys
from osgeo import gdal, ogr
gdal.UseExceptions()
P = "https://private-work-bucket.s3.us-west-2.amazonaws.com/_proto/grid-1"
OV = f"/vsicurl/{P}/overview/utm12_e400_n4400-ov3.tif"
src = gdal.OpenEx(sys.argv[1]); sl = src.GetLayer(0)
sl.SetAttributeFilter("\"naip:state\" = 'ut'"); sl.SetSpatialFilterRect(-112.18, 39.75, -111.0, 40.645)
out = ogr.GetDriverByName("Parquet").CreateDataSource(sys.argv[2])
lyr = out.CreateLayer("naip", sl.GetSpatialRef(), ogr.wkbPolygon)
md = {"SRS": "EPSG:26912", "SRS_BEHAVIOR": "REPROJECT", "RESX": "0.6", "RESY": "0.6", "MINX": "400000.2", "MINY": "4399999.8",
      "MAXX": "499999.8", "MAXY": "4500000", "OVERVIEW_0_DATASET": OV}
for k in range(6):
    md[f"OVERVIEW_{k + 1}_DATASET"] = OV; md[f"OVERVIEW_{k + 1}_OPEN_OPTIONS"] = f"OVERVIEW_LEVEL={k}"
for k, v in md.items():
    lyr.SetMetadataItem(k, v)
d = sl.GetLayerDefn()
for i in range(d.GetFieldCount()):
    lyr.CreateField(d.GetFieldDefn(i))
for f in sl:
    g = ogr.Feature(lyr.GetLayerDefn()); g.SetFrom(f); lyr.CreateFeature(g)
