#!/usr/bin/env python3
"""Bring the record of the national run up to date from the run folders.

For each planned run that has a summary.json and a hosted-checks.json in the runs dir:
copies both into evidence/ under the state's name, and prints one table row (for
VALIDATION.md) and one build.converted entry (for dataset.yaml). The table and the entries
are generated here so they are never typed by hand.

    python3 record_runs.py <runs dir> --table table.md --entries entries.yaml [--skip run,run]

--skip names runs whose dataset.yaml entry already exists; they stay in the table.
"""
import argparse
import datetime
import json
import os
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
STATES = {
    "al": "alabama", "ar": "arkansas", "az": "arizona", "ca": "california", "ct": "connecticut",
    "fl": "florida", "ga": "georgia", "ia": "iowa", "id": "idaho", "il": "illinois", "in": "indiana",
    "ks": "kansas", "ky": "kentucky", "la": "louisiana", "ma": "massachusetts", "me": "maine",
    "mi": "michigan", "mn": "minnesota", "mo": "missouri", "ms": "mississippi", "mt": "montana",
    "nc": "north-carolina", "nd": "north-dakota", "ne": "nebraska", "nj": "new-jersey",
    "nm": "new-mexico", "nv": "nevada", "ny": "new-york", "oh": "ohio", "ok": "oklahoma",
    "or": "oregon", "pa": "pennsylvania", "sc": "south-carolina", "sd": "south-dakota",
    "tn": "tennessee", "tx": "texas", "va": "virginia", "wi": "wisconsin", "wv": "west-virginia",
    "wy": "wyoming",
}


def load(path):
    with open(path) as f:
        return json.load(f)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("runs_dir")
    p.add_argument("--table", required=True)
    p.add_argument("--entries", required=True)
    p.add_argument("--skip", default="")
    a = p.parse_args()
    plan = load(os.path.join(HERE, "evidence", "national-launch-plan.json"))["runs"]
    twice = {}                                   # states with two resolutions in one year
    for r in plan:
        state, year, _ = r["manifest"].split("-")
        twice[state, year] = twice.get((state, year), 0) + 1

    rows, entries = [], []
    for r in sorted(plan, key=lambda r: (r["wave"], r["manifest"])):
        folder = os.path.join(a.runs_dir, r["run"])
        summary, checks = load(f"{folder}/summary.json"), load(f"{folder}/hosted-checks.json")
        state, year, res = r["manifest"].split("-")
        name = f"{STATES[state]}-{year}" + (f"-{res}" if twice[state, year] > 1 else "")
        for kind in ("summary", "hosted-checks"):
            shutil.copyfile(f"{folder}/{kind}.json", os.path.join(HERE, "evidence", f"{name}-{kind}.json"))

        flown, finished, lowest = [], 0.0, 9.0
        for receipt_name in os.listdir(f"{folder}/receipts"):
            receipt = load(f"{folder}/receipts/{receipt_name}")
            flown.append(receipt["id"].rsplit("_", 1)[1])
            finished = max(finished, receipt["finished_unix"])
            lowest = min(lowest, min(min(pair) for pair in receipt["output"]["overview_edges"]))
        day = lambda d: f"{d[:4]}-{d[4:6]}-{d[6:]}"
        tasks, sample = summary["tasks"], checks["sample"]
        sampled_ok = sample["sha256"]["pass"] and sample["open_in_place"]["pass"]
        rows.append("| " + " | ".join([
            str(r["wave"]), f"{STATES[state].replace('-', ' ').title()} {year}", res,
            f"{summary['quads']:,} of {r['quads']:,}", str(summary["quads_with_problems"]),
            f"{summary['output_bytes'] / 1e9:,.1f}", f"{summary['output_share_of_source']:.1%}",
            f"{day(min(flown))} to {day(max(flown))}", f"{lowest:.3f}",
            f"{summary['psnr_db']['quads']}, {summary['psnr_db']['median']}, {summary['psnr_db']['min']}",
            f"{tasks['started']}, {tasks['spot_interruptions']}",
            f"{checks['listing']['listed']:,}" + ("" if checks["listing"]["pass"] else " FAIL"),
            f"{sample['files']}" + (", all match" if sampled_ok else " FAIL"),
            f"{checks['index']['rows']:,}" + ("" if checks["index"]["pass"] else " FAIL"),
            "pass" if checks["pass"] else "FAIL",
        ]) + " |")
        if r["run"] in a.skip.split(","):
            continue
        checked = datetime.date.fromtimestamp(os.path.getmtime(f"{folder}/hosted-checks.json"))
        entries.append("\n".join([
            f"  - state_year: {r['manifest']}",
            f"    run: {r['run']}",
            f"    converted_on: '{datetime.datetime.fromtimestamp(finished, datetime.timezone.utc).date()}'",
            f"    files: {summary['quads']}",
            f"    bytes: {summary['output_bytes']}",
            f"    summary: datasets/naip/evidence/{name}-summary.json",
            f"    hosted_checks: datasets/naip/evidence/{name}-hosted-checks.json",
            f"    hosted_checks_result: {'passed' if checks['pass'] else 'FAILED'} {checked}",
            "    location: nthh/naip on Source Cooperative (unlisted)",
        ]))

    head = ["Wave", "State-year", "Size", "Quads with a receipt", "With a problem", "GB", "Share of source",
            "Flown", "Lowest overview edge ratio", "Pixel checks: quads, median PSNR, lowest (dB)",
            "Tasks started, Spot interruptions", "Hosted: listed at recorded size",
            "Hosted: hashed and opened", "Hosted: index rows equal to receipts", "Hosted checks"]
    with open(a.table, "w") as f:
        f.write("| " + " | ".join(head) + " |\n|" + "---|" * len(head) + "\n" + "\n".join(rows) + "\n")
    with open(a.entries, "w") as f:
        f.write("\n".join(entries) + "\n")
    print(len(rows), "rows,", len(entries), "entries")


if __name__ == "__main__":
    main()
