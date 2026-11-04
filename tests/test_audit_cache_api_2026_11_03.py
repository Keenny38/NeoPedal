#  NeoPedal is an open-source overlay application for racing simulation.
#  Copyright (C) 2022-2026 TinyPedal developers, see contributors.md file
#
#  This file is part of NeoPedal.
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""Cache & API audit 2026-11-03: update checks & the community lap times sheet keep their last answer and wait
after a failure (RaceOS reads removed 2026-11-04)"""

from __future__ import annotations

import time

import pytest


def release_body(tag: str = "v0.30.0") -> bytes:
    import json

    return b"HTTP/1.1 200 OK\r\n\r\n" + json.dumps({
        "tag_name": tag, "published_at": "2026-11-10T00:00:00Z", "body": "### New\n\n- x", "assets": []}).encode()


def test_failed_update_check_keeps_the_last_result(monkeypatch):
    from neopedal import update, version

    answers = [release_body(), b""]  # second check: offline, rate limit or GitHub error

    async def latest(repo):
        return answers.pop(0)

    monkeypatch.setattr(update, "request_latest_release", latest)
    monkeypatch.setattr(update, "verified_release", lambda *args: None)
    monkeypatch.setattr(update, "fetch_changelog", lambda *args, **kwargs: "")
    monkeypatch.setattr(version, "__version__", "0.29.0")
    checker = update.UpdateChecker()
    checker._UpdateChecker__checking("Keenny38/NeoPedal")
    assert checker.is_updates() and checker.latest_version() == (0, 30, 0)
    checker._UpdateChecker__checking("Keenny38/NeoPedal")
    assert checker.is_updates() and checker.latest_version() == (0, 30, 0)  # notice kept, not erased
    assert checker.message().startswith("New Updates")


def test_changelog_not_read_is_not_kept_as_the_release_changelog(monkeypatch):
    from neopedal import update

    calls = []
    results = [update.ChangelogUnavailable("HTTP 503"), "## 0.30.0 (2026-11-10)\n\n- x\n"]

    def fetch(repo, tag, language, timeout=5):
        calls.append(language)
        result = results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(update, "fetch_changelog", fetch)
    checker = update.UpdateChecker()
    assert checker._changelog("a/b", "v0.30.0", "en") == ""  # offline: nothing kept
    assert checker._changelog("a/b", "v0.30.0", "en").startswith("## 0.30.0")  # next check reads it
    assert checker._changelog("a/b", "v0.30.0", "en").startswith("## 0.30.0") and len(calls) == 2


def test_missing_translation_is_final_but_a_server_error_is_not(monkeypatch):
    import io
    import urllib.error

    from neopedal import update

    def failing(code):
        def open_url(url, timeout):
            raise urllib.error.HTTPError(url, code, "x", {}, io.BytesIO(b""))  # type: ignore[arg-type]
        return open_url

    monkeypatch.setattr(update, "open_url", failing(404))
    assert update.fetch_changelog("a/b", "v1.0.0", "fr") == ""  # not translated
    monkeypatch.setattr(update, "open_url", failing(503))
    with pytest.raises(update.ChangelogUnavailable):
        update.fetch_changelog("a/b", "v1.0.0", "fr")


def test_failed_sheet_download_waits_before_the_next_page_opening(tmp_path):
    from neopedal.ui.quick.stats_common import REFERENCE_RETRY_SECONDS
    from neopedal.userfile import lap_reference

    folder = str(tmp_path)
    assert not lap_reference.failed_recently(folder, REFERENCE_RETRY_SECONDS)
    lap_reference.mark_download(folder, failed=True)
    assert lap_reference.failed_recently(folder, REFERENCE_RETRY_SECONDS)  # page reopened: no new attempts
    assert not lap_reference.failed_recently(folder, REFERENCE_RETRY_SECONDS, now=time.time() + 3601)
    lap_reference.mark_download(folder, failed=False)  # one worked
    assert not lap_reference.failed_recently(folder, REFERENCE_RETRY_SECONDS)
