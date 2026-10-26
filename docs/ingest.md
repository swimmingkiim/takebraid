# Metadata ingest (TB-101)

```bash
takebraid ingest ./raw/clip.mov --project ./workspace/demo
```

Requires FFprobe on PATH. Source must be a regular local video file; URLs and cover-art-only audio
files are not accepted. Paths are resolved, source data is opened read-only and no media is copied.
FFprobe receives a structured argument list, file-only protocol access and a 30-second timeout.
Containers requiring network access are unsupported. Local references inside containers are not
sandboxed by the protocol whitelist; do not treat the probe process as an untrusted-media sandbox.

## Output

Success prints the absolute metadata path and returns 0:

```text
<project>/assets/sha256-<full-content-digest>/asset.json
```

Errors return 1 with a message on stderr. Existing metadata is never overwritten, including on
repeat ingest of identical bytes. Use another project directory for an independent registration.
Relinking existing assets, batch ingest and a root `project.json` registry are future work.

Schema v0.1 records:

- `schema_version`, content-derived `asset_id` and Takebraid version.
- `source`: resolved locator, byte size, mtime in nanoseconds and full-file SHA-256 fingerprint.
- `metadata`: format, reported start/duration, all streams, FFprobe version and warning codes.
- `timing_status`: `metadata_only_unverified_frame_timestamps`.

Each stream preserves its index/type, codec, exact rational time base, signed `start_pts`, integer
`duration_ts`, reported start/duration, nominal/average frame rates, dimensions, rotation/display
matrix, pixel format/color metadata, audio sample rate/channels/layout and attached-picture flag.
Unreported values are JSON null. Fractions serialize as `{numerator, denominator}` objects;
reported decimal seconds are preserved as exact fractions of their reported decimal value.
They do not replace source PTS, and no frame positions are computed from FPS.

Display-matrix rotation takes precedence over legacy `rotate` tags, and the original matrix is
retained for mirrored transforms. Rotation is recorded, not applied. Video and audio streams need
a positive time base. Multiple video streams are retained with an explicit-selection warning;
ingest chooses no primary stream. Missing audio is valid.

## Timing limits

Ingest does not scan frames or packets, classify CFR/VFR, validate presentation continuity, decode
proxies, choose cuts or render video. FPS, container duration and stream duration are observations,
not guarantees of valid frame boundaries. A missing/invalid A/V time base is rejected; missing start
PTS/duration is retained as unknown. Every result includes `frame_timestamps_not_scanned`.
Use the separate [scan command](frame-maps.md) for decoded PTS maps and frame-boundary validation.
The original ingest metadata is retained unchanged; use the scan report for verified timing status.

## Publication and integrity

The source's identity/size/mtime/ctime are checked around hashing and probing. A detected source
change aborts without publishing metadata. This detects ordinary concurrent changes, not adversarial
changes designed to evade filesystem metadata checks. Sources should remain stable during ingest.

The writer flushes a temporary file, then creates a same-filesystem hard link to publish the complete
JSON without replacing an existing destination. Temporary files are cleaned on failure. Project
storage must support hard links (for example APFS, ext4 or NTFS); unsupported filesystems return an
error. This gives no-clobber publication, not a multi-file transaction or power-loss durability.

## Validation

```bash
python -m pytest -m "not integration" --strict-markers
python -m pytest -m integration --strict-markers
```

The integration suite generates short blue FFV1/Matroska video with optional PCM sine audio and
checks real FFprobe output, fractional rate preservation and source fingerprints. Unit tests cover
rotation, signed PTS, multiple streams, unknown/malformed metadata, tool errors, changed sources and
no-clobber publication. See `tests/fixtures/README.md` for fixture provenance.
