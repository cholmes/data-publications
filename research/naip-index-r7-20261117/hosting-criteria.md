# NAIP stac/ files, index release r7: hosted checks

Written on 2026-11-17 (UTC) before the r7 file was put in place. r7 changes one hosted file,
`stac/naip.gti`, which `replace-run-1` (plan `replace-plan.json`) replaces only if it still holds
the r6 bytes. The other five stac/ files of r6 are byte-identical to r7's and stay. All six must be
the bytes of index release `index-20261117-r7`.

Checks 1 to 8 are those of `research/naip-index-r6-20261117/hosting-criteria.md`, on the six files,
with check 8 run by the r7 `check_gti_open.py --hosted`, which adds the add-layer step (approximate
statistics of band 1 and a 1,000-pixel draw of the whole extent, no more than 8 MiB fetched). The
quad index is unchanged from r6, so check 7 does not wait for the range cache.
