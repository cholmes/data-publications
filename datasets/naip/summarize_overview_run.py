#!/usr/bin/env python3
"""Totals and a per-file table of a run of state overview builds, for VALIDATION.md.

    python3 summarize_overview_run.py <folder of *-result.json and *-against-quads.json> <launch state.json> [national result.json]

Prints Markdown: the totals first, then one row per file. Cost is the build seconds of each
task at the on-demand price of its size (dispatch.py's prices); Spot is cheaper and start-up
time is not counted, so it is an indication, not a bill.
"""
import glob
import json
import os
import sys

from dispatch import GB_HOUR_USD, VCPU_HOUR_USD


def main():
    folder, state_path = sys.argv[1:3]
    with open(state_path) as f:
        tasks = json.load(f)["tasks"]
    rows, usd = [], 0.0
    for path in sorted(glob.glob(os.path.join(folder, "*-result.json"))):
        with open(path) as f:
            r = json.load(f)
        with open(path.replace("-result.json", "-against-quads.json")) as f:
            q = json.load(f)
        task = tasks[r["name"]][-1]
        seconds = sum(r["seconds"].values())
        usd += seconds / 3600 * (task["cpu"] / 1024 * VCPU_HOUR_USD + task["memory"] / 1024 * GB_HOUR_USD)
        rows.append((r, q, task, seconds))
    own = [min(r["file"]["windows"]["lowest_db"]) for r, *_ in rows]
    failed_own = [r["name"] for (r, *_), low in zip(rows, own) if low < 30]
    moved = [r["name"] for r, q, *_ in rows if q["blocks_better_moved_by_one_pixel"]]
    print(f"- {len(rows)} files, {sum(r['quads'] for r, *_ in rows):,} quads, {sum(r['bytes'] for r, *_ in rows) / 1e9:.2f} GB;",
          f"{sum(1 for r, *_ in rows if r['quads'] <= 100)} files have 100 quads or fewer.")
    kinds = lambda key: ", ".join(sorted({str(r["file"][key]) for r, *_ in rows}))
    print(f"- Structure, the values found across all files: layout {kinds('layout')}; compression {kinds('compression')};",
          f"mask per dataset {kinds('mask_per_dataset')}; write retried on one thread: {sum(1 for r, *_ in rows if r['write_retried_with_one_thread'])}.")
    print(f"- Own check (file against the mosaic it was written from, lowest band of the lowest window): lowest {min(own):.2f} dB,",
          f"median {sorted(own)[len(own) // 2]:.2f} dB. Below the 30 dB mark: {', '.join(failed_own) or 'none'}.")
    print(f"- Against the hosted quads: {sum(q['quads_sampled'] for _, q, *_ in rows)} quads, {sum(q['blocks'] for _, q, *_ in rows):,} blocks,",
          f"{sum(q['blocks_better_moved_by_one_pixel'] for _, q, *_ in rows)} agree better moved by one pixel ({', '.join(moved) or 'no file'});",
          f"lowest block {min(q['psnr_db']['lowest'] for _, q, *_ in rows)} dB.")
    print(f"- Build time summed {sum(s for *_, s in rows) / 3600:.1f} task-hours, longest {max(s for *_, s in rows) / 60:.1f} min; about ${usd:.2f} at on-demand prices.")
    if len(sys.argv) > 3:
        with open(sys.argv[3]) as f:
            n = json.load(f)
        w = n["file"]["windows"]
        print(f"- National file `{n['name']}`: {n['sources']} state files read at {n['read_m']} m, pixel {n['res']:.3f} m in EPSG:{n['target_epsg']},",
              f"{n['file']['size'][0]:,} by {n['file']['size'][1]:,} pixels, {len(n['file']['levels'])} reduced levels, {n['bytes'] / 1e6:.1f} MB,",
              f"{n['file']['layout']}, {n['file']['compression']}; mask equal to the canvas on {n['file']['mask_matches_canvas']:.0%} of pixels;",
              f"own check lowest {min(w['lowest_db'])} dB over {w['count']} windows; dark pixels {n['dark_share_of_covered']:.6f} of the covered ones;",
              f"sources showing nothing: {len(n['sources_showing_nothing'])}; built in {sum(n['seconds'].values()):.0f} s.")
    print("\n| File | Quads | Pixels | MB | Build (s) | vCPU | Own check, lowest dB (R, G, B) | Centres masked | Against quads: sampled, blocks, moved, lowest dB |")
    print("|---|---|---|---|---|---|---|---|---|")
    for r, q, task, seconds in rows:
        f = r["file"]
        print(f"| {r['name']} | {r['quads']:,} | {f['size'][0]:,} x {f['size'][1]:,} | {r['bytes'] / 1e6:.1f} | {seconds:.0f} | {task['cpu'] // 1024} |",
              f"{', '.join(str(v) for v in f['windows']['lowest_db'])} | {len(f['centres_masked'] or [])} |",
              f"{q['quads_sampled']}, {q['blocks']}, {q['blocks_better_moved_by_one_pixel']}, {q['psnr_db']['lowest']} |")


if __name__ == "__main__":
    main()
