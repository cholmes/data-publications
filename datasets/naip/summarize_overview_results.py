#!/usr/bin/env python3
"""A Markdown table of the overview test from the result files, for VALIDATION.md.

    python3 summarize_overview_results.py <folder of *-result.json, *-reads.json, *-against-quads.json>

One row per build. "Own check" is the build's comparison of the file with the mosaic it was
written from; "against quads" is check_overview_against_quads.py, 128 pixel blocks.
"""
import glob
import json
import os
import sys


def load(path):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)


def main():
    folder = sys.argv[1]
    print("| Build | Quads | Pixels | File | Read, copy, write (s) | Own check, lowest dB | Centres masked | "
          "Requests, 37 km view and whole file | Against quads: blocks, moved, lowest and median dB |")
    print("|---|---|---|---|---|---|---|---|---|")
    for path in sorted(glob.glob(os.path.join(folder, "*-result.json"))):
        name = os.path.basename(path)[:-len("-result.json")]
        r, reads, quads = load(path), load(path.replace("-result.json", "-reads.json")), load(path.replace("-result.json", "-against-quads.json"))
        f, s = r["file"], r["seconds"]
        windows = f["windows"]["lowest_db"]
        print("| " + " | ".join([
            name, f"{r['quads']:,}", f"{f['size'][0]:,} by {f['size'][1]:,}", f"{r['bytes'] / 1e6:,.1f} MB",
            ", ".join(str(round(s[k])) if k in s else "none" for k in ("read_quads", "copy_mosaic", "write_file")),
            ", ".join(f"{v:.2f}" for v in windows) + ("" if min(windows) >= 30 else " (fails)"),
            str(len(f["centres_masked"])),
            f"{reads['view_37km']['requests']} and {reads['whole_file']['requests']}" if reads else "not run",
            (f"{quads['blocks']:,}, {quads['blocks_better_moved_by_one_pixel']}, "
             f"{quads['psnr_db']['lowest']:.2f} and {quads['psnr_db']['median']:.2f}") if quads else "not run",
        ]) + " |")


if __name__ == "__main__":
    main()
