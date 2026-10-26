# Data contracts

Status: draft v0.1. Only `TimeBase` and `SourceRange` exist in code. Remaining records below are
design targets and must gain parsers, versioned schemas and tests in their delivery milestones.

## Identity and time

`asset_id` is a stable project identity; paths are locators and can be relinked. Every source
reference names a stream. Keep exact integer PTS/time base values. Source ranges are nonempty,
half-open and can include negative PTS. Validate against the decoded frame map in M1.

Example wire representation (not a shipped parser):

```json
{
  "schema_version": "0.1",
  "asset_id": "asset-001",
  "stream_index": 0,
  "in_pts": 1080000,
  "out_pts": 1530000,
  "time_base": {"numerator": 1, "denominator": 90000}
}
```

This represents five seconds. Do not persist rounded display seconds as the authoritative range.
An exact PTS range is not proof of valid frame endpoints or available source media.

## Planned records

| Record | Required information | Invariant |
|---|---|---|
| Asset | ID, locator, fingerprint, stream metadata, rotation/color/audio | ID resolves to one verified source |
| Sample map | Source PTS, proxy/sample position, extraction config | Every sample maps back to source |
| Observation | ID, range, method/version, measurements, evidence | Measurement provenance is explicit |
| Interpretation | Range, event/quality label, evidence IDs, uncertainty | Inferences are distinguishable from measurements |
| Candidate | Event, trim variant, range, role, alternative group, score breakdown | References existing source/evidence |
| Brief | Budget, ordering mode, required events, trim limits, audio policy | Hard and soft requirements are separate |
| Override | Target ID, include/exclude/trim/order instruction, parent plan | Original evidence and plan are retained |
| Timeline | Source clips, output frame ranges/rate, audio mapping, reasons | Only valid referenced ranges can execute |
| Receipt | Timeline hash, tool versions, artifacts, validation results | Render can be traced to one saved plan |

Use finite numbers for scores; reject NaN/Infinity. A rank score is not a probability.
Use `keep`, `exclude`, `review`, `unknown` for quality policy results. Keep raw measurements
independently so a later policy can reconsider a decision.

## Versioning and migration

Each persisted document carries `schema_version`; unknown major versions fail with an actionable
error. Add explicit migrations when semantics change. Store model outputs as untrusted raw evidence
separately from validated domain records. Export adapters may lose metadata and must report that loss.
Define deterministic serialization and hashing in M1; do not make untested cross-version hash promises.
