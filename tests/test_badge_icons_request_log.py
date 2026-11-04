"""Badge icon downloads are told in the requests journal (requests dialog, bug report)"""

import io
import urllib.error

import pytest

from neopedal import request_log
from neopedal.userfile import badge_icons


class Answer(io.BytesIO):
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


@pytest.fixture(autouse=True)
def clean_journal():
    request_log.clear()
    yield
    request_log.clear()


def last_line():
    return request_log.snapshot()[request_log.BADGE_ICONS]["lines"][0]


def test_download_recorded(monkeypatch):
    monkeypatch.setattr(badge_icons.urllib.request, "urlopen", lambda *_args, **_kw: Answer(b"<svg/>"))
    assert badge_icons.download(badge_icons.icon_url("sr-clean")) == b"<svg/>"
    line = last_line()
    assert line.status == 200 and line.route == "GET badge icon"  # no badge name in the route
    assert request_log.snapshot()[request_log.BADGE_ICONS]["hour"] == 1


def test_http_error_recorded(monkeypatch):
    def refuse(*_args, **_kw):
        raise urllib.error.HTTPError("https://x", 404, "Not Found", None, None)

    monkeypatch.setattr(badge_icons.urllib.request, "urlopen", refuse)
    assert badge_icons.download(badge_icons.icon_url("nope")) == b""
    assert last_line().status == 404


def test_no_answer_recorded(monkeypatch):
    def offline(*_args, **_kw):
        raise OSError("offline")

    monkeypatch.setattr(badge_icons.urllib.request, "urlopen", offline)
    assert badge_icons.download(badge_icons.icon_url("sr-clean")) == b""
    assert last_line().status == 0
