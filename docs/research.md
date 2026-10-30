# Research basis and dependency candidates

Reviewed 2026-10-26. These are candidates and constraints, not implemented Takebraid integrations
or endorsements of measured accuracy. Recheck the exact code/checkpoint/data revision before adoption.

| Component | Proposed role | Conditions / caveat |
|---|---|---|
| [Qwen3-VL](https://github.com/QwenLM/Qwen3-VL) | Structured action/state interpretation from video windows | [8B-Instruct card](https://huggingface.co/Qwen/Qwen3-VL-8B-Instruct) lists Apache-2.0; timestamps need verification |
| [OpenCLIP](https://github.com/mlfoundations/open_clip) | Relevance and visual grouping | Code MIT; each chosen checkpoint needs its own review; still-image similarity is not action understanding |
| [DINOv2](https://github.com/facebookresearch/dinov2) | Optional visual duplicate/alternative features | General DINOv2 is Apache-2.0; specialized models in the repository have separate terms |
| [OpenCV](https://docs.opencv.org/4.x/dc/d6b/group__video__track.html) | Flow and tracking | Apache-2.0 code; editorial defect policy is our implementation |
| [OR-Tools](https://github.com/google/or-tools) | Later constrained assembly | Apache-2.0; compare against simpler chronological selection first |
| [OpenTimelineIO](https://github.com/AcademySoftwareFoundation/OpenTimelineIO) | Editable timeline interchange | Apache-2.0; external-format adapters are separate and need target-editor testing |
| [FFmpeg](https://www.ffmpeg.org/legal.html) | Decode/render and probing | License depends on build; preserve source map and sample accuracy independently |
| [Moment-DETR / QVHighlights](https://github.com/jayleicn/moment_detr) | Research retrieval/highlight baseline | Code MIT; annotations CC BY-NC-SA 4.0; do not assume a single license for code/data/weights |
| [DOVER](https://github.com/VQAssessment/DOVER) | Research quality comparison | [S-Lab noncommercial terms](https://github.com/VQAssessment/DOVER/blob/master/LICENSE); outside the default stack |
| [TVSum](https://github.com/yalesong/tvsum) | Research importance comparison | Read the dataset's source/attribution terms; edited web-video summaries differ from raw multi-take editing |

Implementation references:
[VideoHighlighter](https://github.com/Aseiel/VideoHighlighter) connects analysis to highlights;
its [pipeline document](https://github.com/Aseiel/VideoHighlighter/blob/main/docs/AUTO-PIPELINE.md)
describes limits in per-beat ordering/duration enforcement. Its AGPL code cannot simply become
Apache-2.0 project code. [Montage AI](https://github.com/mfahsold/montage-ai) illustrates montage
assembly and media export. These projects have not been run against Takebraid's target dataset.

The integration contribution is an exact-time, evidence-preserving, reversible workflow with
explicit editing constraints and an evaluation set of unedited source projects. Better model
benchmarks alone do not establish better first cuts.

## TB-301 learned-encoder shortlist — reviewed 2026-10-30

Research only: no weights were downloaded, exported, executed, approved for redistribution or
selected as the application's default. The optional adapter still accepts only static float32
RGB NCHW inputs, `stretch-area` resizing, declared channel normalization, a single-file ONNX graph
up to 512 MiB, and one float32 `[1, dimensions]` output (1..4096). See `local-embeddings.md`.

| Candidate | Evidence and proposed role | Compatibility work remaining |
|---|---|---|
| DINOv2 ViT-S/14, without registers | Preferred first retrieval experiment, not a measured winner. The [official model card](https://github.com/facebookresearch/dinov2/blob/7764ea0f912e53c92e82eb78a2a1631e92725fc8/MODEL_CARD.md) lists Apache-2.0, 384-dimensional features and nearest-neighbor image retrieval. | The [reference evaluation transform](https://github.com/facebookresearch/dinov2/blob/7764ea0f912e53c92e82eb78a2a1631e92725fc8/dinov2/data/transforms.py) defaults to bicubic short-edge resize 256, center crop 224, then ImageNet normalization. This differs from our stretch-area contract. Export a pinned backbone with one class-token output and verify numerical parity; a compatible ONNX artifact has not been qualified. |
| `timm/resnet18.a1_in1k` | Smaller feature-backbone comparison candidate; no local latency claim. Its [publisher card](https://huggingface.co/timm/resnet18.a1_in1k/blob/491b427b45c94c7fb0e78b5474cc919aff584bbf/README.md) lists Apache-2.0 and removes the classifier with `num_classes=0` for embeddings. | Its [pinned config](https://huggingface.co/timm/resnet18.a1_in1k/blob/491b427b45c94c7fb0e78b5474cc919aff584bbf/config.json) declares 512 features, bicubic center-crop preprocessing, 224 training input and 288 test input. The repository offers safetensors/PyTorch weights, not a qualified ONNX export. Freeze one evaluation configuration and export pooled features, not classification logits. |

These are image-feature candidates, not text-brief relevance models, VLMs or action-boundary
detectors. Their publisher benchmarks do not establish duplicate-take accuracy for our footage.
General DINOv2 terms do not cover every specialized model in that repository. Check the exact
chosen weights and export dependencies separately before acquisition; do not infer data rights
or redistribution permission from a code license alone.

Next verifiable slice:

1. Pin the chosen checkpoint source/revision/hash and its terms; keep export dependencies in an
   isolated development environment. Do not add a default downloader or a core model dependency.
2. Define a versioned resize/crop contract with independent pixel/numeric reference tests before
   changing the adapter. Stretching a frame before a graph cannot recover a reference crop.
   Record interpolation, antialiasing, rounding, normalization, tool versions and output choice;
   change the inference recipe/cache identity when preprocessing semantics change.
3. Export one static, single-file graph, record its checksum and conversion recipe, and compare
   its output with the pinned reference on square, portrait and landscape inputs. Measure CPU
   latency, peak memory and graph size; do not infer them from parameter counts.
4. Freeze shoot-separated duplicate/nonduplicate/ambiguous labels and calibration/test splits.
   Compare the learned encoder with the spatial baseline under equal sample budgets; publish
   retrieval precision/recall, unknown coverage and failure cases without tuning on test labels.

The shortlist is complete; checkpoint selection, export/parity, preprocessing support and held-out
semantic evaluation are still pending. TB-301 and the human M2/M3 gates remain open.
