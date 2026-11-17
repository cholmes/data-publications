# Pinned workflow files of the Census releases

The analytic release `cb2023-r1` and the display builds record the commit they were built from
and the SHA-256 of each workflow file. `index.json` binds each of those commits and paths to the
exact bytes in `blobs/<sha256>`, so a pinned file can be checked when the commit is no longer in
the repository's history. `export.py` wrote them from Git and stopped on any file whose bytes
differed from what a release recorded; none did. `scripts/check_provenance.py` verifies them.
