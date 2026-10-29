# Search saved image embeddings (TB-301c)

`takebraid embedding-search` compares checked saved embedding samples across source assets and
returns cosine-ranked frame candidates. It replays existing numerical evidence: no model file,
model manifest on disk, NumPy or ONNX Runtime is required. Original media, its project/receipt/frame
map artifacts and compatible FFmpeg/ffprobe builds are still required for source-clock validation.
The search does not run inference, download a checkpoint or execute model code.

```bash
takebraid embedding-search \
  --input /absolute/path/asset-a.json /absolute/path/embeddings-a.json \
  --input /absolute/path/asset-b.json /absolute/path/embeddings-b.json \
  --output workspace/embedding-search --min-cosine 0.9 --limit 20
```

The threshold is an explicit example, not a calibrated recommendation. It must be finite in [-1,1].
Cosine is a floating-point geometric score, not a probability of matching events or duplicate takes.
Every result retains both asset IDs, stream indices, decoded source-frame indices, signed PTS and
rational time bases. Sampling never reconstructs media positions from FPS or floating seconds.

## Identity and compatibility

The loader validates each preserved attempt's terminal receipt/checksum, source identity, decoded
map/tool provenance, settings, sampling partition, numerical coverage and unit-vector dimensions.
It reconstructs the recorded preprocessing context without importing a provider or opening weights.
A hand-edited vector, changed source or mismatched clock cannot silently become a search input.
A saved manifest hash records what was used for inference; replay does not re-verify an absent
checkpoint's current availability or its license. Model rights remain the operator's responsibility.

All inputs must share the exact encoder recipe, full model specification (including declared
filename, hash, revision/license metadata, input preprocessing and output shape), saved runtime
provenance, and media-tool builds. This conservative initial space identity intentionally rejects
some numerically compatible aliases; it does not guess that two models belong to the same space.
Different sampling strides/source clocks are supported. Different model, preprocessing, provider,
runtime or media builds are rejected with an incompatibility error. The report stores a canonical
embedding-space fingerprint plus every input observation's digest/provenance.

No model-output regeneration occurs during search. Archived inference artifacts can be replayed
without the original model/runtime, provided the source/project and media validation dependencies
remain available. Copying only an `embeddings.json` outside its project is insufficient: immutable
receipt and map/source checks are part of the contract. Preserve/relink projects as documented in
`projects.md` rather than stripping provenance to make an unchecked input pass.

## Scoring and unknown coverage

Only rows with valid finite unit vectors enter cosine scoring. Zero/nonfinite outputs already
recorded as unknown remain missing evidence; they are never replaced by zero vectors or assigned
a low similarity score. Unsupported whole inputs retain their source status/reasons and have no
sample rows. No matches, or zero evaluated pairs, does not establish that complete sources differ.
The report separately counts possible sampled pairs, evaluated pairs, skipped unknown pairs and
unknown samples per source. Unsampled frames have no claimed search coverage.

Cosine uses double-precision summation and norm division, clamped to [-1,1] for numerical rounding;
identical vectors return 1. Threshold inclusion is `cosine >= min_cosine`. Ranking is descending
score, then lexicographic asset identity and frame indices, independent of input order. The report
returns at most `--limit` candidates (default 20, maximum 1000), with total matches/truncation counts.
Floating similarities are not promised bitwise equivalent across Python/platform math libraries;
the current math environment is included in the search-stage key.

This stage returns individual sampled frame pairs. It does not infer continuous duplicate windows,
action completeness, editorial relevance, whole-take alternatives or chronological dependencies.
Matches do not create decisions, exclusions, cuts or renders. Both semantic-accuracy validation
and automatic-exclusion validation flags remain false, even for a high cosine.

## Budgets and replay

Search accepts 2..10 distinct source content identities. Repeated references to the same asset are
rejected. Before scoring, limits are 2000 total sampled rows, 2,000,000 stored vector coordinates,
50,000 possible cross-source sampled pairs and 8,000,000 pair-coordinate products. Limits count
unknown rows/pairs conservatively. Increase extraction `--every` or reduce inputs to stay in bounds;
the search never silently changes sampling. Each record is also subject to its bounded JSON loader.

Recipe `saved-embedding-cosine-search/1` keys space/input identity, threshold, result limit and math
environment. Cache reuse checks terminal receipts and recomputes candidates from validated saved
vectors before reuse. `--force` preserves a new attempt; prior output and source files are untouched.
Cancellation returns 130, errors 1, and a valid report returns 0 even when there are no comparable
vectors. The stage performs bounded local numeric work, not GPU inference or a vector database.

## Evidence and limitations

Unit tests cover exact/orthogonal/opposite directions, floating normalization, threshold boundaries,
unknown coverage, deterministic ties/truncation, dimensions and sample/pair/coordinate budgets.
Actual generated ONNX channel-mean graphs encode red/green/blue/black source frames. Tests then
archive the model folder, forbid optional imports and search the saved records: matching colors
are recovered across reordered frames; black zero outputs remain unknown. Receipt/source edits
and mixed preprocessing are rejected. Negative-start and VFR search points match the independent
media oracle. These original constructed signals are numerical tests, not human duplicate labels.

The three existing CC0 pilot excerpts have a separate local search under
`workspace/embedding-search-pilot/`. Their synthetic RGB channel-mean model gives almost equal
directions for grayscale inputs, so a high score on them is intentionally uninformative about
semantics. The validation summary records actual counts/hashes. It is not an embedding-quality
benchmark. Learned checkpoint qualification, held-out duplicate-take/event labels and M2/M3 human
validation remain open.
