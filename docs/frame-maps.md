# Decoded frame maps (TB-102)

After ingest, explicitly select the absolute video stream index from `asset.json`:

```bash
takebraid scan ./workspace/demo/assets/sha256-<digest>/asset.json --stream 0
```

The scanner validates the asset/content ID, resolves registry relinks, rehashes the source and probes
current stream metadata. It reuses a validated completed scan or decodes frames into a new preserved
stage attempt at `stages/<key>/attempts/<uuid>/frames.json`. `--force` creates a new attempt without
replacing old outputs. Original asset metadata stays unchanged. Selecting audio/cover art or changed
media fails. No source media or proxy is created/modified. See [projects and cache rules](projects.md).

## Contract and status

The v0.1 report stores `frame_map` (asset, stream, rational clock, ordered frame observations),
derived `status`, `issues` with frame indices, `cadence`, `presentation_end_pts` and provenance.
Each observation preserves integer `pts`, optional decoder `duration` and optional
`best_effort_timestamp`. Older FFprobe's `pkt_duration` is used only when `duration` is absent;
duration is still a reported observation, not independent proof of playback correctness.

No timestamps are synthesized, sorted, deduplicated or recovered from FPS. Missing raw PTS remains
missing even when FFprobe provides a best-effort timestamp. Presentation order comes from decoded
frames, not packet DTS. Signed/nonzero starts are preserved.

| Status | Meaning | CLI exit |
|---|---|---|
| `ready` | Increasing raw PTS, known positive final duration, no observed duration conflicts | 0 |
| `review_required` | Reported duration disagrees with the next increasing PTS | 2 |
| `unsupported` | Empty decode, missing/non-increasing PTS, nonpositive duration, or unknown final end | 2 |
| No report | Invalid asset/source, tool/decode errors, timeout/limits or publication failure | 1 |

An irregular PTS gap alone cannot distinguish a held VFR frame from damaged timing. If a reported
duration conflicts with that gap, flag it for review rather than silently bridging or declaring
corruption. Missing internal durations are acceptable when the next observed PTS establishes the
presentation boundary; the final frame must have its own positive duration. Its end is
`last_pts + last_duration`. Stream/container duration and average FPS are never fallback endpoints.

`cadence` describes observed adjacent PTS intervals (`uniform_pts_intervals`,
`variable_pts_intervals`, `unknown`). Uniform PTS does not prove a camera's entire capture was CFR;
one frame provides insufficient evidence. Decoder errors, even with process exit 0, fail the scan
so a partial decode cannot become a ready map.

## Editing boundaries

`FrameMap.validate_range(SourceRange(...))` checks asset, stream, clock and exact frame boundaries.
It refuses both uncertain statuses. Intervals remain half-open: a cut can end at the final
presentation end, but cannot start there. Merely falling within the source duration is insufficient.
The frame-map loader reconstructs domain values and derives status, rejecting inconsistent summaries;
an editable JSON `status` field cannot authorize cuts. Cache reuse runs this validation again.

## Proxy/sample coordinate mapping

`domain.frames.map_proxy_samples` maps a tuple of observed proxy PTS to source frame indices/PTS.
The caller supplies both rational clocks and explicit source/proxy origins for an established 1x,
unretimed relationship. The function converts elapsed time exactly, then finds the active source
frame in `[source_pts, next_pts)`. Repeated source-frame mappings during upsampling are valid.
Samples at/after the final end, before the first frame, or out of increasing proxy order fail.
Uncertain source maps fail. There is no clamping or image interpolation.

This is a coordinate-mapping API, not proxy generation or independent proof that two videos depict
the same moments. Retiming, speed ramps, arbitrary offsets inferred from images, audio synchronization
and persisted proxy manifests remain outside this slice.

## Resource and repair policy

Default decode timeout is 300 seconds (`--timeout`), and the parsed map limit is 250,000 frames
(`--max-frames`). FFprobe output is spooled to temporary disk before parsing, avoiding a second full
raw JSON tree in RAM. Map records and final JSON are still O(frame count) memory; temporary disk grows
with decoded output until timeout. The frame limit applies after decoding, not as a decode-work limit.
Media subprocesses are not a security sandbox. Raise limits deliberately for long recordings.

Publication reuses TB-101's no-clobber writer and hard-link filesystem requirement. Source stat
identity is checked across hashing/probing/decoding; the full hash must match the registered asset.
Ordinary detected changes abort. This is not adversarial snapshot isolation or power-loss durability.

The initial repair policy is **no automatic repair**: retain evidence and refuse editable boundaries
for review/unsupported maps. Repaired maps need a future explicit, versioned transformation and new
verification; no override is silently applied here.

## Verification

Unit tests exercise signed PTS, unknown final ends, duplicates/reversals, reported gaps/overlaps,
exact range membership and proxy mapping across unequal clocks. Integration generates synthetic
MPEG-4/MOV schedules: uniform frames, skipped-frame VFR, a two-second start offset and B-frame
reordering. Observed timestamps and final end are compared to the known schedule, not reported FPS.
Negative PTS is covered at the parser/domain layers because muxers may normalize negative starts.
