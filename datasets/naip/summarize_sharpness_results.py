#!/usr/bin/env python3
"""A Markdown table of the overview sharpness test, for VALIDATION.md.

    python3 summarize_sharpness_results.py <folder> <against-full-resolution.json> <label>=<build name> ...

The folder holds each build's <name>-result.json; the JSON is what
check_overview_against_full_resolution.py printed for the same labels. The first label is
the present build, and the others are given as differences from it.
"""
import json
import os
import sys


def main():
    folder, scores_path = sys.argv[1:3]
    with open(scores_path) as f:
        scores = json.load(f)["files"]
    pairs = [a.split("=", 1) for a in sys.argv[3:]]
    base = scores[pairs[0][0]]
    print("| Build | Level read, method, quality | File | Read from quads | Staged | Median dB against the reference | "
          "Change from present | Lowest block dB | Own check, lowest dB |")
    print("|---|---|---|---|---|---|---|---|---|")
    for label, name in pairs:
        with open(os.path.join(folder, name + "-result.json")) as f:
            r = json.load(f)
        s = scores[label]
        own = r["file"]["windows"]["lowest_db"]
        quality = "85" if name.endswith("q85") else "75"
        print("| " + " | ".join([
            f"`{name}`", f"{r['read_m']} m, {r.get('resample', 'bilinear')}, {quality}", f"{r['bytes'] / 1e6:.1f} MB",
            f"{r['quad_bytes_read'] / 1e6:.0f} MB", f"{r['staged_bytes'] / 1e6:.0f} MB",
            ", ".join(f"{v:.2f}" for v in s["median_db"]),
            "" if s is base else ", ".join(f"{v - b:+.2f}" for v, b in zip(s["median_db"], base["median_db"])),
            ", ".join(f"{v:.2f}" for v in s["lowest_db"]),
            ", ".join(f"{v:.2f}" for v in own) + ("" if min(own) >= 30 else " (fails)"),
        ]) + " |")


if __name__ == "__main__":
    main()
