"""Post-mortem 0.28.0, P2 items 12 & 13: garbage collection on the UI thread only (QObject never freed by a worker
thread), no reference cycle left by the Driver Stats page, history records never lost by an append landing while
the history file is read"""

import gc
import json
import os
import threading
import time
import weakref
from contextlib import suppress

import pytest
from PySide6.QtCore import QCoreApplication, QEvent
from shiboken6 import Shiboken

from tests.test_driver_stats_viewer import (  # noqa: F401  (fixtures)
    HISTORY,
    SHEET,
    SPA,
    STATS,
    dialogs,
    settle,
    write_stats,
)


# --- Item 12 (b): no QObject left in a reference cycle by the Driver Stats page
def collected_garbage() -> list:
    """Objects a full collection finds unreachable now (kept for inspection, then dropped)"""
    gc.set_debug(gc.DEBUG_SAVEALL)
    try:
        gc.collect()
        garbage = gc.garbage[:]
    finally:
        gc.set_debug(0)
        gc.garbage.clear()
    return garbage


def qobjects_in(garbage: list, own: weakref.WeakSet) -> list[str]:
    """QObject wrappers of own (objects of the page under test, never those of earlier tests) among garbage: type
    name & whether its C++ object still lives (freed with the wrapper, on whichever thread the collector runs)"""
    from PySide6.QtCore import QObject

    # type() never forwarded (weak proxy of a gone object); QObject only (value types like QFontMetricsF unhashable)
    return [f"{type(item).__name__}{' (alive)' if Shiboken.isValid(item) else ''}"
            for item in garbage if issubclass(type(item), QObject) and item in own]


def page_objects(viewer, backend) -> weakref.WeakSet:
    """QObjects of a page (held weakly): page, its children & QObjects its backend holds (with or without parent)"""
    from PySide6.QtCore import QObject

    found = [viewer, backend, *viewer.findChildren(QObject), *backend.findChildren(QObject)]
    found += [value for value in vars(backend).values() if isinstance(value, QObject)]
    own: weakref.WeakSet = weakref.WeakSet()
    for item in found:
        with suppress(TypeError):  # wrapper without weak reference support: not checked
            own.add(item)
    return own


@pytest.mark.parametrize("job_running", [False, True], ids=["idle", "job_running"])
def test_driver_stats_page_closed_leaves_no_cycle(dialogs, monkeypatch, job_running):  # noqa: F811
    """Page closed (idle, or while its history is read on a worker thread): every page object freed at once on the
    UI thread by reference counting, none left for the garbage collector (which may run on any thread)"""
    from neopedal.api_control import api
    from neopedal.setting import cfg
    from neopedal.ui.driver_stats_viewer import DriverStatsViewer
    from neopedal.ui.quick import stats_core, stats_io
    from neopedal.userfile import driver_history, lap_reference

    write_stats(STATS)
    lap_reference.save_cache(cfg.path.config, SHEET)
    driver_history.save_history(cfg.path.config, HISTORY)
    driver_history.forget_records()
    monkeypatch.setattr(type(api.read.session), "track_name", lambda self: SPA, raising=False)
    monkeypatch.setattr(stats_core, "SYNC_HISTORY_BYTES", 0)  # history read on a worker thread
    started, release = threading.Event(), threading.Event()
    original = stats_io.load_history

    def load_history(path, strict=False):
        if job_running and threading.current_thread() is not threading.main_thread():
            started.set()
            release.wait(10)
        return original(path, strict)

    monkeypatch.setattr(stats_io, "load_history", load_history)
    collected_garbage()  # earlier tests' garbage out of the way
    gc.disable()
    try:
        viewer = DriverStatsViewer(None)
        viewer.resize(1200, 800)
        viewer.show()
        backend = viewer.backend
        if job_running:
            assert started.wait(10)  # page closed while its history is read
        else:
            settle(backend)
            backend.reload_stats()  # jobs started & handed over again
            settle(backend)
        references = [weakref.ref(viewer), weakref.ref(backend), weakref.ref(backend.jobs)]
        own = page_objects(viewer, backend)
        del backend
        viewer.close()
        viewer.deleteLater()
        del viewer
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        release.set()
        deadline = time.monotonic() + 10
        while any(ref() is not None for ref in references) and time.monotonic() < deadline:
            QCoreApplication.processEvents()  # job handed over (dropped): its work & result freed here
            time.sleep(0.005)
        QCoreApplication.processEvents()
        in_cycle = [type(ref()).__name__ for ref in references if ref() is not None]  # freed only by a collection
        garbage = collected_garbage()
        kept = [type(ref()).__name__ for ref in references if ref() is not None]
    finally:
        gc.enable()
    names = qobjects_in(garbage, own)
    del garbage
    assert not names, f"QObjects freed by the garbage collector (reference cycle): {names}"
    assert not in_cycle, f"page objects in a reference cycle: {in_cycle}"
    assert not kept, f"page objects kept after closed: {kept}"


# --- Item 13: history record never lost when an append lands while the file is read
class Interleaved:
    """History file opened by parse_file: writer's append (rest of a line) lands between two line reads, once a
    line without end was read (Linux makes a write visible page by page: a reader may see half a line)"""

    def __init__(self, file, append):
        self._file = file
        self._append = append

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self._file.close()

    def __getattr__(self, name):
        return getattr(self._file, name)

    def __iter__(self):
        while True:
            line = self._file.readline()
            if not line:
                return
            yield line
            if not line.endswith(b"\n") and self._append is not None:
                self._append()  # rest of the line written now, before the reader asks for the next line
                self._append = None


def history_records(count: int):
    from neopedal.userfile.driver_history import SessionRecord

    return [SessionRecord(1_700_000_000.0 + index * 60, f"Track {index % 3}", "GT3 - BMW", 1, 100.0 + index)
            for index in range(count)]


def test_append_landing_between_line_reads_never_loses_record(tmp_path, monkeypatch):
    from neopedal.userfile import driver_history
    from neopedal.userfile.driver_history import read_records, record_line

    folder = str(tmp_path)
    path = driver_history.history_path(folder)
    records = history_records(4)
    lines = [record_line(entry).encode("utf-8") for entry in records]
    with open(path, "wb") as file:
        file.write(b"".join(lines[:3]) + lines[3][:25])  # last record half visible
    driver_history.forget_records(folder)

    written = []

    def append():
        written.append(1)
        with open(path, "ab") as file:
            file.write(lines[3][25:])

    appended = []
    real_open = open

    def interleaved_open(file, mode="r", *args, **kwargs):
        opened = real_open(file, mode, *args, **kwargs)
        if not appended and "b" in mode and "r" in mode:
            appended.append(1)
            return Interleaved(opened, append)
        return opened

    with monkeypatch.context() as patch:
        patch.setattr(driver_history, "open", interleaved_open, raising=False)
        first = read_records(folder)
    assert first in (records[:3], records)  # half record not read yet, or whole
    if not written:
        append()  # reader stopped at the half line: rest written after the read
    assert read_records(folder) == records  # next read (file grown) finds the record
    with open(path, "ab") as file:
        file.write(record_line(history_records(5)[4]).encode("utf-8"))
    assert read_records(folder) == history_records(5)  # later appends read from the right offset


def test_append_between_size_check_and_read(tmp_path, monkeypatch):
    """Record appended after the file size was taken, before its lines are read: read next time, never skipped once
    the file stops changing"""
    from neopedal.userfile import driver_history
    from neopedal.userfile.driver_history import read_records, record_line

    folder = str(tmp_path)
    path = driver_history.history_path(folder)
    records = history_records(6)
    with open(path, "wb") as file:
        file.write(b"".join(record_line(entry).encode("utf-8") for entry in records[:4]))
    driver_history.forget_records(folder)
    real_fstat = os.fstat
    pending = [records[4], records[5]]

    def fstat_then_append(fd):
        stat = real_fstat(fd)
        if pending:
            line = record_line(pending.pop(0)).encode("utf-8")
            with open(path, "ab") as file:  # appended after size taken: half, then the rest (two writes)
                file.write(line[:30])
                file.write(line[30:])
        return stat

    with monkeypatch.context() as patch:
        patch.setattr(driver_history.os, "fstat", fstat_then_append)
        read_records(folder)
        read_records(folder)
    assert read_records(folder) == records
    assert read_records(folder) == records  # file unchanged since: kept records complete


# --- Item 12 (a): garbage collection on the UI thread only
def test_due_generation_follows_interpreter_rule():
    from neopedal.loader import due_generation

    threshold = (2000, 10, 10)
    assert due_generation((1999, 9, 9), threshold) == -1
    assert due_generation((2000, 0, 0), threshold) == 0
    assert due_generation((2500, 10, 3), threshold) == 1
    assert due_generation((5, 10, 10), threshold) == 2  # oldest due generation (collects the younger ones too)
    assert due_generation((5000, 10, 10), (0, 10, 10)) == -1  # collection turned off (threshold 0)
    assert due_generation((2000, 50), (2000, 0)) == 0  # generation with threshold 0 never collected alone


@pytest.fixture
def collect_calls(monkeypatch):
    from neopedal import loader, realtime_state

    calls = []
    monkeypatch.setattr(loader.gc, "collect", lambda generation=2: calls.append(generation) or 0)
    monkeypatch.setattr(loader.gc, "get_threshold", lambda: (2000, 10, 10))
    monkeypatch.setattr(loader.gc, "isenabled", lambda: False)
    monkeypatch.setattr(realtime_state, "active", False)
    return calls


def test_collect_due_on_timer(collect_calls, monkeypatch):
    from neopedal import loader, realtime_state

    count = [(100, 0, 0)]
    monkeypatch.setattr(loader.gc, "get_count", lambda: count[0])
    assert loader.collect_due() == -1 and collect_calls == []  # nothing due: timer tick costs nothing
    count[0] = (2400, 3, 1)
    assert loader.collect_due() == 0
    count[0] = (2400, 10, 10)
    monkeypatch.setattr(loader, "_gc_last_full", time.monotonic())
    monkeypatch.setattr(realtime_state, "active", True)
    assert loader.collect_due() == 1  # driving: full collection waits FULL_COLLECT_DRIVING_S
    monkeypatch.setattr(loader, "_gc_last_full", time.monotonic() - loader.FULL_COLLECT_DRIVING_S)
    assert loader.collect_due() == 2
    assert loader.collect_due() == 1  # just done
    monkeypatch.setattr(realtime_state, "active", False)
    assert loader.collect_due() == 2  # not driving: as the interpreter would
    assert collect_calls == [0, 1, 2, 1, 2]


def test_collect_due_turns_automatic_collection_off_again(collect_calls, monkeypatch):
    from neopedal import loader

    disabled = []
    monkeypatch.setattr(loader.gc, "isenabled", lambda: True)  # a library turned it on
    monkeypatch.setattr(loader.gc, "disable", lambda: disabled.append(1))
    monkeypatch.setattr(loader.gc, "get_count", lambda: (0, 0, 0))
    loader.collect_due()
    assert disabled == [1]


UI_THREAD_COLLECTION = r"""
import gc, json, sys, threading, time
from PySide6.QtCore import QCoreApplication, QObject
app = QCoreApplication([])
from neopedal import loader

freed = []

class Page(QObject):  # QObject without parent in a reference cycle: freed with its C++ object
    def __init__(self):
        super().__init__()
        self.cycle = self

    def __del__(self):
        freed.append(threading.current_thread().name)

if sys.argv[1] == "ui":
    loader.collect_on_ui_thread()
gc.collect()
for _ in range(50):
    Page()  # unreachable at once, freed only by a collection
stop = threading.Event()

def worker():  # allocates as a module or page job does: automatic collection would run here
    keep = []
    while not stop.is_set():
        keep.append([{} for _ in range(100)])
        node = []
        node.append(node)  # garbage cycles made by the worker too
        if len(keep) > 50:
            keep.pop(0)

thread = threading.Thread(target=worker, name="Worker")
thread.start()
end = time.monotonic() + 1.5
while time.monotonic() < end:
    if sys.argv[1] == "ui":
        app.processEvents()  # collection timer
    time.sleep(0.005)  # UI thread allocates nothing meanwhile: automatic collection runs on the worker
young = gc.get_count()[0]
stop.set()
thread.join()
app.processEvents()
print(json.dumps({"freed": len(freed), "threads": sorted(set(freed)), "enabled": gc.isenabled(), "young": young}))
"""


@pytest.mark.parametrize("mode", ["automatic", "ui"])
def test_cycles_freed_on_ui_thread_only(mode):
    """Automatic collection frees a QObject cycle on the thread allocating at that moment (crash class of the
    post-mortem); collected by the UI thread timer instead, every cycle is freed there, young generation bounded"""
    import subprocess
    import sys

    result = subprocess.run([sys.executable, "-c", UI_THREAD_COLLECTION, mode], capture_output=True, text=True,
                            timeout=120, env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
                            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    assert result.returncode == 0, result.stderr
    outcome = json.loads(result.stdout.strip().splitlines()[-1])
    assert outcome["freed"] == 50, outcome
    if mode == "ui":
        assert outcome["threads"] == ["MainThread"] and not outcome["enabled"], outcome
        assert outcome["young"] < 50_000, outcome  # worker allocations collected by the timer meanwhile
    else:
        assert "Worker" in outcome["threads"], outcome  # the crash class, without UI thread collection
