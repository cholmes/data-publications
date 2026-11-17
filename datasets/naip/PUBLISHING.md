# Publishing the NAIP visualization COGs to Source Cooperative

Written 2026-11-11, before any file was uploaded. It holds the steps from the converted pilot
files to a published product, and the checks that were set for those steps before running them.
Results go in [VALIDATION.md](VALIDATION.md) as each step runs.

## Where things stand (2026-11-11)

- Three state-years are converted and sit in a private work bucket in us-west-2: Utah 2024
  (6,032 files), New Hampshire 2025 (771) and Rhode Island 2025 (116). Their receipts are in the
  same bucket under `_receipts/<run id>/`.
- The Source Cooperative product `nthh/naip` exists. Listed anonymously on 2026-11-11,
  `s3://us-west-2.opendata.source.coop/nthh/naip/` holds no objects.
- Source Cooperative was asked to let one AWS role of ours write to that prefix directly (their
  "direct uploads" path). The owner reported on 2026-11-11 that access should be in place. No
  write has been tried yet, so the grant is not confirmed.
- Manifests for all 52 state-years of 2024 and 2025 were built on 2026-11-10 from a listing of
  `s3://naip-analytic`. They are kept outside this repository (78 MB); the commands that make
  them are below.

## Where files go

```
s3://us-west-2.opendata.source.coop/nthh/naip/<state>/<year>/<resolution>/rgb/<block>/<name>.tif
```

The part after `nthh/naip/` is the same path the file would have in `s3://naip-visualization`.

Writes go straight to that bucket from tasks running in us-west-2, under the granted role, so
no transfer is billed. Source Cooperative's default upload path, `data.source.coop`, is outside
AWS, and an upload through it from us-west-2 is billed as internet egress.

The role can put and read objects under `nthh/` and cannot delete them. A wrong object can be
overwritten but not removed by us, so each step starts small.

## Steps, in order

### 1. Confirm the grant with two quads

Launch one shard of the Rhode Island manifest with `--limit 2` into the product, under a new run
id. Two files and two receipts should appear. If the task's log shows `AccessDenied` on the put,
the grant is not in place for this product and nothing else can proceed.

```sh
python3 dispatch.py launch ri2025-pub-smoke _manifests/ri-2025-60cm.jsonl <state dir> \
  --stack stack.json --task-definition <publishing task definition> \
  --out-bucket us-west-2.opendata.source.coop --out-prefix nthh/naip/ \
  --shards 1 --limit 2 --sample-every 1 --memory-mib 2048 --deadline 900 --max-usd 0.05
```

A quad whose receipt exists under the same run id is skipped. Every publishing run therefore
needs a run id that has not been used, or it converts nothing.

### 2. The three converted state-years

Convert Rhode Island 2025, New Hampshire 2025 and Utah 2024 again, straight into the product,
smallest first. Converting again is preferred to copying the files across from the work bucket:

- the converter is the only program that runs under the publishing role, and there is no copy
  tool;
- the Utah pilot files have no recorded SHA-256, and a new run records one for every file;
- it is cheap: Utah's first run was billed $0.51, and the other two together are about a sixth
  of Utah's source bytes.

Use 2 GiB tasks for these (all three are 60 cm) and `--sample-every 50`.

```sh
python3 dispatch.py launch <run id> _manifests/<state>-<year>-<res>.jsonl <state dir> \
  --stack stack.json --task-definition <publishing task definition> \
  --out-bucket us-west-2.opendata.source.coop --out-prefix nthh/naip/ \
  --shards <n> --sample-every 50 --memory-mib 2048 --deadline 3600 --max-usd <bound>

python3 dispatch.py status <run id> <local manifest file> --stack stack.json --shards <n>
python3 dispatch.py launch ... --only <shards still short>     # after a Spot interruption or a deadline
aws s3 sync s3://<work bucket>/_receipts/<run id>/ <state dir>/receipts/
python3 dispatch.py summarize <state dir>/receipts <state dir>
```

### 3. The index

One GeoParquet file per state-year, built from that run's receipts with `build_index.py`. Its
`path` column is relative to the product root, so the same file serves any host.

Where the index sits inside the product is not decided. The proposal is
`nthh/naip/index/<state>-<year>-<resolution>.parquet`. Uploading it needs the publishing role
too, so it goes up from a task, or through `data.source.coop` from outside AWS (the files are
under 1 MB each, so egress does not matter for them).

### 4. Checks on the hosted files

Set on 2026-11-11, before any upload. They are run from outside the publishing role, with
anonymous requests, because that is how a reader reaches the files.

1. **Every file is there at its size.** An anonymous listing of the state-year's prefix has
   exactly the receipts' paths, and each object's size equals the receipt's `output_bytes`.
2. **A sample is the bytes that were made.** Every 50th file, at least 20 per state-year, is
   downloaded anonymously and its SHA-256 equals the receipt's `output_sha256`.
3. **A reader can open them in place.** For the same sample, GDAL opens the file over
   `/vsis3/` with `AWS_NO_SIGN_REQUEST=YES`, reports a COG layout with JPEG compression, and
   reads one overview and one full-resolution block.
4. **The index matches.** The index has one row per listed file, and every row's `path`,
   `bytes` and `sha256` equal the receipt's.

A state-year that fails any of these is recorded as failed in VALIDATION.md with the figures,
and the failure is kept when it is later fixed.

### 5. The other 49 state-years

After steps 1 to 4 pass on the three. The estimate is about $20 of compute and requests
(`evidence/national-cost-estimate.json`), with no storage cost to us because the files are
written to Source Cooperative.

- 60 cm state-years: `--memory-mib 2048`. 30 cm: `--memory-mib 4096` (measured peak 1.5 GiB).
- A 60 cm quad takes about 6 to 9 seconds and a 30 cm quad about 31 seconds of task time. Size
  `--shards` and `--deadline` so a shard can finish, or launch short shards again with `--only`.
  The largest are Texas 2024 (17,276 quads, 60 cm) and Montana 2025 (11,745 quads, 30 cm).
- No full 30 cm state-year has run. Start with the smallest one and read its figures before
  the rest.
- The account's limit on concurrent Fargate Spot vCPUs has not been checked against a
  many-state launch.
- One Idaho 2025 quad (`m_4311118_ne_12_030_20250717`) has no data file in the source and is
  not in its manifest.

### 6. Record it

For each state-year: add it to `build.converted` in `dataset.yaml` with its run id, counts,
summary and index evidence, add its results to VALIDATION.md, then run
`python3 scripts/source_products.py write` and `python3 scripts/catalog.py --write`. The product
page text on Source Cooperative comes from `source-coop/product-README.md`, which those commands
generate. Publication status in `dataset.yaml` moves from `candidate` only when the hosted
checks have passed.

## Listing the source and building manifests

`s3://naip-analytic` is requester pays. One listing per state-year prefix, as `key<TAB>size`:

```sh
aws s3api list-objects-v2 --bucket naip-analytic --prefix "<state>/<year>/" \
  --request-payer requester --region us-west-2 \
  --query 'Contents[].[Key,Size]' --output text | gzip > <state>-<year>.tsv.gz

python3 dispatch.py manifests <listing dir> <manifest dir>
```

A manifest row names the three source files of one quad and the output path. A run reads its
manifest from the work bucket (`_manifests/<name>.jsonl`), so copy it there before launching.

## Not decided

- Where the index sits in the product (step 3), and whether there is also one national index.
- Whether the three pilot state-years are converted again (the proposal in step 2) or copied.
- What happens to the pilot files in the private work bucket once the product holds them.
- Whether to tell USDA and Esri, who maintain the source buckets, that this copy exists.
- When the workspace branch is pushed. Nothing here has been pushed or announced.
