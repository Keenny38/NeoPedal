"""Bug audit 2026-11-01 of the VR layer (audit_bugs_vr_2026-11-01.md): one regression test per bug fixed"""

import struct
import sys
import threading
import time
import types

import pytest
from PySide6.QtCore import QCoreApplication

from neopedal import vr_overlay, vr_shared
from neopedal.setting import cfg
from neopedal.vr_overlay import VROverlay
from tests.test_vr_overlay_openvr import FakeIVROverlay, HmdMatrix34_t
from tests.test_vr_shared import env  # noqa: F401

WAIT_S = 10.0  # upper bound of a wait for a background thread (never reached when it works)


def wait_until(condition, pump=None) -> bool:
    """condition() true within WAIT_S (pump() called between checks)"""
    deadline = time.monotonic() + WAIT_S
    while time.monotonic() < deadline:
        if pump is not None:
            pump()
        if condition():
            return True
        time.sleep(0.005)
    return condition()


# B-005: SteamVR start dropped by a reload shut openvr down under the next start's overlay


def test_b005_dropped_steamvr_start_never_runs_with_next_one(ui_env, monkeypatch):
    log = []
    first_in_init = threading.Event()
    release_first = threading.Event()
    calls = []

    def init(app_type):
        calls.append(app_type)
        number = len(calls)
        log.append(("init", number))
        if number == 1:  # SteamVR slow to answer (starting or closing)
            first_in_init.set()
            release_first.wait(WAIT_S)
        log.append(("init done", number))

    module = types.ModuleType("openvr")
    module.VRApplication_Overlay = 2
    module.TrackingUniverseSeated = 0
    module.k_unTrackedDeviceIndex_Hmd = 0
    module.HmdMatrix34_t = HmdMatrix34_t
    module.init = init
    module.shutdown = lambda: log.append(("shutdown",))
    module.IVROverlay = lambda: FakeIVROverlay(log)
    monkeypatch.setitem(sys.modules, "openvr", module)

    class SyncCheck:  # SteamVR process found at once
        running = True

        def done(self):
            return True

    monkeypatch.setattr(vr_overlay, "SteamVRCheck", SyncCheck)
    cfg.user.config["vr_overlay"].update(enable_vr_overlay=True, enable_vr_mirror_window=False)
    control = VROverlay()
    try:
        control.enable()  # first start blocked in openvr.init
        assert first_in_init.wait(WAIT_S)
        control.disable()  # overlays reloaded meanwhile
        control.enable()
        for _ in range(5):  # ticks: second start created, waits for the first one
            control.update_overlay()
            time.sleep(0.01)
        assert ("init", 2) not in log, "second openvr.init while the dropped start is still in openvr.init"
        release_first.set()
        assert wait_until(lambda: control._handle is not None, control.update_overlay)
        # Dropped start released (overlay destroyed, openvr shut down) before the next start's openvr.init
        assert log.index(("shutdown",)) < log.index(("init", 2))
        assert log.count(("shutdown",)) == 1
    finally:
        release_first.set()
        control.disable()
        assert wait_until(lambda: not vr_overlay._STEAMVR_START_LOCK.locked())  # no thread left to other tests
        QCoreApplication.processEvents()


# B-006: two app instances (portable copy: own config folder & instance lock) shared the shared memory & layer
# registration: one closing hid the other's overlay & unregistered its layer


@pytest.mark.skipif(sys.platform != "win32", reason="named mutex (Windows)")
def test_b006_writer_lock_taken_by_one_instance():
    first = vr_shared.acquire_writer_lock()
    try:
        assert first is not None and vr_shared.writer_lock_held()
        assert vr_shared.acquire_writer_lock() is None  # second app instance
    finally:
        vr_shared.close_handle(first)
    assert not vr_shared.writer_lock_held()
    again = vr_shared.acquire_writer_lock()  # free again once the first instance closed (or crashed)
    assert again is not None
    vr_shared.close_handle(again)


def test_b006_second_instance_leaves_first_instance_layer(env, monkeypatch):  # noqa: F811
    held = []  # fake named mutex (any OS)

    def acquire(name=None):
        if held:
            return None
        held.append(name)
        return 7

    monkeypatch.setattr(vr_shared, "acquire_writer_lock", acquire, raising=False)
    monkeypatch.setattr(vr_shared, "writer_lock_held", lambda name=None: bool(held), raising=False)
    monkeypatch.setattr(vr_shared, "close_handle", lambda handle: held.clear())
    first, second = VROverlay(), VROverlay()
    try:
        first.enable()
        assert first.openxr_active and len(env.registered) == 1
        heartbeat = struct.unpack_from("<Q", env.buffer, vr_shared.OFFSET_APP_HEARTBEAT)[0]
        assert heartbeat != 0
        second.enable()  # portable copy started
        assert not second.openxr_active and len(env.registered) == 1
        assert any("another NeoPedal instance" in error for error in env.errors)
        second.disable()  # portable copy closed: first instance's overlay & registration kept
        assert not env.unregistered
        assert struct.unpack_from("<Q", env.buffer, vr_shared.OFFSET_APP_HEARTBEAT)[0] == heartbeat
        first.disable()
        assert env.unregistered and not held
    finally:
        second.disable()
        first.disable()
