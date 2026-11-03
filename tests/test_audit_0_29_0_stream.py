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

"""Stream overlays bug audit before 0.29.0 (2026-11-02): "On air" counts sources showing something only, results
page follows the colorblind option & fits 24 h race times, overlay sources woken by their own overlay only, layout
size of the screen the capture uses, class key read safely from server threads"""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from types import SimpleNamespace

import pytest
from PySide6.QtGui import QImage

from neopedal import stream_overlay
from neopedal.process import results_file as rf
from neopedal.stream_overlay import FrameStore, Placement
from neopedal.template.setting_status_colors import status_css


def image(width=10, height=10) -> QImage:
    picture = QImage(width, height, QImage.Format.Format_ARGB32)
    picture.fill(0x80FF0000)
    return picture


def bundle_head(data: bytes) -> dict:
    length = int.from_bytes(data[:4], "big")
    return json.loads(data[4:4 + length])


# B-004: an overlay source waits for its own overlay, not for every frame of another overlay
def test_b004_overlay_source_woken_by_its_overlay_only():
    store = FrameStore()
    store.publish({"gear": image(), "fuel": image()}, [Placement("gear", 0, 0, 1.0), Placement("fuel", 50, 0, 1.0)],
                  (1920, 1080))
    seq = store.seq
    store.publish({"fuel": image(12, 10)}, [Placement("gear", 0, 0, 1.0), Placement("fuel", 50, 0, 1.0)], (1920, 1080))
    started = time.monotonic()
    head = bundle_head(store.bundle("gear", seq, "zraw", timeout=0.2))  # fuel changed only: waits
    assert time.monotonic() - started >= 0.15
    assert head["seq"] == store.seq and [(entry["name"], entry["size"]) for entry in head["overlays"]] == [("gear", 0)]
    started = time.monotonic()
    head = bundle_head(store.bundle("layout", seq, "zraw", timeout=2))  # layout: any change
    assert time.monotonic() - started < 1 and [entry["name"] for entry in head["overlays"]] == ["gear", "fuel"]
    seq = store.seq
    # Own image, opacity, hidden, canvas, cleared, layout places: answered at once
    changes = (
        lambda: store.publish({"gear": image(14, 10)}, [Placement("gear", 0, 0, 1.0), Placement("fuel", 50, 0, 1.0)],
                              (1920, 1080)),
        lambda: store.publish({}, [Placement("gear", 0, 0, 0.5), Placement("fuel", 50, 0, 1.0)], (1920, 1080)),
        lambda: store.publish({}, [Placement("fuel", 50, 0, 1.0)], (1920, 1080)),
        lambda: store.publish({}, [Placement("fuel", 50, 0, 1.0)], (2560, 1440)),
        store.bump,
        store.clear,
    )
    for change in changes:
        change()
        started = time.monotonic()
        store.bundle("gear", seq, "zraw", timeout=2)
        assert time.monotonic() - started < 1, change
        seq = store.seq
    assert bundle_head(store.bundle("gear", 999, "zraw", timeout=0.01))["overlays"] == []  # server started again


def test_b004_waiting_overlay_source_woken_when_its_overlay_changes():
    store = FrameStore()
    store.publish({"gear": image(), "fuel": image()}, [Placement("gear", 0, 0, 1.0), Placement("fuel", 50, 0, 1.0)],
                  (1920, 1080))
    seq = store.seq
    answers: list[tuple[float, dict]] = []

    def wait():
        started = time.monotonic()
        head = bundle_head(store.bundle("gear", seq, "zraw", timeout=5))
        answers.append((time.monotonic() - started, head))

    thread = threading.Thread(target=wait)
    thread.start()
    time.sleep(0.05)
    for _ in range(5):  # other overlay changing: gear source keeps waiting
        store.publish({"fuel": image()}, [Placement("gear", 0, 0, 1.0), Placement("fuel", 50, 0, 1.0)], (1920, 1080))
        time.sleep(0.02)
    assert not answers
    store.publish({"gear": image(20, 10)}, [Placement("gear", 0, 0, 1.0), Placement("fuel", 50, 0, 1.0)], (1920, 1080))
    thread.join(5)
    assert answers and answers[0][0] < 4
    entry = answers[0][1]["overlays"][0]
    assert entry["name"] == "gear" and entry["w"] == 20 and entry["size"] > 0


# L: classes key read on server threads while a reload changes the classes (GUI thread)
def test_classes_key_read_again_when_changed_meanwhile(ui_env, monkeypatch):
    calls = []
    real_dumps = json.dumps

    def dumps(*args, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("dictionary changed size during iteration")
        return real_dumps(*args, **kwargs)

    monkeypatch.setattr(stream_overlay.json, "dumps", dumps)
    key = stream_overlay.classes_key()
    monkeypatch.setattr(stream_overlay.json, "dumps", real_dumps)
    assert len(calls) == 2 and key == stream_overlay.classes_key() != 0
    monkeypatch.setattr(stream_overlay.json, "dumps", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError()))
    assert stream_overlay.classes_key() == 0  # never an error page


# B-002: "On air: N sources shown" counts sources showing something, as on_air
def test_b002_on_air_counts_sources_showing_something(ui_env, monkeypatch):
    from neopedal import i18n
    from neopedal.setting import cfg
    from neopedal.ui.quick import stream_backend

    i18n.set_language("English")
    for name, enabled, visibility in (("gear", True, "Screen & Stream"), ("radar", True, "Screen Only"),
                                      ("fuel", False, "Screen & Stream")):
        monkeypatch.setitem(cfg.user.setting[name], "enable", enabled)
        monkeypatch.setitem(cfg.user.setting[name], "stream_visibility", visibility)
    store = FrameStore()
    monkeypatch.setattr(stream_overlay.streamoverlay, "store", store)
    monkeypatch.setattr(type(stream_overlay.streamoverlay), "running", property(lambda self: True))
    monkeypatch.setitem(cfg.user.config["stream_overlay"], "enable_stream_overlay", True)
    backend = stream_backend.StreamOverlaysBackend()
    try:
        for view in ("radar", "fuel", "does_not_exist"):  # screen only, disabled, unknown: empty sources
            store.touch(view)
        backend.refresh(force=True)
        assert backend.watchingCount == 0 and backend.statusText == "Ready"
        assert not stream_overlay.streamoverlay.on_air()
        store.touch("gear")
        backend.refresh(force=True)
        assert backend.watchingCount == 1 and backend.statusText == "On air: 1 source shown"
        store.touch("layout")
        backend.refresh(force=True)
        assert backend.watchingCount == 2 and backend.statusText == "On air: 2 sources shown"
    finally:
        backend.deleteLater()


# B-005: layout size of the screen the capture uses (overlays shown on stream), not of every overlay window
def test_b005_layout_screen_of_stream_overlays(ui_env, monkeypatch):
    from neopedal.ui.quick import stream_backend

    shown = SimpleNamespace(wcfg={"stream_visibility": "Screen & Stream"})
    hidden = SimpleNamespace(wcfg={"stream_visibility": "Stream Only"})
    screen_only = SimpleNamespace(wcfg={"stream_visibility": "Screen Only"})
    asked = []
    monkeypatch.setattr(stream_backend, "canvas_screen", lambda widgets: asked.append(widgets))
    monkeypatch.setattr(stream_backend, "overlay_windows",
                        lambda: {"gear": shown, "fuel": hidden, "radar": screen_only})
    monkeypatch.setattr(stream_backend, "stream_overlays", lambda: [("gear", shown)])
    assert stream_backend.StreamOverlaysBackend.screen_size() == (0, 0)
    assert asked[-1] == [shown]  # same list as the capture
    monkeypatch.setattr(stream_backend, "stream_overlays", list)  # out of a session: hidden ones
    stream_backend.StreamOverlaysBackend.screen_size()
    assert asked[-1] == [shown, hidden]


# B-003: status colors sent with the results data, applied by open sources when the colorblind option changes
@pytest.fixture
def server(ui_env, monkeypatch):
    from neopedal.setting import cfg

    monkeypatch.setattr(rf, "find_results_folders", lambda libraries=None: {})
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    cfg.user.config["stream_overlay"].update({
        "enable_stream_overlay": True, "stream_overlay_port": port, "access_token": "", "enable_lan_access": False})
    control = stream_overlay.StreamOverlay()
    control.enable()
    assert control.running
    yield control
    control.disable()


def test_b003_results_status_colors_follow_colorblind_option(server, monkeypatch):
    from neopedal.setting import cfg

    style = cfg.user.config["overlay_style"]
    monkeypatch.setitem(style, "enable_colorblind_colors", False)
    with urllib.request.urlopen(server.url("/api/results"), timeout=5) as response:
        assert json.loads(response.read())["status"] == status_css()
    monkeypatch.setitem(style, "enable_colorblind_colors", True)
    with urllib.request.urlopen(server.url("/api/results"), timeout=5) as response:
        data = json.loads(response.read())
    assert data["status"] == status_css(colorblind=True) != status_css() and data["available"] is False


def results_script() -> str:
    return stream_overlay.RESULTS_HTML.split("<script>", 1)[1].split("</script>", 1)[0]


# Results page run in Node with a minimal page: status colors applied, Time / Gap column fits a 24 h race time
HARNESS = r"""
const props={};
function element(){return {style:{setProperty(){}},classList:{add(){},remove(){}},dataset:{},textContent:"",
  innerHTML:"",src:"",className:"",append(){}}}
const elements={};
globalThis.document={documentElement:{classList:{add(){}},style:{setProperty(name,value){props[name]=value}}},
  getElementById:id=>elements[id]||(elements[id]=element()),createElement:()=>element()};
globalThis.location={search:"?rows=10&token=x"};
globalThis.requestAnimationFrame=()=>0;
const realTimeout=setTimeout;
globalThis.setTimeout=(callback,delay)=>delay===5000?0:realTimeout(callback,0);
const answers=JSON.parse(process.argv[2]);let calls=0;
globalThis.fetch=async()=>({ok:true,json:async()=>answers[Math.min(calls++,answers.length-1)]});
"""

HARNESS_END = r"""
realTimeout(async()=>{const first={...props};await load();realTimeout(()=>{
  process.stdout.write(JSON.stringify({first,second:props}))},10)},10);
"""


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js not installed")
def test_results_page_script_colors_and_gap_width(tmp_path):
    def answer(gap: str, status: str) -> dict:
        return {"available": True, "id": gap, "kind": "Race", "title": "Le Mans", "subtitle": "", "trackLogo": "",
                "race": True, "partial": False, "classes": [{"name": "Hyper", "color": "#f00", "count": 1}],
                "labels": {}, "status": status,
                "rows": [{"pos": 1, "classPos": 1, "cls": "Hyper", "color": "#f00", "number": "7", "driver": "A",
                          "team": "T", "car": "C", "laps": 380, "gap": gap, "gapTone": "", "classGap": "+1.000",
                          "classGapTone": "", "best": "3:28.000", "fastest": True, "classFastest": True, "pits": 30,
                          "player": False, "logo": ""}]}

    answers = [answer("24:00:27.250", status_css()), answer("1:23.456", status_css(colorblind=True))]
    path = os.path.join(tmp_path, "results.js")
    with open(path, "w", encoding="utf-8") as file:
        file.write(HARNESS + results_script() + HARNESS_END)
    result = subprocess.run(["node", path, json.dumps(answers)], capture_output=True, text=True, timeout=60,
                            check=False)
    assert result.returncode == 0, result.stderr
    props = json.loads(result.stdout)
    first, second = props["first"], props["second"]
    row = min(78 / (10 + 3.2), 6)
    width = float(first["--gapw"][:-2])
    assert width == pytest.approx(row * 12 * .27, abs=0.01) and width > 14  # 24 h time: wider column
    assert first["--loss"] == "#f87171" and second["--loss"] == "#f08a50"  # colorblind colors at the next answer
    assert second["--gapw"] == "14.00vh"  # normal times: column as before


def test_results_page_time_cells_never_spill():
    page = stream_overlay.RESULTS_HTML
    assert "6vh var(--gapw,14vh) 13vh 10vh;" in page
    assert ".row .r{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}" in page


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js not installed")
def test_results_page_script_valid(tmp_path):
    path = os.path.join(tmp_path, "results.js")
    with open(path, "w", encoding="utf-8") as file:
        file.write(results_script().replace("@@", "__"))
    result = subprocess.run(["node", "--check", path], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
