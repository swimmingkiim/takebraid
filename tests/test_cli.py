import json

import pytest

from takebraid import __version__
from takebraid.cli import main


def test_doctor_reports_missing_media_tools(monkeypatch, capsys) -> None:
    monkeypatch.setattr("takebraid.cli.shutil.which", lambda _: None)
    assert main(["doctor", "--json"]) == 1
    report = json.loads(capsys.readouterr().out)
    assert report["media_tools_available"] is False
    assert report["tools"] == {"ffmpeg": None, "ffprobe": None}


def test_doctor_reports_available_tools(monkeypatch, capsys) -> None:
    monkeypatch.setattr("takebraid.cli.shutil.which", lambda name: f"/tools/{name}")
    assert main(["doctor"]) == 0
    output = capsys.readouterr().out
    assert "ffprobe: /tools/ffprobe" in output
    assert "not implemented yet" in output


def test_version_matches_package(capsys) -> None:
    with pytest.raises(SystemExit) as result:
        main(["--version"])
    assert result.value.code == 0
    assert capsys.readouterr().out.strip() == f"takebraid {__version__}"
