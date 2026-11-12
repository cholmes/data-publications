#!/usr/bin/env python3
"""Launch plan for the state-years not yet published, from the manifests and measured speeds.

    python3 make_launch_plan.py <manifests dir> <out.json>

Shards are sized by source bytes so each is about SHARD_HOURS of work at the measured
task-hours per source TB (whole task time, start-up and Spot rework included, runs
nh2025-pub-2, ut2024-pub-2, vt2025-pub-1 on image v4). Waves keep running tasks under WAVE_TASKS.
"""
import json, math, os, sys
DONE = {"ri-2025-60cm", "nh-2025-60cm", "ut-2024-60cm", "vt-2025-30cm"}
HOURS_PER_TB = {"60cm": 7.9, "30cm": 8.1}
MEMORY = {"60cm": 2048, "30cm": 4096}
ON_DEMAND_TASK_HOUR = {"60cm": 0.0395, "30cm": 0.04662}
SPOT_TASK_HOUR = {"60cm": 0.01015 + 2 * 0.001116 + 0.005, "30cm": 0.01015 + 4 * 0.001116 + 0.005}
SHARD_HOURS, DEADLINE, RELAUNCH_MARGIN, WAVE_TASKS = 0.6, 3600, 1.3, 450

def main(mdir, out):
    names = sorted(n[:-6] for n in os.listdir(mdir) if n.endswith(".jsonl"))
    years = {}
    for n in names:
        years.setdefault(n.rsplit("-", 1)[0], []).append(n)
    runs = []
    for n in names:
        if n in DONE:
            continue
        st, year, res = n.split("-")
        rows = [json.loads(l) for l in open(f"{mdir}/{n}.jsonl")]
        tb = sum(r["lrc_bytes"] for r in rows) / 1e12
        hours = tb * HOURS_PER_TB[res]
        shards = max(1, math.ceil(hours / SHARD_HOURS))
        run = f"{st}{year}-{res}-pub-1" if len(years[f"{st}-{year}"]) > 1 else f"{st}{year}-pub-1"
        runs.append({"run": run, "manifest": n, "quads": len(rows), "res": res, "source_tb": round(tb, 3),
                     "expected_task_hours": round(hours, 1), "expected_usd": round(hours * SPOT_TASK_HOUR[res], 2),
                     "shards": shards, "memory_mib": MEMORY[res], "deadline": DEADLINE,
                     "max_usd": round(shards * RELAUNCH_MARGIN * DEADLINE / 3600 * ON_DEMAND_TASK_HOUR[res] + 0.05, 2)})
    waves = []
    for r in sorted(runs, key=lambda r: -r["shards"]):
        for w in waves:
            if w["tasks"] + r["shards"] <= WAVE_TASKS:
                break
        else:
            w = {"tasks": 0, "runs": []}
            waves.append(w)
        w["tasks"] += r["shards"]; w["runs"].append(r["run"])
    for i, w in enumerate(waves):
        for r in runs:
            if r["run"] in w["runs"]:
                r["wave"] = i + 1
    plan = {"made": "2026-11-11", "basis": __doc__.split("\n\n", 2)[2].strip(),
            "totals": {"runs": len(runs), "quads": sum(r["quads"] for r in runs),
                       "source_tb": round(sum(r["source_tb"] for r in runs), 2),
                       "shards": sum(r["shards"] for r in runs),
                       "expected_task_hours": round(sum(r["expected_task_hours"] for r in runs)),
                       "expected_compute_usd": round(sum(r["expected_usd"] for r in runs), 2),
                       "max_usd_bound": round(sum(r["max_usd"] for r in runs), 2)},
            "waves": [{"wave": i + 1, **w} for i, w in enumerate(waves)],
            "runs": sorted(runs, key=lambda r: (r["wave"], r["run"]))}
    json.dump(plan, open(out, "w"), indent=1)
    print(json.dumps(plan["totals"])); [print(w["wave"], w["tasks"], len(w["runs"])) for w in plan["waves"]]
    print(max(runs, key=lambda r: r["shards"]), len({r["run"] for r in runs}))

main(*sys.argv[1:])
