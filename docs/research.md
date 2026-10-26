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
