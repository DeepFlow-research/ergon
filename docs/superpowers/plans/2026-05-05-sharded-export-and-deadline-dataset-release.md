# Sharded Export And Deadline Dataset Release Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Ergon-native incremental sharded export so the rollout-card artifact can publish verified sub-1GB datasets first, retar Ergon, and leave large-dataset ETL/export jobs running overnight.

**Architecture:** Ergon owns export semantics: pagination, Parquet/JSONL shard writing, resource descriptors, resource copy/linking, manifests, checksums, and resume state. The rollout-card artifact remains a thin orchestrator that fetches sources, invokes Ergon CLI commands, packages generated shards for Hugging Face, and documents NeurIPS submission status.

**Tech Stack:** Python 3.13, SQLModel/Postgres, Ergon ingestion models, `pyarrow` for Parquet, content-addressed resource files, Hugging Face dataset layout.

---

## Deadline Strategy

The submission path is intentionally staged:

1. Implement Ergon-native sharded export and retar Ergon.
2. Run and publish all sub-1GB datasets first within the next one to two hours.
3. Verify shard format, manifests, resource hashes, reducer rows, and drops rows.
4. Push verified sub-1GB exports to the Hugging Face org and include that org/link in the NeurIPS upload.
5. Start large ETL/export jobs overnight with the same resumable exporter.
6. Update the hosted HF collection as large datasets complete.

The OpenReview upload should not contain full 50-100GB derived data. It should contain code, Ergon tarball, Croissant/manifests where available, smoke fixtures, and links to hosted HF datasets.

## Dataset Triage

Use the latest local size audit from `rollout-card-artifact/outputs/verification/dataset_size_audit.json`.

### First-wave datasets

Run these first because configured input/prepared size is below 1GB:

- `agentharm`
- `atbench`
- `bfcl`
- `debate_mallm`
- `gpqa`
- `maestro`
- `miniwob`
- `stabletoolbench`
- `tau_bench`
- `tot_crosswords`
- `tot_game24`
- `weblinx`

`debate_mallm`, `gpqa`, and `stabletoolbench` are still meaningful enough to watch, but they are under 1GB and should finish quickly relative to the large sets.

### Overnight datasets

Run after the first wave is published:

- `agent_reward_bench`
- `openhands_swe_rebench`
- `swe_smith`

These dominate local storage and runtime. They must use the same sharded/resumable exporter and must not require one giant in-memory or single-file export.

## File Structure

### Add to Ergon

- `ergon_ingestion/ergon_ingestion/exports/__init__.py`
  - Package marker for export helpers.
- `ergon_ingestion/ergon_ingestion/exports/models.py`
  - Pydantic/dataclass models for export config, shard manifests, resource descriptors, and dataset manifests.
- `ergon_ingestion/ergon_ingestion/exports/sharded.py`
  - Core sharded exporter. Owns DB pagination, Parquet/JSONL writing, resource copy/linking, checksums, and resume state.
- `ergon_ingestion/ergon_ingestion/exports/verify.py`
  - Verifier for generated export directories: checks counts, resources, hashes, non-empty reducers/drops, and no truncation markers.
- `ergon_ingestion/ergon_ingestion/cli.py`
  - Add `ergon ingest export` or wire an export subcommand under the existing ingestion CLI surface if that is the least invasive deadline path.
- `ergon_cli/ergon_cli/main.py`
  - Register the CLI route if needed.
- `ergon_ingestion/tests/unit/test_sharded_export.py`
  - Unit tests for shard rollover, resume behavior, manifest shape, and resource hash validation.
- `docs/architecture/cross_cutting/artifacts.md`
  - Update architecture docs to state Ergon owns sharded dataset exports and artifact repos only orchestrate them.

### Keep in rollout-card-artifact as wrapper/orchestration

- `artifact_tools/export_reanalysis.py`
  - Convert into a compatibility shim that imports Ergon exporter functions and passes artifact-specific arguments through to them.
  - It must not implement pagination, sharding, resource copying, checksum generation, manifest writing, or verification itself.
- `artifact_tools/package_hf.py`
  - Keep HF-specific packaging/readme/upload behavior here, but make it consume Ergon export directories rather than inventing export semantics.
- `scripts/05_export_reanalysis_inputs.sh`
  - Point at the new Ergon export command.
- `scripts/run_all_cards.sh`
  - Run datasets in first-wave/overnight order, with resume enabled.

## Export Format

Each dataset export directory should look like:

```text
outputs/ergon-export/<batch>/<dataset>/
  manifest.json
  checksums.json
  state.json
  runs/
    runs-00000.parquet
    runs-00001.parquet
  reducers/
    reducers-00000.parquet
  drops/
    drops-00000.parquet
  resources/
    ab/
      <sha256>.json
```

The Hugging Face package can mirror this directory or copy it under `outputs/huggingface/<dataset>/`.

### Manifest requirements

`manifest.json` must include:

- `dataset`
- `batch`
- `created_at`
- `exporter_version`
- `source_url`
- `source_version_ref`
- `run_count`
- `reducer_count`
- `drop_count`
- `resource_count`
- `resource_total_bytes`
- `shards`
- `malformed_source_records`
- `verification`

### Shard rules

- Default `shard_size_mb`: 256.
- Default `page_size`: 1000 runs.
- Runs, reducers, and drops are separate shard families.
- Shards are append-only within a run. On resume, completed shards listed in `state.json` are not rewritten.
- Temporary shard path is `<name>.tmp`; rename atomically to final name after writing and checksum.

### Resource rules

- Postgres stores only descriptors: path, size, hash, kind, MIME type, metadata.
- Full payloads live as blob files.
- Export should copy or hardlink blob files into `resources/<sha256[:2]>/<sha256><suffix>`.
- If a destination resource already exists with matching hash and size, skip copy.
- If a destination resource exists with mismatched hash or size, fail loudly.

## CLI Design

Deadline-friendly command:

```bash
ergon ingest export \
  --batch hf-trace-publication-v1 \
  --dataset weblinx \
  --output outputs/ergon-export/hf-trace-publication-v1/weblinx \
  --format parquet \
  --page-size 1000 \
  --shard-size-mb 256 \
  --resume
```

Batch wrapper command, if time permits:

```bash
ergon ingest export-batch \
  --batch hf-trace-publication-v1 \
  --output outputs/ergon-export/hf-trace-publication-v1 \
  --dataset agentharm \
  --dataset atbench \
  --resume
```

If adding a top-level `ergon export` command is straightforward, prefer that. If routing is risky before the deadline, use `ergon ingest export` now and rename later.

## Implementation Tasks

### Task 1: Define Export Models

**Files:**

- Create: `ergon_ingestion/ergon_ingestion/exports/__init__.py`
- Create: `ergon_ingestion/ergon_ingestion/exports/models.py`
- Test: `ergon_ingestion/tests/unit/test_sharded_export.py`

- [ ] Add models for `ShardedExportConfig`, `ShardRecord`, `DatasetExportManifest`, and `ExportState`.
- [ ] Include fields for dataset, batch, output path, page size, shard size, resume flag, and resource policy.
- [ ] Test JSON serialization produces stable sorted keys.
- [ ] Test `ExportState` can record completed shard names and resume cursor fields.

### Task 2: Implement Paginated DB Reader

**Files:**

- Create/modify: `ergon_ingestion/ergon_ingestion/exports/sharded.py`
- Test: `ergon_ingestion/tests/unit/test_sharded_export.py`

- [ ] Move the query logic currently embedded in `rollout-card-artifact/artifact_tools/export_reanalysis.py` into Ergon.
- [ ] Page `RunRecord` rows by stable order: `sample_id`, `instance_key`, `id`.
- [ ] For each run, fetch annotations, resources, reducers, and drops.
- [ ] Convert rows into export dictionaries equivalent to the current reanalysis payload, but without inlining resource payloads.
- [ ] Print progress every 100 runs: `exported_runs: N`.

### Task 3: Add Parquet Shard Writer

**Files:**

- Modify: `ergon_ingestion/ergon_ingestion/exports/sharded.py`
- Test: `ergon_ingestion/tests/unit/test_sharded_export.py`

- [ ] Use `pyarrow` to write `runs`, `reducers`, and `drops` shard families.
- [ ] Use JSON string columns for nested structures:
  - `observed_fields_json`
  - `missing_fields_json`
  - `annotations_json`
  - `resources_json`
  - `output_json`
  - `evidence_json`
- [ ] Roll over to a new shard when estimated uncompressed row payload exceeds `shard_size_mb`.
- [ ] Write to `.tmp` and atomically rename after checksum calculation.
- [ ] Record each completed shard in `state.json`.

### Task 4: Copy Or Link Resources Incrementally

**Files:**

- Modify: `ergon_ingestion/ergon_ingestion/exports/sharded.py`
- Test: `ergon_ingestion/tests/unit/test_sharded_export.py`

- [ ] For every `RunResource`, resolve its `file_path`.
- [ ] Copy or hardlink to `resources/<sha256[:2]>/<sha256><suffix>`.
- [ ] Skip resources already present with matching hash and size.
- [ ] Fail on missing source files.
- [ ] Fail on hash mismatch.
- [ ] Add resource copy counts and bytes to manifest/state.

### Task 5: Add Export Verification

**Files:**

- Create: `ergon_ingestion/ergon_ingestion/exports/verify.py`
- Test: `ergon_ingestion/tests/unit/test_sharded_export.py`

- [ ] Verify `manifest.json`, `checksums.json`, and `state.json` exist.
- [ ] Verify every listed shard exists and matches checksum.
- [ ] Verify resource files match hash and size.
- [ ] Verify `run_count > 0`, `reducer_count > 0`, and `drop_count > 0` unless `--allow-empty-drops` is explicitly set.
- [ ] Scan exported JSON fields and resources for truncation markers:
  - `[truncated]`
  - `<truncated>`
  - `...<truncated>`
  - `__TRUNCATED__`
  - `truncated_payload`

### Task 6: Wire CLI

**Files:**

- Modify: `ergon_ingestion/ergon_ingestion/cli.py`
- Modify: `ergon_cli/ergon_cli/main.py` if required by command routing.
- Test: CLI unit or smoke command.

- [ ] Add command parser support for `ergon ingest export`.
- [ ] Add arguments:
  - `--dataset`
  - `--batch`
  - `--output`
  - `--format parquet`
  - `--page-size`
  - `--shard-size-mb`
  - `--resume`
  - `--allow-empty-drops`
- [ ] Print final summary:
  - runs
  - reducers
  - drops
  - resources
  - total bytes
  - output path

### Task 7: Convert Artifact Export Wrapper

**Files:**

- Modify: `rollout-card-artifact/artifact_tools/export_reanalysis.py`
- Modify: `rollout-card-artifact/scripts/05_export_reanalysis_inputs.sh`

- [ ] Keep the old JSONL exporter available only as a legacy mode if needed.
- [ ] Default to invoking the new Ergon sharded export command.
- [ ] Write outputs to `outputs/ergon-export/<batch>/<dataset>/`.
- [ ] Keep current summary JSON output for compatibility if scripts expect it.

### Task 8: Package Hugging Face Layout

**Files:**

- Modify: `rollout-card-artifact/artifact_tools/package_hf.py`
- Modify: `rollout-card-artifact/scripts/10_package_hf_datasets.sh`

- [ ] Package sharded Ergon export directories without rewriting shards.
- [ ] Copy README and `dataset_info.json`.
- [ ] Include `manifest.json`, `checksums.json`, and resource files.
- [ ] Avoid copying resource blobs if package directory already contains matching hash/size.
- [ ] Emit `package_manifest.json` with HF repo names and local paths.

### Task 9: Update Architecture Docs

**Files:**

- Modify: `docs/architecture/cross_cutting/artifacts.md`

- [ ] Add a section: “Sharded Dataset Export”.
- [ ] State that Ergon owns export format, resource integrity, resume state, and manifest generation.
- [ ] State that paper/artifact repos own orchestration and paper-specific packaging only.

### Task 10: Retar Ergon

**Files:**

- Output in rollout artifact: `rollout-card-artifact/third_party/ergon-anonymous-src.tar.gz`
- Verify with: `rollout-card-artifact/scripts/00_checkout_ergon.sh`

- [ ] Copy or synchronize the modified local Ergon checkout into `rollout-card-artifact/third_party/ergon`.
- [ ] Rebuild `third_party/ergon-anonymous-src.tar.gz`.
- [ ] Extract into a temporary directory and verify the new export modules exist.
- [ ] Run anonymity audit.

### Task 11: First-Wave Run And Publish

**Files/Commands:**

- `rollout-card-artifact/scripts/run_all_cards.sh`
- `rollout-card-artifact/scripts/10_package_hf_datasets.sh`
- `rollout-card-artifact/scripts/11_upload_hf_datasets.sh`

- [ ] Run ingest/export/package for first-wave datasets only:

```bash
FIRST_WAVE=(
  agentharm
  atbench
  bfcl
  debate_mallm
  gpqa
  maestro
  miniwob
  stabletoolbench
  tau_bench
  tot_crosswords
  tot_game24
  weblinx
)
```

- [ ] Verify sharded output for each dataset.
- [ ] Package for HF.
- [ ] Upload to HF org.
- [ ] Record HF URLs in upload notes.

### Task 12: Overnight Large Runs

**Datasets:**

- `agent_reward_bench`
- `openhands_swe_rebench`
- `swe_smith`

- [ ] Start each large dataset as an independent resumable job.
- [ ] Log output to `outputs/logs/<dataset>-overnight.log`.
- [ ] Verify progress every 30-60 minutes if awake, otherwise rely on `state.json`.
- [ ] On failure, rerun with `--resume`.
- [ ] Upload completed large datasets to the same HF org/collection.

## Verification Commands

Run these before claiming success:

```bash
cd /Users/charliemasters/Desktop/synced_vm_002/ergon
PYTHONPATH="ergon_ingestion:ergon_core" uv run pytest -q ergon_ingestion/tests/unit
```

```bash
cd /Users/charliemasters/Desktop/synced_vm_002/ergon_submission_bundle/rollout-card-artifact
scripts/00_checkout_ergon.sh "$(mktemp -d)/ergon"
scripts/audit_anonymity.sh
```

For each exported dataset:

```bash
ergon ingest export \
  --dataset DATASET \
  --batch hf-trace-publication-v1 \
  --output outputs/ergon-export/hf-trace-publication-v1/DATASET \
  --format parquet \
  --resume
```

Then verify:

```bash
ergon ingest verify-export \
  --output outputs/ergon-export/hf-trace-publication-v1/DATASET
```

If `verify-export` is not implemented as a CLI command, run the verifier module directly from the Ergon project.

## Acceptance Criteria

- Ergon contains the sharded export implementation.
- Artifact export logic is a wrapper, not the owner of export semantics.
- Ergon tarball is refreshed and checkout-verified.
- At least all first-wave sub-1GB datasets export to sharded Parquet with manifests and checksums.
- First-wave datasets are uploaded to HF and linked in the NeurIPS upload material.
- Large datasets can run overnight independently and resume from `state.json`.
- No generated full dataset needs to be included in the OpenReview zip.

