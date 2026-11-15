#!/usr/bin/env python3
"""Start the planned runs of the given waves as task slots come free.

The account may run 512 Fargate Spot vCPUs at once and every task is one vCPU. Rather than
wait for a whole wave to end, this starts the next planned run that fits under --ceiling
tasks, counting the tasks in the cluster now. Each run keeps its planned shard count,
memory and spend bound from the launch plan (evidence/national-launch-plan.json unless --plan
names another); nothing else is changed.

    python3 rolling_launch.py <runs dir> --stack <stack.json> --waves 4,5,6 \
        --task-definition <arn> [--ceiling 500] [--reserve-waves 3] [--reserve-runs a,b] [--parallel 4] [--hours 10] [--plan f]

Starts no further run once a launch fails, so a refused start is looked at before more are made.
Runs that already have a state.json in the runs dir are skipped.
"""
import argparse
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))


def running(cluster):
    out = subprocess.run(["aws", "ecs", "list-tasks", "--cluster", cluster, "--region", "us-west-2",
                          "--query", "taskArns", "--output", "json"], capture_output=True, text=True)
    return len(json.loads(out.stdout)) if out.returncode == 0 else None


def main():
    p = argparse.ArgumentParser()
    p.add_argument("runs_dir")
    p.add_argument("--stack", required=True)
    p.add_argument("--waves", required=True)
    p.add_argument("--task-definition", required=True)
    p.add_argument("--ceiling", type=int, default=500)
    p.add_argument("--reserve-waves", default="", help="waves another launcher is starting; their slots are kept")
    p.add_argument("--reserve-runs", default="", help="runs another launcher is starting")
    p.add_argument("--parallel", type=int, default=4, help="runs being started at once")
    p.add_argument("--hours", type=float, default=10)
    p.add_argument("--plan", default=os.path.join(HERE, "evidence", "national-launch-plan.json"),
                   help="launch plan made by make_launch_plan.py; default the national one")
    a = p.parse_args()
    with open(a.stack) as f:
        cluster = json.load(f)["cluster_name"]
    with open(a.plan) as f:
        plan = json.load(f)["runs"]
    waves = [int(w) for w in a.waves.split(",")]
    todo = [r for w in waves for r in plan if r["wave"] == w
            and not os.path.exists(os.path.join(a.runs_dir, r["run"], "state.json"))]
    print(len(todo), "runs to start,", sum(r["shards"] for r in todo), "tasks", flush=True)
    end = time.time() + a.hours * 3600

    def unstarted(run):
        """Tasks a run is still owed: its shard count less the tasks its state file records."""
        path = os.path.join(a.runs_dir, run["run"], "state.json")
        try:
            with open(path) as f:
                return max(0, run["shards"] - json.load(f)["started"])
        except (FileNotFoundError, ValueError):   # not begun, or caught mid-write
            return run["shards"]

    # Runs of --reserve-waves are being started by another launcher; their slots are kept for them.
    reserved = [r for r in plan if r["wave"] in [int(w) for w in a.reserve_waves.split(",") if w]
                or r["run"] in a.reserve_runs.split(",")]
    flying, failed = [], False
    while (todo or flying) and time.time() < end:
        for run, process in list(flying):
            code = process.poll()
            if code is None:
                continue
            flying.remove((run, process))
            if code != 0:
                failed = True
                print(f"launch of {run['run']} failed with exit {code}; no more runs will be started. "
                      f"See {a.runs_dir}/{run['run']}/launch.log", flush=True)
        now = running(cluster)
        if now is not None and not failed and len(flying) < a.parallel:
            owed = sum(unstarted(r) for r, _ in flying) + sum(unstarted(r) for r in reserved)
            fits = next((r for r in todo if now + owed + r["shards"] <= a.ceiling), None)
            if fits is not None:
                state_dir = os.path.join(a.runs_dir, fits["run"])
                os.makedirs(state_dir, exist_ok=True)
                print(f"{time.strftime('%H:%M:%S')} {now} running, {owed} owed; starting {fits['run']} "
                      f"({fits['shards']} tasks)", flush=True)
                log = open(os.path.join(state_dir, "launch.log"), "w")
                flying.append((fits, subprocess.Popen(
                    [sys.executable, os.path.join(HERE, "dispatch.py"), "launch", fits["run"],
                     f"_manifests/{fits['manifest']}.jsonl", state_dir, "--stack", a.stack,
                     "--task-definition", a.task_definition, "--shards", str(fits["shards"]),
                     "--memory-mib", str(fits["memory_mib"]), "--max-usd", str(fits["max_usd"]),
                     "--sample-every", "50", "--deadline", str(fits["deadline"]),
                     "--out-bucket", "us-west-2.opendata.source.coop", "--out-prefix", "nthh/naip/",
                     "--env", "QUALITY=65", "--env", "OVERVIEW_QUALITY=75"],
                    stdout=log, stderr=subprocess.STDOUT)))
                todo.remove(fits)
                time.sleep(5)      # let its state file appear before the next count
                continue
        if failed and not flying:
            sys.exit(1)
        time.sleep(30)
    print("all started" if not todo else "not started: " + ",".join(r["run"] for r in todo), flush=True)


if __name__ == "__main__":
    main()
