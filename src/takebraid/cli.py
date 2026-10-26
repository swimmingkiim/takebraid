"""Small bootstrap CLI; editing commands arrive with their working implementations."""

import argparse
import json
import platform
import shutil
import sys
from pathlib import Path

from takebraid import __version__
from takebraid.application.ingest import IngestError, ingest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Turn raw footage into a considered first cut.")
    parser.add_argument("--version", action="version", version=f"takebraid {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)
    doctor = commands.add_parser("doctor", help="Report Python and media tool availability.")
    doctor.add_argument("--json", action="store_true", dest="as_json")
    register = commands.add_parser("ingest", help="Inspect a local video and save asset metadata.")
    register.add_argument("source", type=Path)
    register.add_argument("--project", type=Path, required=True, help="Project output directory.")
    args = parser.parse_args(argv)

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
        print("Status: metadata ingest available; analysis and editing are not implemented yet.")
    return 0 if report["media_tools_available"] else 1
