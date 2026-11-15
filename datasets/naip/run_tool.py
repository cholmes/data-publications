#!/usr/bin/env python3
"""Run one of the tools kept in the work bucket (_tools/) as a single Fargate Spot task, and wait for it.

    python3 run_tool.py <tool file name> --stack stack.json --task-definition <family:rev> \
        [--env NAME=VALUE ...] [--vcpu 4] [--memory-gb 16] [--disk-gb 21] [--deadline 3000] [--run name]

The task downloads s3://<work bucket>/_tools/<tool> and runs it with python3 under the
deadline, with WORK_BUCKET set and each --env added. Used for the tools that need to be
beside the buckets or under the task's role: sample_hosted.py, national.py.
Exits with the container's exit code (1 when the task did not start or was interrupted).
"""
import argparse
import json
import subprocess
import sys

REGION = "us-west-2"
CONTAINER = "convert"


def aws(*args):
    out = subprocess.run(["aws", "--region", REGION, "--output", "json", *args], capture_output=True, text=True)
    if out.returncode != 0:
        raise SystemExit(out.stderr.strip())
    return json.loads(out.stdout) if out.stdout.strip() else {}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("tool")
    p.add_argument("--stack", required=True)
    p.add_argument("--task-definition", required=True)
    p.add_argument("--env", action="append", default=[], metavar="NAME=VALUE")
    p.add_argument("--vcpu", type=int, default=4)
    p.add_argument("--memory-gb", type=int, default=16)
    p.add_argument("--disk-gb", type=int, default=21)
    p.add_argument("--deadline", type=int, default=3000)
    p.add_argument("--run")
    a = p.parse_args()
    with open(a.stack) as f:
        stack = json.load(f)
    bucket, cluster = stack["bucket_name"], stack["cluster_name"]
    run = a.run or a.tool.rsplit(".", 1)[0]
    command = (f"python3 -c \"import boto3; boto3.client('s3').download_file('{bucket}','_tools/{a.tool}','/tmp/{a.tool}')\""
               f" && timeout {a.deadline} python3 /tmp/{a.tool}")
    environment = [{"name": "WORK_BUCKET", "value": bucket}] + [dict(zip(("name", "value"), e.split("=", 1))) for e in a.env]
    overrides = {"cpu": str(a.vcpu * 1024), "memory": str(a.memory_gb * 1024), "ephemeralStorage": {"sizeInGiB": a.disk_gb},
                 "containerOverrides": [{"name": CONTAINER, "command": [command], "environment": environment}]}
    network = {"awsvpcConfiguration": {"subnets": stack["subnet_ids"], "securityGroups": [stack["security_group_id"]],
                                       "assignPublicIp": "ENABLED"}}
    started = aws("ecs", "run-task", "--cluster", cluster, "--task-definition", a.task_definition,
                  "--capacity-provider-strategy", "capacityProvider=FARGATE_SPOT,weight=1", "--count", "1",
                  "--started-by", run[:36], "--tags", f"key=run,value={run}",
                  "--network-configuration", json.dumps(network), "--overrides", json.dumps(overrides))
    if started.get("failures") or not started.get("tasks"):
        raise SystemExit(f"not started: {started.get('failures')}")
    arn = started["tasks"][0]["taskArn"]
    print("task", arn.rsplit("/", 1)[1], flush=True)
    subprocess.run(["aws", "--region", REGION, "ecs", "wait", "tasks-stopped", "--cluster", cluster, "--tasks", arn], check=True)
    task = aws("ecs", "describe-tasks", "--cluster", cluster, "--tasks", arn)["tasks"][0]
    code = task["containers"][0].get("exitCode")
    print("stopped:", task.get("stopCode"), task.get("stoppedReason"), "exit", code, flush=True)
    sys.exit(1 if code is None else code)


if __name__ == "__main__":
    main()
