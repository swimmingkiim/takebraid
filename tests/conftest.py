import json

import pytest

from takebraid.adapters.media.probe import parse_probe


@pytest.fixture
def probe_metadata():
    return parse_probe(
        json.dumps(
            {
                "program_version": {"version": "test-version"},
                "format": {"format_name": "test"},
                "streams": [{"index": 0, "codec_type": "video", "time_base": "1/1000"}],
            }
        )
    )
