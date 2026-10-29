"""Export prediction-hidden local frame review packets and collect independently declared votes."""

import argparse
import copy
import hashlib
import json
import re
import subprocess
from pathlib import Path

from takebraid.adapters.artifacts import write_new_json
from takebraid.adapters.evaluation import load_manifest, local_path
from takebraid.adapters.identity import file_digest
from takebraid.adapters.records import read_json
from takebraid.application.analysis import prepare_analysis
from takebraid.domain.evaluation import TRUTHS
from takebraid.domain.quality import QualitySettings

RECIPE = "blind-frame-review/1"
MAX_FRAMES = 5000


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,80}", value):
        raise ValueError("Expected a short reviewer/label identifier")
    return value


def context_for(manifest_path, entry):
    observation = read_json(local_path(manifest_path, entry["observation"]))
    return prepare_analysis(
        local_path(manifest_path, entry["asset"]),
        observation["inputs"]["stream_index"],
        QualitySettings(size=512),
        timeout=300,
        recipe=RECIPE,
        semantic_settings={"max_edge": 512, "sampling": "every decoded frame"},
        max_samples=MAX_FRAMES,
    )


def export_packet(manifest_path: Path, output: Path):
    manifest_path = manifest_path.expanduser().resolve(strict=True)
    manifest_hash = file_digest(manifest_path)
    manifest = load_manifest(manifest_path)
    entries = [e for e in manifest["entries"] if e["kind"] == "camera"]
    if not entries:
        raise ValueError("Review requires camera entries; constructed labels are not human tasks")
    # Validate budgets and source clocks before creating the fresh destination.
    contexts = {}
    for entry in entries:
        key = (entry["asset"], entry["observation"])
        if key not in contexts:
            contexts[key] = context_for(manifest_path, entry)
    if sum(len(c.frame_map.frames) for c in contexts.values()) > MAX_FRAMES:
        raise ValueError("Review packet exceeds the 5000 decoded-frame budget")
    for context in contexts.values():
        if context.reasons:
            raise ValueError("Unsupported review input: " + ", ".join(context.reasons))
        context.frame_map.boundaries()
    output = output.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=False)
    public = output / "review"
    public.mkdir()
    media, tasks, bindings = {}, [], []
    for entry in entries:
        context = contexts[(entry["asset"], entry["observation"])]
        source_id = hashlib.sha256(
            f"{context.frame_map.asset_id}:{context.frame_map.stream_index}".encode()
        ).hexdigest()[:24]
        task_id = hashlib.sha256(f"{source_id}:{entry['defect']}".encode()).hexdigest()[:24]
        if source_id not in media:
            folder = public / "frames" / source_id
            folder.mkdir(parents=True)
            count = len(context.frame_map.frames)
            command = [
                "ffmpeg",
                "-v",
                "error",
                "-nostdin",
                "-n",
                "-noautorotate",
                "-i",
                str(context.source),
                "-map",
                f"0:{context.frame_map.stream_index}",
                "-vf",
                "scale=w='min(512,iw)':h='min(512,ih)':force_original_aspect_ratio=decrease",
                "-fps_mode",
                "passthrough",
                "-frames:v",
                str(count + 1),
                "-start_number",
                "0",
                str(folder / "%06d.png"),
            ]
            subprocess.run(command, check=True, capture_output=True, timeout=300)
            images = sorted(folder.glob("*.png"))
            if len(images) != count:
                raise ValueError("Review image count differs from decoded source map")
            context.assert_stable()
            media[source_id] = {
                "source_sha256": context.inputs["source_sha256"],
                "stream_index": context.frame_map.stream_index,
                "frame_map_sha256": context.map_digest,
                "time_base": context.inputs["time_base"],
                "boundaries_pts": list(context.frame_map.boundaries()),
                "images": [
                    {"path": image.relative_to(public).as_posix(), "sha256": file_digest(image)}
                    for image in images
                ],
                "tools": context.inputs["tools"],
            }
        tasks.append({"id": task_id, "media_id": source_id, "defect": entry["defect"]})
        bindings.append({"task_id": task_id, "entry_id": entry["id"]})
    packet = {"schema_version": "0.1", "recipe": RECIPE, "media": media, "tasks": tasks}
    write_new_json(public / "packet.json", packet)
    packet_hash = file_digest(public / "packet.json")
    template = Path(__file__).with_name("blind_review.html").read_text(encoding="utf-8")
    # Embedded JSON needs no fetch/server and cannot escape its script element.
    encoded = json.dumps(packet, ensure_ascii=True).replace("<", "\\u003c")
    html = template.replace("__PACKET_JSON__", encoded).replace("__PACKET_SHA256__", packet_hash)
    (public / "index.html").write_text(html, encoding="utf-8")
    for context in contexts.values():
        context.assert_stable()
    if file_digest(manifest_path) != manifest_hash:
        raise ValueError("Manifest changed during packet export")
    write_new_json(
        output / "binding.json",
        {
            "schema_version": "0.1",
            "recipe": RECIPE,
            "manifest": str(manifest_path),
            "manifest_sha256": manifest_hash,
            "packet_sha256": packet_hash,
            "tasks": bindings,
        },
    )
    (public / "README.txt").write_text(
        "Open index.html locally. No server or network is needed. Share only this review folder, "
        "subject to source rights. Do not share the parent binding or evaluation files.\n"
        "Review every frame independently before seeing predictions or other labels. "
        "normal means no visible target defect at this review resolution; "
        "unknown preserves doubt.\n"
        "Exported JSON is an attestation, not proof of human identity or independent review. "
        "Do not reuse previously unblinded pilot reviewers for a blind validation claim.\n"
        "Frame indices are decoded presentation indices, never average-FPS conversions. "
        "Downscaling to at most 512 pixels limits optical judgments.\n"
        + "\n".join(sorted({json.dumps(e["rights"], ensure_ascii=False) for e in entries}))
        + "\n",
        encoding="utf-8",
    )
    return public / "index.html"


def review_votes(review, packet, packet_hash):
    reviewer = identifier(review["reviewer"])
    if (
        review.get("packet_sha256") != packet_hash
        or review.get("reviewer_kind") != "human"
        or review.get("independent_before_predictions") is not True
    ):
        raise ValueError("Review needs matching packet and independent human attestation")
    rows = review["tasks"]
    expected = {t["id"] for t in packet["tasks"]}
    if (
        not isinstance(rows, list)
        or len(rows) != len(expected)
        or {r["id"] for r in rows} != expected
    ):
        raise ValueError("Review must cover every task exactly once")
    result = {}
    for row in rows:
        task = next(t for t in packet["tasks"] if t["id"] == row["id"])
        count = len(packet["media"][task["media_id"]]["images"])
        intervals = row["intervals"]
        if not isinstance(intervals, list) or not 1 <= len(intervals) <= count:
            raise ValueError("Review requires bounded full-coverage intervals")
        cursor, votes = 0, []
        for interval in intervals:
            first, end, truth = (interval[k] for k in ("first_frame", "end_frame", "truth"))
            if (
                type(first) is not int
                or type(end) is not int
                or first != cursor
                or not first < end <= count
                or truth not in TRUTHS
            ):
                raise ValueError("Review intervals must partition all frames with explicit truths")
            votes.extend([truth] * (end - first))
            cursor = end
        if cursor != count:
            raise ValueError("Review must cover final decoded frame")
        result[row["id"]] = votes
    return reviewer, result


def merge_votes(reviews):
    """Combine partitions without inventing consensus; disagreements remain separate votes."""
    raters = [r for r, _ in reviews]
    if len(set(raters)) != len(raters) or not 2 <= len(raters) <= 10:
        raise ValueError("Need 2..10 distinct independently declared human reviewers")
    result = {}
    for task in reviews[0][1]:
        columns = [votes[task] for _, votes in reviews]
        if len({len(column) for column in columns}) != 1:
            raise ValueError("Review frame counts differ")
        labels = []
        for i, values in enumerate(zip(*columns, strict=True)):
            votes = dict(zip(raters, values, strict=True))
            if labels and labels[-1]["votes"] == votes:
                labels[-1]["end_frame"] = i + 1
            else:
                labels.append({"first_frame": i, "end_frame": i + 1, "votes": votes})
        result[task] = labels
    return result


def collect(packet_dir: Path, review_paths: list[Path], output: Path, label_version: str):
    identifier(label_version)
    if not 2 <= len(review_paths) <= 10:
        raise ValueError("Need 2..10 distinct independently declared human reviewers")
    packet_dir = packet_dir.expanduser().resolve(strict=True)
    binding = read_json(packet_dir / "binding.json")
    public = packet_dir / "review"
    packet_path = public / "packet.json"
    packet = read_json(packet_path, limit=8 * 1024 * 1024)
    packet_hash = file_digest(packet_path)
    manifest_path = Path(binding["manifest"])
    if (
        binding["recipe"] != RECIPE
        or packet["recipe"] != RECIPE
        or packet_hash != binding["packet_sha256"]
        or file_digest(manifest_path) != binding["manifest_sha256"]
    ):
        raise ValueError("Packet or source manifest changed after export")
    for medium in packet["media"].values():
        for image in medium["images"]:
            path = (public / image["path"]).resolve(strict=True)
            if not path.is_relative_to(public) or file_digest(path) != image["sha256"]:
                raise ValueError("Review image changed after export")
    hashes, reviews = [], []
    for path in review_paths:
        digest = file_digest(path)
        review = read_json(path, limit=8 * 1024 * 1024)
        if file_digest(path) != digest:
            raise ValueError("Review changed during collection")
        hashes.append(digest)
        reviews.append(review_votes(review, packet, packet_hash))
    combined = merge_votes(reviews)
    manifest = copy.deepcopy(load_manifest(manifest_path))
    camera_ids = {e["id"] for e in manifest["entries"] if e["kind"] == "camera"}
    bound_tasks = binding["tasks"]
    if (
        len(bound_tasks) != len(camera_ids)
        or {t["entry_id"] for t in bound_tasks} != camera_ids
        or len({t["task_id"] for t in bound_tasks}) != len(bound_tasks)
        or {t["task_id"] for t in bound_tasks} != {t["id"] for t in packet["tasks"]}
    ):
        raise ValueError("Binding must cover each camera entry and review task exactly once")
    for binding_task in bound_tasks:
        task_id = binding_task["task_id"]
        entry = next(e for e in manifest["entries"] if e["id"] == binding_task["entry_id"])
        context = context_for(manifest_path, entry)
        task = next(t for t in packet["tasks"] if t["id"] == task_id)
        medium = packet["media"][task["media_id"]]
        if (
            task["defect"] != entry["defect"]
            or context.inputs["source_sha256"] != medium["source_sha256"]
            or context.map_digest != medium["frame_map_sha256"]
            or list(context.frame_map.boundaries()) != medium["boundaries_pts"]
        ):
            raise ValueError("Reviewed source clock/content changed")
        context.assert_stable()
        entry.update(
            {
                "label_method": "human",
                "annotators": [r for r, _ in reviews],
                "labels": combined[task_id],
                "annotation_protocol": "Independently declared human frame review; "
                "identity/independence "
                "are attestations, not verified. Packet SHA-256 "
                + packet_hash
                + "; review SHA-256 "
                + ",".join(hashes),
            }
        )
    # Absolute local references allow a new output location without rewriting the frozen pilot.
    for entry in manifest["entries"]:
        for name in ("asset", "observation", "interpretation", "decision"):
            if entry.get(name) is not None:
                entry[name] = str(local_path(manifest_path, entry[name]))
    manifest["label_version"] = label_version
    manifest["annotation_review"] = {
        "recipe": RECIPE,
        "packet_sha256": packet_hash,
        "review_sha256": hashes,
        "identity_and_independence": "self-attested; not verified by software",
    }
    if file_digest(manifest_path) != binding["manifest_sha256"]:
        raise ValueError("Manifest changed during collection")
    write_new_json(output.expanduser().resolve(), manifest)
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    export = commands.add_parser("export")
    export.add_argument("manifest", type=Path)
    export.add_argument("--output", type=Path, required=True)
    merge = commands.add_parser("collect")
    merge.add_argument("packet_dir", type=Path)
    merge.add_argument("--review", type=Path, action="append", required=True)
    merge.add_argument("--output", type=Path, required=True)
    merge.add_argument("--label-version", required=True)
    args = parser.parse_args()
    if args.command == "export":
        print(export_packet(args.manifest, args.output))
    else:
        print(collect(args.packet_dir, args.review, args.output, args.label_version))


if __name__ == "__main__":
    main()
