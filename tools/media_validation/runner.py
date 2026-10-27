"""Execute the committed independent media oracle and keep reproducible evidence."""

import json
import platform
import re
import subprocess
import time
import uuid
from datetime import UTC, datetime
from fractions import Fraction
from pathlib import Path

import takebraid
from takebraid.adapters.artifacts import write_new_json
from takebraid.adapters.identity import file_digest
from takebraid.adapters.records import load_frame_map
from takebraid.application.ingest import ingest
from takebraid.application.preview import create_plan, render_plan
from takebraid.application.scan import scan_asset
from tools.media_validation.fixtures import (
    COUNT,
    HEIGHT,
    WIDTH,
    command_run,
    decode_audio,
    decode_gray,
    generate_case,
    raw_probe,
)

MANIFEST = Path(__file__).with_name("cases.json")


def load_cases() -> dict:
    document = json.loads(MANIFEST.read_text(encoding="utf-8"))
    ids = set()
    if document["schema_version"] != "0.1":
        raise ValueError("Unsupported fixture manifest")
    for case in document["cases"]:
        if not re.fullmatch(r"[a-z0-9-]+", case["id"]) or case["id"] in ids:
            raise ValueError("Invalid/duplicate fixture identity")
        ids.add(case["id"])
        source = case["source"]
        if source["format"] not in {"mkv", "mov"} or source["codec"] not in {"ffv1", "mpeg4"}:
            raise ValueError("Unsupported synthetic codec/container")
        if (
            not 1 <= Fraction(source["fps"]) <= 120
            or source["rotation"] not in (0, 90)
            or source["sar"] not in ("1/1", "2/1")
            or not 0 <= source["audio_frames"] <= COUNT
            or source["b_frames"] not in (0, 2)
        ):
            raise ValueError("Invalid fixture generation settings")
        if source["frame_ids"] != sorted(set(source["frame_ids"])) or not all(
            type(index) is int and 0 <= index < COUNT for index in source["frame_ids"]
        ):
            raise ValueError("Source frame IDs must be ordered and unique")
        if len(case["expected"]["source_pts"]) != len(source["frame_ids"]):
            raise ValueError("Source PTS oracle does not match source frame count")
    return document


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def run_case(folder: Path, case: dict, tolerances: dict) -> dict:
    folder.mkdir(parents=True, exist_ok=False)
    write_new_json(
        folder / "expected.json", {"schema_version": "0.1", "case": case, "tolerances": tolerances}
    )
    started = time.monotonic()
    commands = []
    result = {"id": case["id"], "status": "failed", "expected": case["expected"]}
    try:
        source = generate_case(folder, case, commands)
        source_digest = file_digest(source)
        asset = ingest(source, folder / "project")
        map_path, status = scan_asset(asset, 0)
        require(status == "ready", f"Generated source map is {status}")
        frame_map = load_frame_map(map_path)
        points = [frame_map.time_base.seconds(frame.pts) for frame in frame_map.frames]
        end = frame_map.time_base.seconds(frame_map.presentation_end_pts)
        expected = case["expected"]
        require(
            points == [Fraction(point) for point in expected["source_pts"]],
            "Source PTS oracle mismatch",
        )
        require(end == Fraction(expected["source_end"]), "Source final-end oracle mismatch")
        raw_metadata = raw_probe(source, commands)
        video = next(
            stream for stream in raw_metadata["streams"] if stream["codec_type"] == "video"
        )
        sar = Fraction(video.get("sample_aspect_ratio", "1:1").replace(":", "/"))
        require(sar == Fraction(case["source"]["sar"]), "Generator did not preserve requested SAR")
        rotations = [
            item.get("rotation")
            for item in video.get("side_data_list", [])
            if item.get("side_data_type") == "Display Matrix"
        ]
        require(
            (rotations[0] if rotations else 0) == case["source"]["rotation"],
            "Source rotation oracle mismatch",
        )
        require(
            not case["source"]["b_frames"] or video.get("has_b_frames", 0) > 0,
            "Generator did not create a B-frame stream",
        )
        raw = decode_gray(source, commands)
        require(len(raw) == len(points) * WIDTH * HEIGHT, "Decoded source frame count mismatch")
        source_errors = [
            abs(raw[index * WIDTH * HEIGHT] - (16 + identity * 16))
            for index, identity in enumerate(case["source"]["frame_ids"])
        ]
        require(
            max(source_errors) <= tolerances["gray_absolute"], "Source picture identity mismatch"
        )
        result["source"] = {
            "sha256": source_digest,
            "pts_seconds": [str(p) for p in points],
            "end_seconds": str(end),
            "codec": video["codec_name"],
            "sar": str(sar),
            "rotation": rotations[0] if rotations else 0,
        }
        try:
            plan = create_plan(
                asset,
                0,
                tuple(tuple(cut) for cut in case["cuts"]),
                Fraction(case["output_fps"]),
                case["audio_policy"],
                1 if case["audio_policy"] == "source" else None,
            )
        except ValueError as exc:
            if case.get("expected_rejection") and case["expected_rejection"] in str(exc):
                result.update(status="passed", expected_rejection_observed=str(exc))
                return result
            raise
        require(not case.get("expected_rejection"), "Expected a missing-audio rejection")
        output = render_plan(folder / "project", plan)
        verification = json.loads((output.parent / "verification.json").read_text())
        expected_frames = len(expected["frame_ids"])
        require(
            verification["video_frames"] == expected_frames, "Output frame-count oracle mismatch"
        )
        require(
            (verification["width"], verification["height"])
            == (expected["width"], expected["height"]),
            "Output display geometry mismatch",
        )
        require(
            verification["audio_samples"] == expected["audio_samples"],
            "Output sample-count oracle mismatch",
        )
        pixel_data = decode_gray(output, commands)
        stride = expected["width"] * expected["height"]
        require(len(pixel_data) == expected_frames * stride, "Decoded output frame count mismatch")
        errors = [
            abs(pixel_data[index * stride] - (16 + identity * 16))
            for index, identity in enumerate(expected["frame_ids"])
        ]
        require(
            max(errors) <= tolerances["gray_absolute"],
            "Output picture order/identity oracle mismatch",
        )
        # Check output clocks against the independent manifest, not the compiler's receipt.
        decoded = json.loads(
            command_run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-select_streams",
                    "v:0",
                    "-show_streams",
                    "-show_frames",
                    "-of",
                    "json",
                    str(output),
                ],
                commands,
            )
        )
        clock = Fraction(decoded["streams"][0]["time_base"])
        fps = Fraction(case["output_fps"])
        frames = decoded["frames"]
        require(
            [int(frame["pts"]) * clock for frame in frames]
            == [Fraction(i, 1) / fps for i in range(expected_frames)],
            "Output PTS oracle mismatch",
        )
        last = frames[-1]
        require(
            (int(last["pts"]) + int(last.get("duration", last.get("pkt_duration", 0)))) * clock
            == Fraction(expected_frames, 1) / fps,
            "Output final-end oracle mismatch",
        )
        peaks = []
        if case["audio_policy"] == "source":
            samples = decode_audio(output, commands)
            require(len(samples) == expected["audio_samples"], "Decoded PCM length mismatch")
            peaks = [i for i, value in enumerate(samples) if abs(value) > 5000]
            require(peaks == expected["audio_peaks"], "PCM impulse position oracle mismatch")
        require(file_digest(source) == source_digest, "Source changed during validation")
        result.update(
            status="passed",
            output={
                "video_frames": expected_frames,
                "audio_samples": verification["audio_samples"],
                "width": verification["width"],
                "height": verification["height"],
                "audio_peaks": peaks,
                "max_gray_error": max(errors),
                "duration_seconds": verification["duration_seconds"],
            },
        )
    except Exception as exc:
        result.update(error_type=type(exc).__name__, error=str(exc))
    finally:
        result["elapsed_seconds"] = round(time.monotonic() - started, 3)
        # Source media is synthetic; keep argument lists for reproducibility, not execution.
        write_new_json(
            folder / "generator-commands.json", {"schema_version": "0.1", "commands": commands}
        )
        write_new_json(folder / "result.json", {"schema_version": "0.1", **result})
    return result


def run_matrix(output: Path, selected: list[str] | None = None) -> Path:
    repo = Path(__file__).resolve().parents[2]
    if Path(takebraid.__file__).resolve() != repo / "src/takebraid/__init__.py":
        raise RuntimeError("Validate this checkout with an editable install or PYTHONPATH=src")
    manifest = load_cases()
    available = {case["id"] for case in manifest["cases"]}
    if selected and (len(set(selected)) != len(selected) or not set(selected) <= available):
        raise ValueError("Requested duplicate or unknown fixture case")
    folder = output.expanduser().resolve() / f"run-{uuid.uuid4().hex}"
    folder.mkdir(parents=True, exist_ok=False)
    cases = [case for case in manifest["cases"] if not selected or case["id"] in selected]
    report = {
        "schema_version": "0.1",
        "started_at": datetime.now(UTC).isoformat(),
        "manifest_sha256": file_digest(MANIFEST),
        "recipe": manifest["recipe"],
        "full_manifest": len(cases) == len(available),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "python": platform.python_version(),
        "tools": {},
        "cases": [],
    }
    for name in ("ffmpeg", "ffprobe"):
        report["tools"][name] = subprocess.check_output([name, "-version"], text=True, timeout=10)
    report["commit"] = subprocess.check_output(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], text=True, timeout=10
    ).strip()
    report["worktree_dirty"] = bool(
        subprocess.check_output(
            ["git", "-C", str(repo), "status", "--porcelain"], text=True, timeout=10
        ).strip()
    )
    for case in cases:
        result = run_case(folder / case["id"], case, manifest["tolerances"])
        report["cases"].append(result)
        print(f"{case['id']}: {result['status']}", flush=True)
    report["passed"] = sum(case["status"] == "passed" for case in report["cases"])
    report["failed"] = len(cases) - report["passed"]
    report["worktree_dirty_at_end"] = bool(
        subprocess.check_output(
            ["git", "-C", str(repo), "status", "--porcelain"], text=True, timeout=10
        ).strip()
    )
    report["matrix_gate_passed"] = (
        report["full_manifest"]
        and not report["failed"]
        and not report["worktree_dirty"]
        and not report["worktree_dirty_at_end"]
    )
    path = folder / "report.json"
    write_new_json(path, report)
    return path
