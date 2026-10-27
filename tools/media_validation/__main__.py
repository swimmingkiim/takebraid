import argparse
import json
from pathlib import Path

from tools.media_validation.runner import run_matrix


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate and check the synthetic media matrix.")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--case", action="append", dest="cases")
    args = parser.parse_args()
    path = run_matrix(args.output, args.cases)
    print(path)
    return 1 if json.loads(path.read_text())["failed"] else 0


raise SystemExit(main())
