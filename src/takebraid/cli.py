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
from takebraid.application.ingest import IngestError, ingest
from takebraid.application.preview import create_plan, render_plan
from takebraid.application.scan import ScanError, scan_asset


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
