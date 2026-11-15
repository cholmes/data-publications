#!/usr/bin/env python3
"""Start one Fargate Spot task per overview request, sized by its quads, and say which are done.

    python3 launch_overviews.py launch <requests dir> <state.json> --stack stack.json --task-definition <family:rev> \
        [--only name,name] [--max-vcpu 480] [--run overviews-1]
    python3 launch_overviews.py status <requests dir> <state.json> --stack stack.json

A request is one file made by make_overview_requests.py. It is done when its result exists in
the work bucket; `launch` skips those and any whose recorded task is still running, so running
it again starts only what an interruption left unfinished. Nothing has to stay running.

Size: a build reads on many threads, copies the mosaic on one and writes on all, so small
files get 2 vCPUs and only the large ones 8 (SIZES). Disk is 1.3 MB a quad for the staged
levels and as much again for the mosaic copy, with half as much again spare. Each task stops
itself after its deadline, which bounds what a stuck task can spend.
"""
import argparse
import json
import math
import os
import subprocess
import time

REGION = "us-west-2"
CONTAINER = "convert"
# quads up to, vCPU units, memory MiB, read threads, deadline seconds
SIZES = [(600, 2048, 8192, 16, 1800), (3000, 4096, 16384, 24, 2700), (10 ** 9, 8192, 32768, 32, 3600)]
MB_PER_QUAD = 1.3


def aws(*args, check=True):
    out = subprocess.run(["aws", "--region", REGION, "--output", "json", *args], capture_output=True, text=True)
    if out.returncode != 0:
        if check:
            raise SystemExit(out.stderr.strip())
        return None
    return json.loads(out.stdout) if out.stdout.strip() else {}


def requests(folder, only):
    for name in sorted(os.listdir(folder)):
        if name.endswith("-request.json") and (not only or name[:-len("-request.json")] in only):
            with open(os.path.join(folder, name)) as f:
                yield json.load(f)


def present(bucket, keys):
    """Which of these keys exist, from one listing of each folder they are in."""
    found = set()
    for prefix in {key.rsplit("/", 1)[0] + "/" for key in keys}:
        out = subprocess.run(["aws", "--region", REGION, "s3api", "list-objects-v2", "--bucket", bucket, "--prefix", prefix,
                              "--query", "Contents[].Key", "--output", "json"], capture_output=True, text=True, check=True).stdout
        found |= set(json.loads(out) or [])
    return found & set(keys)


def running(cluster, arns):
    """Of these task ARNs, the ones not yet stopped, with their vCPU units."""
    alive = {}
    for i in range(0, len(arns), 100):
        for task in aws("ecs", "describe-tasks", "--cluster", cluster, "--tasks", *arns[i:i + 100]).get("tasks", []):
            if task["lastStatus"] != "STOPPED":
                alive[task["taskArn"]] = int(task["cpu"])
    return alive


def load(path):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {"tasks": {}}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("action", choices=["launch", "status"])
    p.add_argument("requests_dir")
    p.add_argument("state")
    p.add_argument("--stack", required=True)
    p.add_argument("--task-definition")
    p.add_argument("--only", default="")
    p.add_argument("--max-vcpu", type=int, default=480)
    p.add_argument("--run", default="overviews-1")
    a = p.parse_args()
    with open(a.stack) as f:
        stack = json.load(f)
    bucket, cluster = stack["bucket_name"], stack["cluster_name"]
    state = load(a.state)
    todo = list(requests(a.requests_dir, set(filter(None, a.only.split(",")))))
    arns = [t["arn"] for tasks in state["tasks"].values() for t in tasks]
    alive = running(cluster, arns) if arns else {}
    have = present(bucket, [r["result_key"] for r in todo])
    done = [r for r in todo if r["result_key"] in have]
    flying = [r for r in todo if r not in done and any(t["arn"] in alive for t in state["tasks"].get(r["name"], []))]
    rest = [r for r in todo if r not in done and r not in flying]
    print(f"{len(done)} of {len(todo)} done, {len(flying)} running, {len(rest)} to start", flush=True)
    if a.action == "status":
        for r in rest:
            print("not done and not running:", r["name"], len(r["quads"]), "quads, tasks started:", len(state["tasks"].get(r["name"], [])))
        return
    network = {"awsvpcConfiguration": {"subnets": stack["subnet_ids"], "securityGroups": [stack["security_group_id"]],
                                       "assignPublicIp": "ENABLED"}}
    for r in sorted(rest, key=lambda r: -len(r["quads"])):
        quads = len(r["quads"])
        _, cpu, memory, threads, deadline = next(s for s in SIZES if quads <= s[0])
        while sum(running(cluster, list(alive)).values()) + cpu > a.max_vcpu * 1024:
            time.sleep(20)
        key = f"_overviews/{a.run}/{r['name']}-request.json"
        with open(os.path.join(a.requests_dir, r["name"] + "-request.json"), "rb") as f:
            subprocess.run(["aws", "--region", REGION, "s3", "cp", "--only-show-errors", "-", f"s3://{bucket}/{key}"],
                           stdin=f, check=True)
        command = (f"python3 -c \"import boto3; boto3.client('s3').download_file('{bucket}','_tools/overview.py','/tmp/overview.py')\""
                   f" && timeout {deadline} python3 /tmp/overview.py")
        overrides = {"cpu": str(cpu), "memory": str(memory),
                     "ephemeralStorage": {"sizeInGiB": max(21, math.ceil(quads * MB_PER_QUAD * 2 * 1.5 / 1000) + 5)},
                     "containerOverrides": [{"name": CONTAINER, "command": [command], "environment": [
                         {"name": "WORK_BUCKET", "value": bucket}, {"name": "REQUEST_KEY", "value": key},
                         {"name": "THREADS", "value": str(threads)}]}]}
        result = aws("ecs", "run-task", "--cluster", cluster, "--task-definition", a.task_definition,
                     "--capacity-provider-strategy", "capacityProvider=FARGATE_SPOT,weight=1", "--count", "1",
                     "--started-by", a.run[:36], "--tags", f"key=run,value={a.run}",
                     "--network-configuration", json.dumps(network), "--overrides", json.dumps(overrides))
        if result.get("failures") or not result.get("tasks"):
            print(f"{r['name']}: not started: {result.get('failures')}; stopping here", flush=True)
            break
        arn = result["tasks"][0]["taskArn"]
        alive[arn] = cpu
        state["tasks"].setdefault(r["name"], []).append({"arn": arn, "cpu": cpu, "memory": memory, "quads": quads,
                                                         "started": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
        with open(a.state, "w") as f:
            json.dump(state, f, indent=1)
        print(f"{r['name']}: {quads} quads, {cpu // 1024} vCPU, {memory // 1024} GB", flush=True)


if __name__ == "__main__":
    main()
