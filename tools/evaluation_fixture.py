"""Generate independent synthetic controls and run the real evaluation pipeline."""

import argparse
import json
import subprocess
from pathlib import Path

from takebraid.adapters.artifacts import write_new_json
from takebraid.adapters.identity import file_digest
from takebraid.application.evaluation import evaluate_manifest
from takebraid.application.ingest import ingest
from takebraid.application.interpretation import interpret_observation
from takebraid.application.motion import observe_motion
from takebraid.application.quality import observe_quality
from takebraid.domain.motion import MotionSettings
from tools.motion_fixtures import sequence


def generate(output: Path) -> Path:
    output = output.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=False)
    policies = {}
    for defect, metric, enter, exit_value in (
        ("focus_failure", "laplacian_variance", "1/10", "1/5"),
        ("exposure_failure", "dark_fraction", "9/10", "4/5"),
        ("unwanted_camera_motion", "path_residual_squared", "1", "1/4"),
    ):
        path = output / f"{defect}-policy.json"
        write_new_json(
            path,
            {
                "schema_version": "0.1",
                "name": f"synthetic-{defect}",
                "calibration": "Constructed regression signals only; not camera calibrated",
                "metric": metric,
                "enter": enter,
                "exit": exit_value,
                "minimum_seconds": "2/25",
                "pad_before_seconds": "0",
                "pad_after_seconds": "0",
            },
        )
        policies[defect] = path
    sharp = bytes(255 if (x // 4 + y // 4) % 2 else 0 for y in range(48) for x in range(64))
    blur = bytes(
        sum(
            sharp[min(47, max(0, y + dy)) * 64 + min(63, max(0, x + dx))]
            for dy in range(-2, 3)
            for dx in range(-2, 3)
        )
        // 25
        for y in range(48)
        for x in range(64)
    )
    cases = [
        (
            "static-product-control",
            "focus_failure",
            64,
            48,
            [bytes([128]) * 64 * 48] * 5,
            ["normal"] * 5,
        ),
        (
            "intentional-night-control",
            "exposure_failure",
            64,
            48,
            [bytes([8]) * 64 * 48] * 5,
            ["normal"] * 5,
        ),
        (
            "constructed-blur",
            "focus_failure",
            64,
            48,
            [sharp, blur, blur, blur, sharp],
            ["normal", "defect", "defect", "defect", "normal"],
        ),
        (
            "intentional-pan-control",
            "unwanted_camera_motion",
            96,
            64,
            sequence("pan"),
            ["normal"] * 4,
        ),
    ]
    entries = []
    for name, defect, width, height, frames, truth in cases:
        folder = output / name
        folder.mkdir()
        raw = folder / "signal.gray"
        raw.write_bytes(b"".join(frames))
        source = folder / "source.mkv"
        subprocess.run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-nostdin",
                "-n",
                "-f",
                "rawvideo",
                "-pix_fmt",
                "gray",
                "-s",
                f"{width}x{height}",
                "-framerate",
                "25",
                "-i",
                str(raw),
                "-c:v",
                "ffv1",
                str(source),
            ],
            check=True,
            capture_output=True,
            timeout=30,
        )
        asset = ingest(source, folder / "project")
        observation, _ = (
            observe_motion(asset, 0, MotionSettings(background=(0, 0, width, height)))
            if defect == "unwanted_camera_motion"
            else observe_quality(asset, 0)
        )
        interpretation, _ = interpret_observation(asset, observation, policies[defect])

        def relative(path):
            return path.relative_to(output).as_posix()

        entries.append(
            {
                "id": name,
                "kind": "synthetic",
                "label_method": "constructed",
                "split": "test",
                "project_id": name,
                "shoot_id": name,
                "scene": name,
                "defect": defect,
                "asset": relative(asset),
                "observation": relative(observation),
                "interpretation": relative(interpretation),
                "annotators": ["oracle-a", "oracle-b"],
                "annotation_protocol": (
                    "Independent constructed labels in tools/evaluation_fixture.py; "
                    "IDs are two oracle votes, not human editors"
                ),
                "rights": {
                    "source": "Original Takebraid signal recipes",
                    "license": "Apache-2.0",
                    "permission_evidence": "Generated solely from project code",
                    "evaluation_permitted": True,
                },
                "labels": [
                    {
                        "first_frame": i,
                        "end_frame": i + 1,
                        "votes": {"oracle-a": value, "oracle-b": value},
                    }
                    for i, value in enumerate(truth)
                ],
            }
        )
    manifest = output / "manifest.json"
    write_new_json(
        manifest,
        {
            "schema_version": "0.1",
            "dataset_id": "synthetic-negative-controls",
            "label_version": "constructed-v1",
            "policy_registry": {key: file_digest(path) for key, path in policies.items()},
            "entries": entries,
        },
    )
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = generate(args.output)
    report = evaluate_manifest(manifest, args.output / "evaluation")
    raw = json.loads(report.read_text())
    assert raw["evidence_scope"] == "synthetic_only" and not raw["automatic_exclusion_validated"]
    rows = {row["id"]: row["score"] for row in raw["entries"]}
    assert rows["static-product-control"]["ratios"]["precision"] == {
        "numerator": 0,
        "denominator": 1,
    }
    assert rows["intentional-night-control"]["durations"]["false_positive_seconds"] == {
        "numerator": 1,
        "denominator": 5,
    }
    assert rows["constructed-blur"]["ratios"]["recall_all_labeled_defect"] == {
        "numerator": 1,
        "denominator": 1,
    }
    assert rows["intentional-pan-control"]["ratios"]["prediction_unknown_rate"] == {
        "numerator": 1,
        "denominator": 2,
    }
    print(report)


if __name__ == "__main__":
    main()
