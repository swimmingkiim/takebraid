import json
import shutil
import subprocess

import pytest

from takebraid.adapters.projects import load_project, relink_asset, verify_project
from takebraid.application.ingest import ingest
from takebraid.application.scan import scan_asset

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not (shutil.which("ffmpeg") and shutil.which("ffprobe")),
        reason="requires media tools",
    ),
]


def test_real_project_relink_and_cached_scan_survive_source_move(tmp_path):
    source = tmp_path / "source.mov"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-nostdin",
            "-f",
            "lavfi",
            "-i",
            "color=c=blue:s=64x48:r=25:d=0.2",
            "-c:v",
            "mpeg4",
            str(source),
        ],
        capture_output=True,
        check=True,
        timeout=30,
    )
    root = tmp_path / "project"
    asset = ingest(source, root)
    first, status = scan_asset(asset, 0)
    assert status == "ready"
    original = asset.read_bytes()
    asset_id = json.loads(original)["asset_id"]
    moved = tmp_path / "moved.mov"
    source.rename(moved)
    relink_asset(root, asset_id, moved)
    assert verify_project(root) == {asset_id: "verified"}
    assert scan_asset(asset, 0)[0] == first
    second, _ = scan_asset(asset, 0, force=True)
    assert second != first
    assert first.exists()
    assert asset.read_bytes() == original
    assert load_project(root)["assets"][asset_id]["source_locator"] == str(moved)
