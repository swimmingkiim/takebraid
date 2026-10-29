"""Small bootstrap CLI; editing commands arrive with their working implementations."""

import argparse
import json
import platform
import shutil
import subprocess
import sys
from fractions import Fraction
from pathlib import Path

from takebraid import __version__
from takebraid.adapters.projects import (
    init_project,
    load_project,
    register_asset,
    relink_asset,
    verify_project,
)
from takebraid.application.decisions import (
    create_decisions,
    decision_plan,
    load_decisions,
    update_decisions,
)
from takebraid.application.embedding_search import search_embeddings
from takebraid.application.embeddings import observe_embeddings
from takebraid.application.evaluation import evaluate_manifest
from takebraid.application.ingest import IngestError, ingest
from takebraid.application.interpretation import interpret_observation
from takebraid.application.motion import observe_motion
from takebraid.application.preview import create_plan, render_plan
from takebraid.application.quality import observe_quality
from takebraid.application.scan import ScanError, scan_asset
from takebraid.application.visual import compare_visual, observe_visual
from takebraid.domain.decisions import DecisionOverride
from takebraid.domain.motion import MotionSettings
from takebraid.domain.quality import QualitySettings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Turn raw footage into a considered first cut.")
    parser.add_argument("--version", action="version", version=f"takebraid {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)
    doctor = commands.add_parser("doctor", help="Report Python and media tool availability.")
    doctor.add_argument("--json", action="store_true", dest="as_json")
    register = commands.add_parser("ingest", help="Inspect a local video and save asset metadata.")
    register.add_argument("source", type=Path)
    register.add_argument("--project", type=Path, required=True, help="Project output directory.")
    scan = commands.add_parser("scan", help="Decode a registered video's frame timestamps.")
    scan.add_argument("asset", type=Path, help="Path to asset.json created by ingest.")
    scan.add_argument("--stream", type=int, required=True, help="Absolute video stream index.")
    scan.add_argument("--timeout", type=float, default=300, help="FFprobe timeout in seconds.")
    scan.add_argument("--max-frames", type=int, default=250000)
    scan.add_argument("--force", action="store_true", help="Recompute as a new preserved attempt.")
    search = commands.add_parser(
        "embedding-search", help="Search checked saved embeddings without a model runtime."
    )
    search.add_argument(
        "--input",
        nargs=2,
        action="append",
        type=Path,
        required=True,
        metavar=("ASSET", "EMBEDDINGS"),
    )
    search.add_argument("--output", type=Path, required=True)
    search.add_argument(
        "--min-cosine", type=float, required=True, help="Explicit similarity threshold -1..1."
    )
    search.add_argument("--limit", type=int, default=20)
    search.add_argument("--force", action="store_true")
    embed = commands.add_parser(
        "embed", help="Run an explicitly selected local ONNX image encoder."
    )
    embed.add_argument("asset", type=Path)
    embed.add_argument("--stream", type=int, required=True)
    embed.add_argument(
        "--model", type=Path, required=True, help="Local hash/revision/license manifest."
    )
    embed.add_argument("--every", type=int, default=25)
    embed.add_argument("--timeout", type=float, default=300)
    embed.add_argument("--inference-timeout", type=float, default=30)
    embed.add_argument("--force", action="store_true")
    visual = commands.add_parser(
        "visual", help="Observe spatial descriptors and compare visual candidates."
    )
    visual_commands = visual.add_subparsers(dest="visual_command", required=True)
    visual_observe = visual_commands.add_parser("observe")
    visual_observe.add_argument("asset", type=Path)
    visual_observe.add_argument("--stream", type=int, required=True)
    visual_observe.add_argument("--size", type=int, default=64)
    visual_observe.add_argument("--every", type=int, default=25)
    visual_observe.add_argument("--timeout", type=float, default=300)
    visual_observe.add_argument("--force", action="store_true")
    visual_compare = visual_commands.add_parser("compare")
    visual_compare.add_argument(
        "--input", nargs=2, action="append", type=Path, required=True, metavar=("ASSET", "VISUAL")
    )
    visual_compare.add_argument("--output", type=Path, required=True)
    visual_compare.add_argument(
        "--max-distance", required=True, help="Exact mean squared distance 0..1."
    )
    visual_compare.add_argument(
        "--min-variance", required=True, help="Positive spatial contrast floor <=1/4."
    )
    visual_compare.add_argument("--limit", type=int, default=20)
    visual_compare.add_argument("--force", action="store_true")
    quality = commands.add_parser(
        "quality", help="Measure focus/exposure without excluding footage."
    )
    quality.add_argument("asset", type=Path)
    quality.add_argument("--stream", type=int, required=True)
    quality.add_argument("--size", type=int, default=160, help="Maximum analysis edge, no upscale.")
    quality.add_argument(
        "--every", type=int, default=1, help="Decoded source-frame sampling stride."
    )
    quality.add_argument("--roi", help="X:Y:WIDTH:HEIGHT on the unrotated analysis pixel grid.")
    quality.add_argument("--timeout", type=float, default=300)
    quality.add_argument("--force", action="store_true")
    motion = commands.add_parser(
        "motion", help="Measure bounded background translation candidates."
    )
    motion.add_argument("asset", type=Path)
    motion.add_argument("--stream", type=int, required=True)
    motion.add_argument("--size", type=int, default=96)
    motion.add_argument("--every", type=int, default=1)
    motion.add_argument("--radius", type=int, default=4)
    motion.add_argument("--background", help="X:Y:WIDTH:HEIGHT on the analysis grid.")
    motion.add_argument("--timeout", type=float, default=300)
    motion.add_argument("--force", action="store_true")
    interpretation = commands.add_parser(
        "interpret", help="Apply an explicit temporal candidate policy."
    )
    interpretation.add_argument("observation", type=Path)
    interpretation.add_argument("--asset", type=Path, required=True)
    interpretation.add_argument("--policy", type=Path, required=True)
    interpretation.add_argument("--force", action="store_true")
    decisions = commands.add_parser("decisions", help="Save reversible editing decisions.")
    edits = decisions.add_subparsers(dest="decision_command", required=True)
    for name in ("create", "show", "set", "restore", "plan"):
        edit = edits.add_parser(name)
        edit.add_argument(
            "record", type=Path, help="Interpretation for create; decision otherwise."
        )
        edit.add_argument("--asset", type=Path, required=True)
        if name == "create":
            edit.add_argument("--observation", type=Path, required=True)
        elif name in {"set", "restore"}:
            edit.add_argument("--frames", required=True, help="FIRST:END decoded frame indices.")
            edit.add_argument("--reason", required=True)
            if name == "set":
                edit.add_argument(
                    "--state", choices=("keep", "exclude", "review", "unknown"), required=True
                )
        elif name == "plan":
            edit.add_argument("--fps", default="25")
            edit.add_argument("--audio", choices=("mute", "source"), required=True)
            edit.add_argument("--audio-stream", type=int)
    evaluation = commands.add_parser(
        "evaluate", help="Score frozen policies against rights-declared labels."
    )
    evaluation.add_argument("manifest", type=Path)
    evaluation.add_argument("--output", type=Path, required=True)
    evaluation.add_argument("--split", choices=("calibration", "test"), default="test")
    evaluation.add_argument("--force", action="store_true")
    plan = commands.add_parser("plan", help="Save manual cuts using decoded frame indices.")
    plan.add_argument("asset", type=Path)
    plan.add_argument("--stream", type=int, required=True)
    plan.add_argument(
        "--cut", action="append", required=True, help="FIRST:END frame indices, exclusive end."
    )
    plan.add_argument("--fps", default="25")
    plan.add_argument("--audio", choices=("mute", "source"), required=True)
    plan.add_argument("--audio-stream", type=int)
    render = commands.add_parser("render", help="Render and verify a saved manual preview.")
    render.add_argument("timeline", type=Path)
    render.add_argument("--project", type=Path, required=True)
    render.add_argument("--timeout", type=float, default=300)
    render.add_argument("--force", action="store_true")
    project = commands.add_parser("project", help="Manage a versioned local project registry.")
    project_commands = project.add_subparsers(dest="project_command", required=True)
    for command in ("init", "show", "verify", "add", "relink"):
        sub = project_commands.add_parser(command)
        sub.add_argument("directory", type=Path)
        if command == "add":
            sub.add_argument("asset", type=Path)
        elif command == "relink":
            sub.add_argument("asset_id")
            sub.add_argument("source", type=Path)
    args = parser.parse_args(argv)

    if args.command == "embedding-search":
        try:
            result = search_embeddings(
                args.input,
                args.output,
                min_cosine=args.min_cosine,
                limit=args.limit,
                force=args.force,
            )
            print(result)
            return 0
        except (
            OSError,
            ValueError,
            TypeError,
            KeyError,
            ZeroDivisionError,
            subprocess.SubprocessError,
        ) as exc:
            print(f"takebraid: {exc}", file=sys.stderr)
            return 1
        except KeyboardInterrupt:
            print("takebraid: embedding search cancelled", file=sys.stderr)
            return 130

    if args.command == "embed":
        try:
            result, status = observe_embeddings(
                args.asset,
                args.stream,
                args.model,
                every=args.every,
                timeout=args.timeout,
                inference_timeout=args.inference_timeout,
                force=args.force,
            )
            print(result)
            if status != "observed":
                print(
                    f"takebraid: embedding coverage is {status}; inspect reasons", file=sys.stderr
                )
                return 2
            return 0
        except (
            OSError,
            ValueError,
            TypeError,
            KeyError,
            ZeroDivisionError,
            subprocess.SubprocessError,
        ) as exc:
            print(f"takebraid: {exc}", file=sys.stderr)
            return 1
        except KeyboardInterrupt:
            print("takebraid: embedding operation cancelled", file=sys.stderr)
            return 130

    if args.command == "visual":
        try:
            if args.visual_command == "observe":
                result, status = observe_visual(
                    args.asset,
                    args.stream,
                    size=args.size,
                    every=args.every,
                    timeout=args.timeout,
                    force=args.force,
                )
                print(result)
                if status != "observed":
                    print(
                        "takebraid: visual observations unknown; inspect reasons", file=sys.stderr
                    )
                    return 2
            else:
                result = compare_visual(
                    args.input,
                    args.output,
                    max_distance=Fraction(args.max_distance),
                    min_variance=Fraction(args.min_variance),
                    limit=args.limit,
                    force=args.force,
                )
                print(result)
            return 0
        except (
            OSError,
            ValueError,
            TypeError,
            KeyError,
            ZeroDivisionError,
            subprocess.SubprocessError,
        ) as exc:
            print(f"takebraid: {exc}", file=sys.stderr)
            return 1
        except KeyboardInterrupt:
            print("takebraid: visual operation cancelled", file=sys.stderr)
            return 130

    if args.command == "evaluate":
        try:
            result = evaluate_manifest(
                args.manifest, args.output, split=args.split, force=args.force
            )
            print(result)
            return 0
        except (
            OSError,
            ValueError,
            TypeError,
            KeyError,
            ZeroDivisionError,
            subprocess.SubprocessError,
        ) as exc:
            print(f"takebraid: {exc}", file=sys.stderr)
            return 1
        except KeyboardInterrupt:
            print("takebraid: evaluation cancelled", file=sys.stderr)
            return 130

    if args.command == "decisions":
        try:
            if args.decision_command == "create":
                result = create_decisions(args.asset, args.observation, args.record)
            elif args.decision_command == "show":
                result, _, _ = load_decisions(args.asset, args.record)
                print(json.dumps(result, ensure_ascii=False, indent=2))
                return 0
            elif args.decision_command in {"set", "restore"}:
                parts = args.frames.split(":")
                if len(parts) != 2:
                    raise ValueError("--frames must be FIRST:END decoded frame indices")
                override = DecisionOverride(
                    args.decision_command,
                    args.state if args.decision_command == "set" else None,
                    int(parts[0]),
                    int(parts[1]),
                    args.reason,
                )
                result = update_decisions(args.asset, args.record, override)
            else:
                result = decision_plan(
                    args.asset, args.record, Fraction(args.fps), args.audio, args.audio_stream
                )
            print(result)
            return 0
        except (
            OSError,
            ValueError,
            TypeError,
            KeyError,
            ZeroDivisionError,
            subprocess.SubprocessError,
        ) as exc:
            print(f"takebraid: {exc}", file=sys.stderr)
            return 1
        except KeyboardInterrupt:
            print("takebraid: decision operation cancelled", file=sys.stderr)
            return 130

    if args.command == "interpret":
        try:
            output, status = interpret_observation(
                args.asset,
                args.observation,
                args.policy,
                force=args.force,
            )
            print(output)
            if status != "interpreted":
                print(
                    f"takebraid: interpretation coverage is {status}; inspect unknown cells",
                    file=sys.stderr,
                )
                return 2
            return 0
        except (
            OSError,
            ValueError,
            TypeError,
            KeyError,
            ZeroDivisionError,
            subprocess.SubprocessError,
        ) as exc:
            print(f"takebraid: {exc}", file=sys.stderr)
            return 1
        except KeyboardInterrupt:
            print("takebraid: interpretation cancelled", file=sys.stderr)
            return 130

    if args.command == "motion":
        try:
            region = tuple(int(v) for v in args.background.split(":")) if args.background else None
            output, status = observe_motion(
                args.asset,
                args.stream,
                MotionSettings(args.size, args.every, args.radius, region),
                timeout=args.timeout,
                force=args.force,
            )
            print(output)
            if status != "observed":
                print(
                    f"takebraid: motion is {status}; inspect tracking diagnostics", file=sys.stderr
                )
                return 2
            return 0
        except (OSError, ValueError, TypeError, KeyError, subprocess.SubprocessError) as exc:
            print(f"takebraid: {exc}", file=sys.stderr)
            return 1
        except KeyboardInterrupt:
            print("takebraid: motion analysis cancelled", file=sys.stderr)
            return 130

    if args.command == "quality":
        try:
            roi = tuple(int(v) for v in args.roi.split(":")) if args.roi else None
            output, status = observe_quality(
                args.asset,
                args.stream,
                QualitySettings(args.size, args.every, roi),
                timeout=args.timeout,
                force=args.force,
            )
            print(output)
            if status == "unknown":
                print("takebraid: quality is unknown; inspect the report reasons", file=sys.stderr)
                return 2
            return 0
        except (OSError, ValueError, TypeError, KeyError, subprocess.SubprocessError) as exc:
            print(f"takebraid: {exc}", file=sys.stderr)
            return 1
        except KeyboardInterrupt:
            print("takebraid: quality analysis cancelled", file=sys.stderr)
            return 130

    if args.command in {"plan", "render"}:
        try:
            if args.command == "plan":
                cuts = []
                for value in args.cut:
                    parts = value.split(":")
                    if len(parts) != 2:
                        raise ValueError("Each --cut must be FIRST:END decoded frame indices")
                    cuts.append((int(parts[0]), int(parts[1])))
                output = create_plan(
                    args.asset,
                    args.stream,
                    tuple(cuts),
                    Fraction(args.fps),
                    args.audio,
                    args.audio_stream,
                )
            else:
                output = render_plan(
                    args.project, args.timeline, timeout=args.timeout, force=args.force
                )
            print(output)
            return 0
        except (
            OSError,
            ValueError,
            TypeError,
            KeyError,
            ZeroDivisionError,
            StopIteration,
            subprocess.SubprocessError,
        ) as exc:
            print(f"takebraid: {exc}", file=sys.stderr)
            return 1
        except KeyboardInterrupt:
            print("takebraid: preview operation cancelled", file=sys.stderr)
            return 130

    if args.command == "project":
        try:
            root = args.directory.expanduser().resolve()
            if args.project_command == "init":
                result = init_project(root)
            elif args.project_command == "show":
                result = load_project(root)
            elif args.project_command == "add":
                result = register_asset(root, args.asset)
            elif args.project_command == "relink":
                result = relink_asset(root, args.asset_id, args.source)
            else:
                result = verify_project(root)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return (
                2
                if args.project_command == "verify"
                and any(value != "verified" for value in result.values())
                else 0
            )
        except (OSError, ValueError, TypeError, KeyError) as exc:
            print(f"takebraid: {exc}", file=sys.stderr)
            return 1

    if args.command == "scan":
        try:
            output, status = scan_asset(
                args.asset,
                args.stream,
                timeout=args.timeout,
                max_frames=args.max_frames,
                force=args.force,
            )
        except ScanError as exc:
            print(f"takebraid: {exc}", file=sys.stderr)
            return 1
        print(output)
        if status != "ready":
            print(f"takebraid: timing is {status}; inspect the frame-map issues", file=sys.stderr)
            return 2
        return 0

    if args.command == "ingest":
        try:
            output = ingest(args.source, args.project)
        except IngestError as exc:
            print(f"takebraid: {exc}", file=sys.stderr)
            return 1
        print(output)
        return 0

    tools = {name: shutil.which(name) for name in ("ffmpeg", "ffprobe")}
    report = {
        "takebraid": __version__,
        "python": platform.python_version(),
        "tools": tools,
        "media_tools_available": all(tools.values()),
    }
    if args.as_json:
        print(json.dumps(report, sort_keys=True))
    else:
        print(f"Takebraid {__version__} / Python {report['python']}")
        for name, path in tools.items():
            print(f"{name}: {path or 'missing (install separately for media processing)'}")
        print(
            "Status: manual plans/previews available; automatic selection is not implemented yet."
        )
    return 0 if report["media_tools_available"] else 1
