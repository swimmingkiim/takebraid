# Projects, validated records and stage execution (TB-103)

Ingest now automatically registers metadata in a project. Originals and `asset.json` remain
immutable; the registry owns the current source locator and preserves prior revisions.

```bash
takebraid project init ./workspace/demo
takebraid ingest ./raw/clip.mov --project ./workspace/demo
takebraid project show ./workspace/demo
takebraid project verify ./workspace/demo
takebraid project relink ./workspace/demo sha256-<digest> ./moved/clip.mov
takebraid scan ./workspace/demo/assets/sha256-<digest>/asset.json --stream 0
# Reuse validated output on repeat; preserve a new attempt when forced:
takebraid scan ./workspace/demo/assets/sha256-<digest>/asset.json --stream 0 --force
```

For TB-101/TB-102 projects created before a registry existed, explicitly add each existing metadata
file with `takebraid project add <project> <asset.json>`. Metadata must be inside the project; media
can remain elsewhere. Existing standalone metadata can still be scanned without a registry.
Legacy `frames-<stream>.json` reports remain intact/readable, but are not silently promoted to
completed stage caches; the first scan under this implementation creates its own verified attempt.

## Registry and source identity

`project.json` v0.1 stores UUID `project_id`, integer `revision`, an `assets` dictionary and additive
fields such as editor annotations. Asset entries contain project-relative `metadata_path` and an
absolute `source_locator`. Normalized metadata, content IDs and referenced paths are validated on
load. Relative paths escaping the project, including resolved symlinks, are rejected.

Relink requires a full SHA-256 match to the original asset. It changes only the registry locator,
not the original metadata or source. Asset readers recognize absolute Windows/POSIX locators so
projects can be opened on another OS before relinking to an accessible native path. Verification
does not trust old size/mtime alone: it hashes sources and detects ordinary concurrent changes.

`project verify` returns 0 when all registered sources verify, 2 for missing/changed sources, and 1
for malformed registry/metadata or I/O errors. Empty projects verify vacuously. `show` describes the
registry without requiring source media to be mounted. All other project command errors return 1.

Updates hold an exclusive `.project.lock`, write an immutable `history/project-<revision>.json`
snapshot, then atomically replace the current registry. Unknown additive fields/annotations are
retained. An interrupted publication can leave an orphan snapshot; retries advance beyond it
without overwriting history. Revision numbers may have gaps. `init` and repeated `add` are idempotent.

This serializes cooperating commands, not arbitrary outside edits. Edit annotations only between
commands. Lock files are never automatically stolen: after a killed process, confirm no writer is
running before manually removing a stale lock. Initial ingest metadata publication and registry
update are not one transaction; if registration fails, the immutable asset remains recoverable with
`project add`. There is no automatic deletion or rollback of original media.

## Validated record loaders

`adapters.records` rejects unknown schema versions, duplicate JSON keys, nonfinite numbers,
invalid identities, clocks and consumed metadata types. Asset records are limited to 2 MiB; general
records to 128 MiB. Additive annotation fields are allowed; frame observation fields remain a strict
domain contract. Asset loading does not assert source availability.

Frame-map loading reconstructs `FrameObservation` and `FrameMap`, recomputes timing status/issues,
cadence and final end, and rejects inconsistent saved summaries/provenance. An edited `status:
ready` flag cannot bypass timing rules. Ready-map range validation remains the execution boundary.
These are integrity checks, not digital signatures or protection against an attacker rewriting all
artifacts and checksums.

## Stage keys, attempts and cache validation

The scan recipe uses a SHA-256 of canonical JSON inputs: source digest, recipe version, Takebraid
version, FFprobe version and settings (stream index, timeout, frame limit). Key ordering is ignored;
changed inputs create another stage. Absolute paths/editor annotations are not analysis inputs.
The recipe version must change when analysis semantics change even during an unchanged dev version.

```text
project.json
history/project-000000.json
assets/sha256-<digest>/asset.json
stages/<input-key>/
  completed.json                 # atomic derived pointer to a validated completed attempt
  attempts/<uuid>/
    started.json                 # running record
    frames.json                  # immutable output if produced
    receipt.json                 # completed / failed / cancelled
```

Before a cache hit, scan still verifies the source hash and current FFprobe/stream clock. The
completion pointer must match its terminal attempt receipt, exact inputs/key, an output inside
that attempt and its SHA-256. The frame-map loader then validates the domain evidence and source
identity/clock. A missing pointer is a cache miss; a corrupt pointer/output is an error suggesting
`--force`, never an accepted hit. A completed scan can legitimately contain unsupported timing:
the scan finished, but those boundaries remain unusable for editing.

`--force` creates another attempt and atomically advances the completion pointer after validation;
old outputs/receipts survive. Once an attempt starts, failure and Ctrl-C produce terminal receipts
without publishing a completion pointer. Preflight errors (source/asset/tool verification) do not
start an attempt. Existing successful pointers survive failed forced runs. SIGKILL/power loss may
leave only a running record or an orphan completed attempt; neither is reused without a matching
validated pointer. Parallel scans can do duplicate work; each writes a separate attempt and the
last valid completion pointer wins. This is safe publication, not deduplicated job scheduling.

Receipts store error type rather than private traceback/source details. Logs and automatic
model/network telemetry are not added. No disk garbage collection, lock recovery, power-loss
durability or adversarial filesystem snapshot isolation is promised in this slice.
