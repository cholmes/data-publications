#!/usr/bin/env python3
"""Copy checked files from the work bucket into the product, from a task under the publishing role.

Only that role may write the product, and it exists only inside a task. This starts one task
that copies each listed object inside S3 (nothing is downloaded), then compares sizes, and
waits for it.

    python3 publish_from_work_bucket.py <copies.json> --stack stack.json --task-definition <family:rev> [--run publish-1]

copies.json: {"to_bucket": "us-west-2.opendata.source.coop",
              "copies": [{"from": "<key in the work bucket>", "to": "nthh/naip/...", "type": "<content type>"}, ...]}

The task writes <run>-result.json beside the request in the work bucket: for each copy, the
bytes at the source and at the destination. Exits 1 unless every pair matches.
"""
import argparse
import json
import subprocess
import sys

REGION = "us-west-2"
CONTAINER = "convert"
PROGRAM = r'''
import boto3, json, os
s3 = boto3.client("s3")
work = os.environ["WORK_BUCKET"]
request = json.loads(s3.get_object(Bucket=work, Key=os.environ["REQUEST_KEY"])["Body"].read())
done = []
for c in request["copies"]:
    s3.copy({"Bucket": work, "Key": c["from"]}, request["to_bucket"], c["to"],
            ExtraArgs={"ContentType": c["type"], "MetadataDirective": "REPLACE"})
    a = s3.head_object(Bucket=work, Key=c["from"])["ContentLength"]
    b = s3.head_object(Bucket=request["to_bucket"], Key=c["to"])["ContentLength"]
    done.append({"to": c["to"], "source_bytes": a, "bytes": b})
    print(c["to"], a, b, flush=True)
s3.put_object(Bucket=work, Key=os.environ["RESULT_KEY"], Body=json.dumps(done).encode(), ContentType="application/json")
'''


def aws(*args):
    out = subprocess.run(["aws", "--region", REGION, "--output", "json", *args], capture_output=True, text=True)
    if out.returncode != 0:
        raise SystemExit(out.stderr.strip())
    return json.loads(out.stdout) if out.stdout.strip() else {}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("copies")
    p.add_argument("--stack", required=True)
    p.add_argument("--task-definition", required=True)
    p.add_argument("--run", default="publish-1")
    a = p.parse_args()
    with open(a.stack) as f:
        stack = json.load(f)
    with open(a.copies) as f:
        wanted = json.load(f)
    bucket, cluster = stack["bucket_name"], stack["cluster_name"]
    request_key, result_key, program_key = (f"_publish/{a.run}-{part}" for part in ("request.json", "result.json", "copies.py"))
    for key, body in ((request_key, json.dumps(wanted)), (program_key, PROGRAM)):
        subprocess.run(["aws", "--region", REGION, "s3", "cp", "--only-show-errors", "-", f"s3://{bucket}/{key}"],
                       input=body.encode(), check=True)
    command = (f"python3 -c \"import boto3; boto3.client('s3').download_file('{bucket}','{program_key}','/tmp/publish_copies.py')\""
               " && timeout 3000 python3 /tmp/publish_copies.py")      # not copy.py: that name hides Python's own copy module
    overrides = {"cpu": "1024", "memory": "2048", "containerOverrides": [{"name": CONTAINER, "command": [command], "environment": [
        {"name": "WORK_BUCKET", "value": bucket}, {"name": "REQUEST_KEY", "value": request_key},
        {"name": "RESULT_KEY", "value": result_key}]}]}
    network = {"awsvpcConfiguration": {"subnets": stack["subnet_ids"], "securityGroups": [stack["security_group_id"]],
                                       "assignPublicIp": "ENABLED"}}
    started = aws("ecs", "run-task", "--cluster", cluster, "--task-definition", a.task_definition,
                  "--capacity-provider-strategy", "capacityProvider=FARGATE_SPOT,weight=1", "--count", "1",
                  "--started-by", a.run[:36], "--tags", f"key=run,value={a.run}",
                  "--network-configuration", json.dumps(network), "--overrides", json.dumps(overrides))
    if started.get("failures") or not started.get("tasks"):
        raise SystemExit(f"not started: {started.get('failures')}")
    arn = started["tasks"][0]["taskArn"]
    print("task", arn.rsplit("/", 1)[1], flush=True)
    subprocess.run(["aws", "--region", REGION, "ecs", "wait", "tasks-stopped", "--cluster", cluster, "--tasks", arn], check=True)
    task = aws("ecs", "describe-tasks", "--cluster", cluster, "--tasks", arn)["tasks"][0]
    print("stopped:", task.get("stopCode"), "exit", task["containers"][0].get("exitCode"), flush=True)
    out = subprocess.run(["aws", "--region", REGION, "s3", "cp", "--only-show-errors", f"s3://{bucket}/{result_key}", "-"],
                         capture_output=True, text=True)
    if out.returncode != 0:
        raise SystemExit("the task wrote no result; see its log")
    done = json.loads(out.stdout)
    wrong = [d for d in done if d["bytes"] != d["source_bytes"]]
    print(f"{len(done)} of {len(wanted['copies'])} copied, {len(wrong)} with a size that differs,",
          f"{sum(d['bytes'] for d in done):,} bytes")
    sys.exit(0 if len(done) == len(wanted["copies"]) and not wrong else 1)


if __name__ == "__main__":
    main()
