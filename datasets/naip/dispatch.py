#!/usr/bin/env python3
"""Build manifests, launch converter shards on ECS Fargate Spot, and summarize receipts.

Uses the `aws` command. `--stack` is a JSON file with the names of the pieces the tasks
run on: cluster_name, task_definition_arn, subnet_ids, security_group_id, bucket_name
(the work bucket) and, when task ends are recorded by an event rule, events_log_group.
`tofu output -json | jq 'map_values(.value)'` of a stack that creates them has that shape.

  dispatch.py manifests <listing dir> <out dir>          one manifest per state, year and resolution
  dispatch.py control <analytic.jsonl.gz> <display.jsonl.gz> <state> <year> <out file>
  dispatch.py launch <run id> <manifest key> <state dir> --stack f --shards N --max-usd X ...
  dispatch.py status <run id> <manifest file> --stack f  quads done and the shards still short
  dispatch.py ends <state dir> --stack f                 task end records from the event log
  dispatch.py summarize <receipts dir> <state dir>       totals from downloaded receipts

A shard is finished when every quad in it has a receipt. Nothing here has to stay running:
`status` names the shards that are short, and `launch --only` starts those again; a task
skips every quad that already has a receipt.

Spend bound: every task stops itself at --deadline seconds, and `launch` refuses to start
a task once (tasks started) x (deadline) x (on-demand price of the task size) would pass
--max-usd. Spot is cheaper than the on-demand price used, so the bound is conservative.
"""

import argparse
import gzip
import json
import os
import statistics
import subprocess
import sys
import time

REGION = "us-west-2"
# On-demand Fargate Linux/ARM in us-west-2, USD per hour; used only for the spend bound.
VCPU_HOUR_USD = 0.03238
GB_HOUR_USD = 0.00356


def aws(*args):
    out = subprocess.run(["aws", "--region", REGION, "--output", "json", *args],
                         check=True, capture_output=True, text=True).stdout
    return json.loads(out) if out.strip() else {}


def load_json(path):
    with open(path) as f:
        return json.load(f)


def read_manifest(path):
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


def write_manifest(path, rows):
    with open(path, "w") as out:
        out.writelines(json.dumps(row) + "\n" for row in rows)
    print(f"{os.path.basename(path)}: {len(rows)} quads, {sum(r['lrc_bytes'] for r in rows):,} lrc bytes")


def quad_row(key, sizes, out_prefix=""):
    """Manifest row for `<state>/<year>/<res>/rgbir/<block>/<name>.mrf`, or None."""
    parts = key.split("/")
    if len(parts) != 6 or parts[3] != "rgbir" or not key.endswith(".mrf"):
        return None
    state, year, resolution, _, block, name = parts
    stem, name = key[:-4], name[:-4]
    if f"{stem}.lrc" not in sizes or f"{stem}.idx" not in sizes:
        return None
    return {
        "id": f"{state}_{name}",
        "src_bucket": "naip-analytic",
        "mrf": key, "idx": f"{stem}.idx", "lrc": f"{stem}.lrc",
        "lrc_bytes": sizes[f"{stem}.lrc"],
        "out_key": f"{out_prefix}{state}/{year}/{resolution}/rgb/{block}/{name}.tif",
    }


def manifests(listing_dir, out_dir):
    """Listings are `<state>-<year>.tsv.gz` files of key<TAB>size for one naip-analytic prefix."""
    os.makedirs(out_dir, exist_ok=True)
    for name in sorted(os.listdir(listing_dir)):
        if not name.endswith(".tsv.gz"):
            continue
        with gzip.open(f"{listing_dir}/{name}", "rt") as lines:
            sizes = {key: int(size) for key, size in (line.rstrip("\n").split("\t") for line in lines if "\t" in line)}
        groups = {}
        for key in sorted(sizes):
            row = quad_row(key, sizes)
            if row:
                state, year, resolution = key.split("/")[:3]
                groups.setdefault(f"{state}-{year}-{resolution}", []).append(row)
        for group, rows in groups.items():
            write_manifest(f"{out_dir}/{group}.jsonl", rows)


def control(analytic_listing, display_listing, state, year, out_file, count=20):
    """Quads of a year that has a published display copy, spread across the state."""
    def read(path):
        with gzip.open(path, "rt") as lines:
            return {o["key"]: o["size"] for o in map(json.loads, lines)}
    sizes, display = read(analytic_listing), read(display_listing)
    rows = []
    for key in sorted(sizes):
        if not key.startswith(f"{state}/{year}/"):
            continue
        row = quad_row(key, sizes, out_prefix="control/")
        published = row and row["out_key"][len("control/"):]
        if row and published in display:
            row.update({"display_bucket": "naip-visualization", "display_key": published,
                        "display_bytes": display[published]})
            rows.append(row)
    step = max(1, len(rows) // count)
    write_manifest(out_file, rows[step // 2::step][:count])


def load_state(state_dir):
    path = f"{state_dir}/state.json"
    return load_json(path) if os.path.exists(path) else {"started": 0, "tasks": {}, "settings": {}}


def save_state(state_dir, state):
    os.makedirs(state_dir, exist_ok=True)
    with open(f"{state_dir}/state.json.tmp", "w") as f:
        json.dump(state, f, indent=1)
    os.replace(f"{state_dir}/state.json.tmp", f"{state_dir}/state.json")


def launch(args):
    stack = load_json(args.stack)
    state = load_state(args.state_dir)
    task_definition = args.task_definition or stack["task_definition_arn"]
    definition = aws("ecs", "describe-task-definition", "--task-definition", task_definition)["taskDefinition"]
    cpu = args.cpu or int(definition["cpu"])
    memory = args.memory_mib or int(definition["memory"])
    hour_usd = cpu / 1024 * VCPU_HOUR_USD + memory / 1024 * GB_HOUR_USD
    out_bucket = args.out_bucket or stack["bucket_name"]
    state["settings"] = {
        "run_id": args.run_id, "manifest_key": args.manifest_key, "shards": args.shards,
        "deadline": args.deadline, "max_usd": args.max_usd, "task_hour_usd": round(hour_usd, 5),
        "cpu": cpu, "memory_mib": memory, "out": f"s3://{out_bucket}/{args.out_prefix}",
        "task_definition": task_definition,
    }
    env = {
        "RUN_ID": args.run_id, "MANIFEST_KEY": args.manifest_key, "SHARD_COUNT": args.shards,
        "DEADLINE_SECONDS": args.deadline, "SAMPLE_EVERY": args.sample_every, "LIMIT": args.limit,
        "OUT_BUCKET": out_bucket, "OUT_PREFIX": args.out_prefix, "WORK_BUCKET": stack["bucket_name"],
        "OVERLAP_DOWNLOADS": 0 if args.no_overlap else 1,
    }
    network = {"awsvpcConfiguration": {"subnets": stack["subnet_ids"],
                                       "securityGroups": [stack["security_group_id"]],
                                       "assignPublicIp": "ENABLED"}}
    shards = [int(x) for x in args.only.split(",")] if args.only else range(args.shards)
    for shard in shards:
        worst = (state["started"] + 1) * args.deadline / 3600 * hour_usd
        if worst > args.max_usd:
            raise SystemExit(f"refusing to start shard {shard}: worst case ${worst:.2f} passes ${args.max_usd}")
        overrides = {"cpu": str(cpu), "memory": str(memory), "containerOverrides": [{
            "name": "convert",
            "environment": [{"name": k, "value": str(v)} for k, v in {**env, "SHARD_INDEX": shard}.items()],
        }]}
        result = aws("ecs", "run-task", "--cluster", stack["cluster_name"],
                     "--task-definition", task_definition,
                     "--capacity-provider-strategy", "capacityProvider=FARGATE_SPOT,weight=1",
                     "--count", "1", "--started-by", args.run_id[:36],
                     # The run tag is what separates this run's lines on the bill.
                     "--tags", f"key=run,value={args.run_id}", "--propagate-tags", "TASK_DEFINITION",
                     "--network-configuration", json.dumps(network),
                     "--overrides", json.dumps(overrides))
        if result.get("failures"):
            raise SystemExit(f"run-task failed for shard {shard}: {result['failures']}")
        state["started"] += 1
        state["tasks"][result["tasks"][0]["taskArn"]] = {"shard": shard}
        save_state(args.state_dir, state)
        time.sleep(0.25)
    print(f"{state['started']} tasks started in all for run {args.run_id}")


def status(args):
    stack = load_json(args.stack)
    manifest = read_manifest(args.manifest_file)
    done, token = set(), None
    while True:
        page = aws("s3api", "list-objects-v2", "--bucket", stack["bucket_name"],
                   "--prefix", f"_receipts/{args.run_id}/", "--max-items", "100000",
                   *(["--starting-token", token] if token else []))
        done.update(o["Key"].rsplit("/", 1)[-1][:-5] for o in page.get("Contents", []))
        token = page.get("NextToken")
        if not token:
            break
    short = sorted({n % args.shards for n, quad in enumerate(manifest) if quad["id"] not in done})
    print(f"{len(done & {q['id'] for q in manifest})} of {len(manifest)} quads have a receipt")
    print("shards still short: " + (",".join(map(str, short)) or "none"))


def ends(args):
    """Fill task end records from the log group an EventBridge rule writes task stops to."""
    stack = load_json(args.stack)
    state = load_state(args.state_dir)
    token = None
    while True:
        page = aws("logs", "filter-log-events", "--log-group-name", stack["events_log_group"],
                   "--filter-pattern", '{ $.detail.lastStatus = "STOPPED" }',
                   *(["--next-token", token] if token else []))
        for event in page.get("events", []):
            detail = json.loads(event["message"])["detail"]
            record = state["tasks"].get(detail["taskArn"])
            if record is not None:
                container = (detail.get("containers") or [{}])[0]
                record.update({
                    "stop_code": detail.get("stopCode"), "stopped_reason": detail.get("stoppedReason"),
                    "exit_code": container.get("exitCode"),
                    "pull_started": detail.get("pullStartedAt"), "started": detail.get("startedAt"),
                    "stopped": detail.get("stoppedAt"),
                })
        token = page.get("nextToken")
        if not token:
            break
    save_state(args.state_dir, state)
    ended = [t for t in state["tasks"].values() if t.get("stopped")]
    print(f"{len(ended)} of {len(state['tasks'])} tasks have an end record, "
          f"{sum(1 for t in ended if t.get('stop_code') == 'SpotInterruption')} Spot interruptions")


def percentile(values, fraction):
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(fraction * len(ordered)))]


def summarize(receipts_dir, state_dir):
    receipts = [load_json(f"{receipts_dir}/{name}") for name in sorted(os.listdir(receipts_dir))
                if name.endswith(".json")]
    if not receipts:
        raise SystemExit("no receipts")
    rate = [r["megapixels_per_cpu_s"] for r in receipts]
    seconds, requests = {}, {}
    for r in receipts:
        for name, value in r["seconds"].items():
            seconds[name] = seconds.get(name, 0.0) + value
        for name, value in r["requests"].items():
            requests[name] = requests.get(name, 0) + value
    out = {
        "schema": "folia.naip-display-pilot-summary@1",
        "quads": len(receipts),
        "megapixels": round(sum(r["megapixels"] for r in receipts), 1),
        "source_bytes": sum(sum(r["source_bytes"].values()) for r in receipts),
        "output_bytes": sum(r["output_bytes"] for r in receipts),
        "seconds_summed": {k: round(v, 1) for k, v in sorted(seconds.items())},
        "megapixels_per_cpu_s": {"p10": percentile(rate, 0.1), "median": statistics.median(rate),
                                 "p90": percentile(rate, 0.9)},
        "requests": dict(sorted(requests.items())),
        "max_rss_kb": max(r["max_rss_kb"] for r in receipts),
        "quads_with_problems": sum(1 for r in receipts if r["problems"]),
    }
    out["output_share_of_source"] = round(out["output_bytes"] / out["source_bytes"], 4)
    sampled = [r["psnr_db"] for r in receipts if r.get("psnr_db")]
    if sampled:
        means = [statistics.mean(v for v in p if v is not None) for p in sampled]
        out["psnr_db"] = {"quads": len(sampled), "min": round(min(means), 2),
                          "median": round(statistics.median(means), 2)}
    control_rows = [r for r in receipts if r.get("published")]
    if control_rows:
        out["control"] = [{
            "id": r["id"],
            "our_bytes": r["output_bytes"], "published_bytes": r["published"]["bytes"],
            "our_psnr_db": r.get("psnr_db"), "published_psnr_db": r["published"]["psnr_db"],
            "published": r["published"]["describe"],
        } for r in control_rows]
    state = load_state(state_dir)
    if state["tasks"]:
        stops = [t.get("stop_code") for t in state["tasks"].values()]
        out["tasks"] = {"started": state["started"],
                        "with_end_record": sum(1 for t in state["tasks"].values() if t.get("stopped")),
                        "spot_interruptions": sum(1 for c in stops if c == "SpotInterruption")}
    print(json.dumps(out, indent=1))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("manifests")
    p.add_argument("listing_dir")
    p.add_argument("out_dir")
    p = sub.add_parser("control")
    for name in ("analytic_listing", "display_listing", "state", "year", "out_file"):
        p.add_argument(name)
    p = sub.add_parser("launch")
    p.add_argument("run_id")
    p.add_argument("manifest_key")
    p.add_argument("state_dir")
    p.add_argument("--stack", required=True)
    p.add_argument("--shards", type=int, required=True)
    p.add_argument("--only", help="comma-separated shard indexes; default all")
    p.add_argument("--limit", type=int, default=0, help="quads per shard; 0 = all")
    p.add_argument("--sample-every", type=int, default=0, help="pixel check every Nth quad")
    p.add_argument("--deadline", type=int, default=7200, help="seconds before a task stops itself")
    p.add_argument("--max-usd", type=float, required=True, help="worst-case compute bound")
    p.add_argument("--out-bucket", help="where converted files go; default the work bucket")
    p.add_argument("--out-prefix", default="", help="key prefix for converted files, ending in /")
    p.add_argument("--task-definition", help="default the stack's task_definition_arn")
    p.add_argument("--cpu", type=int, help="CPU units per task; default the task definition's")
    p.add_argument("--memory-mib", type=int, help="memory per task; default the task definition's")
    p.add_argument("--no-overlap", action="store_true",
                   help="download each quad only after the previous one is done (for comparison)")
    p = sub.add_parser("status")
    p.add_argument("run_id")
    p.add_argument("manifest_file")
    p.add_argument("--stack", required=True)
    p.add_argument("--shards", type=int, required=True)
    p = sub.add_parser("ends")
    p.add_argument("state_dir")
    p.add_argument("--stack", required=True)
    p = sub.add_parser("summarize")
    p.add_argument("receipts_dir")
    p.add_argument("state_dir")
    args = parser.parse_args()

    if args.command == "manifests":
        manifests(args.listing_dir, args.out_dir)
    elif args.command == "control":
        control(args.analytic_listing, args.display_listing, args.state, args.year, args.out_file)
    elif args.command == "launch":
        launch(args)
    elif args.command == "status":
        status(args)
    elif args.command == "ends":
        ends(args)
    else:
        summarize(args.receipts_dir, args.state_dir)


if __name__ == "__main__":
    sys.exit(main())
