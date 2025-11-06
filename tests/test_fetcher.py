import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import fetcher


def test_filename_for_ts():
    ts = datetime(2020, 1, 2, 3, 4, 5)
    assert fetcher.filename_for_ts(ts, ".jpg") == "20200102_030405.jpg"


class DummyResp:
    def __init__(self, headers):
        self.headers = headers


def test_guess_extension_from_content_type():
    r = DummyResp({"content-type": "image/png; charset=utf-8"})
    assert fetcher.guess_extension(r, "http://example.com/a") == ".png"


def test_guess_extension_from_url():
    r = DummyResp({})
    assert fetcher.guess_extension(r, "http://example.com/foo.jpg?x=1") == ".jpg"
