"""Prepare licensed camera samples, retain honest review provenance and score a frozen pilot."""

import argparse
import json
import os
import subprocess
import tempfile
import urllib.request
import zipfile
from pathlib import Path

from takebraid.adapters.artifacts import write_new_json
from takebraid.adapters.identity import file_digest
from takebraid.adapters.records import _fraction
from takebraid.application.evaluation import evaluate_manifest
from takebraid.application.ingest import ingest
from takebraid.application.interpretation import interpret_observation
from takebraid.application.quality import observe_quality

CONFIG = Path(__file__).resolve().parents[1] / "examples/labeled-pilot"


def configuration():
    return json.loads((CONFIG / "sources.json").read_text()), json.loads(
        (CONFIG / "labels.json").read_text()
    )


def fetch(directory: Path):
    directory.mkdir(parents=True, exist_ok=True)
    for source in configuration()[0]["sources"]:
        target = directory / source["filename"]
        if target.exists():
            if file_digest(target) != source["sha256"]:
                raise ValueError("Existing source checksum mismatch")
            continue
        request = urllib.request.Request(
            source["url"],
            headers={
                "User-Agent": "Takebraid-labeled-pilot/1 (https://github.com/swimmingkiim/takebraid)"
            },
        )
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=directory, delete=False) as output:
                temporary = Path(output.name)
                with urllib.request.urlopen(request, timeout=45) as response:
                    size = 0
                    while block := response.read(1024 * 1024):
                        size += len(block)
                        if size > 20 * 1024 * 1024:
                            raise ValueError("Source exceeds 20 MiB download limit")
                        output.write(block)
            if file_digest(temporary) != source["sha256"]:
                raise ValueError("Downloaded source does not match pinned content")
            os.link(temporary, target)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)


def media(command, commands):
    commands.append(command)
    subprocess.run(command, check=True, capture_output=True, timeout=60)


def prepare(source_dir: Path, output: Path):
    sources, labels = configuration()
    output = output.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=False)
    commands = []
    cases = []
    for source in sources["sources"]:
        original = (source_dir / source["filename"]).expanduser().resolve(strict=True)
        if file_digest(original) != source["sha256"]:
            raise ValueError("Pinned source checksum mismatch")
        base = output / "cases" / f"{source['id']}-original" / "clip.mkv"
        base.parent.mkdir(parents=True)
        media(
            [
                "ffmpeg",
                "-v",
                "error",
                "-nostdin",
                "-n",
                "-ss",
                source["start_seconds"],
                "-i",
                str(original),
                "-map",
                "0:v:0",
                "-an",
                "-vf",
                "fps=25,scale=w='trunc(iw*min(1,320/max(iw,ih))/2)*2':h='trunc(ih*min(1,320/max(iw,ih))/2)*2',format=gray",
                "-frames:v",
                "50",
                "-c:v",
                "ffv1",
                str(base),
            ],
            commands,
        )
        for variant in ("original", "blur", "dark"):
            target = output / "cases" / f"{source['id']}-{variant}" / "clip.mkv"
            if variant != "original":
                target.parent.mkdir(parents=True)
                effect = "gblur=sigma=6" if variant == "blur" else "lutyuv=y=val*0.04"
                media(
                    [
                        "ffmpeg",
                        "-v",
                        "error",
                        "-nostdin",
                        "-n",
                        "-i",
                        str(base),
                        "-an",
                        "-vf",
                        effect + ":enable='between(n,15,34)'",
                        "-fps_mode",
                        "passthrough",
                        "-c:v",
                        "ffv1",
                        str(target),
                    ],
                    commands,
                )
            review = output / "review" / f"{source['id']}-{variant}.jpg"
            review.parent.mkdir(exist_ok=True)
            media(
                [
                    "ffmpeg",
                    "-v",
                    "error",
                    "-nostdin",
                    "-n",
                    "-i",
                    str(target),
                    "-vf",
                    "scale=128:-1,tile=10x5",
                    "-frames:v",
                    "1",
                    str(review),
                ],
                commands,
            )
            cases.append(
                {
                    "id": f"{source['id']}-{variant}",
                    "source_id": source["id"],
                    "variant": variant,
                    "clip": target.relative_to(output).as_posix(),
                    "sha256": file_digest(target),
                }
            )
    write_new_json(output / "sources.json", sources)
    write_new_json(output / "labels.json", labels)
    write_new_json(
        output / "derivations.json",
        {
            "schema_version": "0.1",
            "recipe": "licensed-pilot/1",
            "cases": cases,
            "commands": commands,
        },
    )
    print(output / "review")


def _policy(output, metric, enter, exit_value, calibration):
    path = output / f"{metric}-policy.json"
    write_new_json(
        path,
        {
            "schema_version": "0.1",
            "name": f"pilot-{metric}",
            "calibration": calibration,
            "metric": metric,
            "enter": str(enter),
            "exit": str(exit_value),
            "minimum_seconds": "2/25",
            "pad_before_seconds": "0",
            "pad_after_seconds": "0",
        },
    )
    return path


def run(dataset: Path):
    dataset = dataset.expanduser().resolve(strict=True)
    labels = json.loads((dataset / "labels.json").read_text())
    sources = json.loads((dataset / "sources.json").read_text())["sources"]
    recipe = json.loads((dataset / "derivations.json").read_text())
    if [s["id"] for s in sources if s["split"] == "calibration"] != ["mma"]:
        raise ValueError("Pilot calibration is restricted to the mma source group")
    lock_path = dataset / "experiment-lock.json"
    if lock_path.exists():
        verify_locked(dataset)
    else:
        artifacts = {}
        for case in recipe["cases"]:
            if case["source_id"] != "mma":
                continue
            asset = ingest(dataset / case["clip"], dataset / "cases" / case["id"] / "project")
            observation, _ = observe_quality(asset, 0)
            artifacts[case["variant"]] = (asset, observation)
        base = json.loads(artifacts["original"][1].read_text())["observations"]
        blur = json.loads(artifacts["blur"][1].read_text())["observations"]
        dark = json.loads(artifacts["dark"][1].read_text())["observations"]
        normal_focus = min(_fraction(row["metrics"]["laplacian_variance"]) for row in base)
        defect_focus = max(_fraction(row["metrics"]["laplacian_variance"]) for row in blur[15:35])
        if defect_focus >= normal_focus:
            raise ValueError("Calibration blur/normal features are not separable")
        focus_enter = (normal_focus + defect_focus) / 2
        # Bounded rational thresholds keep the explicit public policy schema portable.
        focus_enter = focus_enter.limit_denominator(10**8)
        focus_exit = ((focus_enter + normal_focus) / 2).limit_denominator(10**8)
        normal_dark = max(_fraction(row["metrics"]["dark_fraction"]) for row in base)
        defect_dark = min(_fraction(row["metrics"]["dark_fraction"]) for row in dark[15:35])
        dark_enter = ((normal_dark + defect_dark) / 2).limit_denominator(10**8)
        dark_exit = ((normal_dark + dark_enter) / 2).limit_denominator(10**8)
        calibration = (
            "Only mma source group calibrated; controlled distortion positives; "
            "one assistant review of originals; not human validation"
        )
        policies = {
            "focus_failure": _policy(
                dataset, "laplacian_variance", focus_enter, focus_exit, calibration
            ),
            "exposure_failure": _policy(
                dataset, "dark_fraction", dark_enter, dark_exit, calibration
            ),
        }
        write_new_json(
            lock_path,
            {
                "schema_version": "0.1",
                "labels_sha256": file_digest(dataset / "labels.json"),
                "sources_sha256": file_digest(dataset / "sources.json"),
                "derivations_sha256": file_digest(dataset / "derivations.json"),
                "calibration_source_ids": ["mma"],
                "policy_registry": {key: file_digest(p) for key, p in policies.items()},
                "thresholds": {
                    "focus_enter": str(focus_enter),
                    "focus_exit": str(focus_exit),
                    "dark_enter": str(dark_enter),
                    "dark_exit": str(dark_exit),
                },
            },
        )
        entries = []
        for case in recipe["cases"]:
            source = next(s for s in sources if s["id"] == case["source_id"])
            if case["source_id"] == "mma":
                asset, observation = artifacts[case["variant"]]
            else:
                asset = ingest(dataset / case["clip"], dataset / "cases" / case["id"] / "project")
                observation, _ = observe_quality(asset, 0)
            defects = (
                ("focus_failure", "exposure_failure")
                if case["variant"] == "original"
                else (labels["controlled_variants"][case["variant"]]["defect"],)
            )
            for defect in defects:
                interpretation, _ = interpret_observation(asset, observation, policies[defect])
                baseline = labels["originals"][source["id"]][defect]
                controlled = case["variant"] != "original"
                intervals = (
                    [(0, 15, baseline), (15, 35, "defect"), (35, 50, baseline)]
                    if controlled
                    else [(0, 50, baseline)]
                )
                annotator = "controlled-transform-oracle" if controlled else labels["reviewer"]
                entries.append(
                    {
                        "id": f"{case['id']}-{defect}",
                        "kind": "synthetic" if controlled else "camera",
                        "label_method": "constructed" if controlled else "assistant_review",
                        "split": source["split"],
                        "project_id": source["id"],
                        "shoot_id": source["id"],
                        "scene": case["variant"],
                        "defect": defect,
                        "asset": asset.relative_to(dataset).as_posix(),
                        "observation": observation.relative_to(dataset).as_posix(),
                        "interpretation": interpretation.relative_to(dataset).as_posix(),
                        "annotators": [annotator],
                        "annotation_protocol": labels["controlled_variants"][case["variant"]][
                            "rationale"
                        ]
                        if controlled
                        else labels["review_protocol"]
                        + " "
                        + labels["originals"][source["id"]]["rationale"],
                        "rights": {
                            "source": source["page"],
                            "license": source["license"],
                            "permission_evidence": (
                                f"Published CC0 by {source['author']}; "
                                f"source SHA-256 {source['sha256']}"
                            ),
                            "evaluation_permitted": True,
                        },
                        "labels": [
                            {"first_frame": a, "end_frame": b, "votes": {annotator: value}}
                            for a, b, value in intervals
                        ],
                    }
                )
        lock = json.loads(lock_path.read_text())
        write_new_json(
            dataset / "manifest.json",
            {
                "schema_version": "0.1",
                "dataset_id": "cc0-camera-derived-pilot",
                "label_version": labels["label_version"],
                "policy_registry": lock["policy_registry"],
                "entries": entries,
            },
        )
        write_new_json(
            dataset / "manifest-lock.json",
            {
                "schema_version": "0.1",
                "manifest_sha256": file_digest(dataset / "manifest.json"),
                "experiment_lock_sha256": file_digest(lock_path),
            },
        )
    verify_locked(dataset)
    for split in ("calibration", "test"):
        report = evaluate_manifest(dataset / "manifest.json", dataset / "evaluation", split=split)
        print(split, report)


def verify_locked(dataset: Path):
    lock = json.loads((dataset / "experiment-lock.json").read_text())
    for name in ("labels", "sources", "derivations"):
        if file_digest(dataset / f"{name}.json") != lock[f"{name}_sha256"]:
            raise ValueError(f"{name} changed after policy lock")
    registry = {"focus_failure": "laplacian_variance", "exposure_failure": "dark_fraction"}
    for defect, metric in registry.items():
        if file_digest(dataset / f"{metric}-policy.json") != lock["policy_registry"][defect]:
            raise ValueError("Policy changed after calibration lock")
    manifest_lock = json.loads((dataset / "manifest-lock.json").read_text())
    if (
        file_digest(dataset / "manifest.json") != manifest_lock["manifest_sha256"]
        or file_digest(dataset / "experiment-lock.json") != manifest_lock["experiment_lock_sha256"]
    ):
        raise ValueError("Evaluation inputs changed after generation")
    for case in json.loads((dataset / "derivations.json").read_text())["cases"]:
        clip = (dataset / case["clip"]).resolve(strict=True)
        if not clip.is_relative_to(dataset.resolve()) or file_digest(clip) != case["sha256"]:
            raise ValueError("Derived sample changed")


def relink(dataset: Path):
    from takebraid.adapters.projects import relink_asset
    from takebraid.adapters.records import load_asset

    dataset = dataset.expanduser().resolve(strict=True)
    verify_locked(dataset)
    for case in json.loads((dataset / "derivations.json").read_text())["cases"]:
        project = dataset / "cases" / case["id"] / "project"
        asset = load_asset(next(project.glob("assets/*/asset.json")))
        relink_asset(project, asset["asset_id"], (dataset / case["clip"]).resolve(strict=True))
    print("Relinked sample sources; evaluate with the same tool build or regenerate observations.")


def pack(dataset: Path, output: Path):
    dataset = dataset.expanduser().resolve(strict=True)
    verify_locked(dataset)
    output = output.expanduser().resolve()
    if output.is_relative_to(dataset):
        raise ValueError("Write the archive outside the dataset directory")
    with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(dataset.rglob("*")):
            if path.is_file() and path.relative_to(dataset).as_posix() != "README.md":
                if path.is_symlink():
                    raise ValueError("Sample archives cannot contain symlinks")
                archive.write(path, "labeled-pilot/" + path.relative_to(dataset).as_posix())
        archive.writestr("labeled-pilot/README.md", (CONFIG / "README.md").read_text())
    print(output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    download = commands.add_parser("download")
    download.add_argument("--source-dir", type=Path, required=True)
    prep = commands.add_parser("prepare")
    prep.add_argument("--source-dir", type=Path, required=True)
    prep.add_argument("--output", type=Path, required=True)
    execute = commands.add_parser("run")
    execute.add_argument("--dataset", type=Path, required=True)
    relocate = commands.add_parser("relink")
    relocate.add_argument("--dataset", type=Path, required=True)
    archive = commands.add_parser("pack")
    archive.add_argument("--dataset", type=Path, required=True)
    archive.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "download":
        fetch(args.source_dir)
    elif args.command == "prepare":
        prepare(args.source_dir, args.output)
    elif args.command == "run":
        run(args.dataset)
    elif args.command == "relink":
        relink(args.dataset)
    else:
        pack(args.dataset, args.output)


if __name__ == "__main__":
    main()
