"""Bug audit 2026-11-01 of the VR layer (audit_bugs_vr_2026-11-01.md): one regression test per bug fixed"""

import sys
import threading
import time
import types

from PySide6.QtCore import QCoreApplication

from neopedal import vr_overlay
from neopedal.setting import cfg
from neopedal.vr_overlay import VROverlay
from tests.test_vr_overlay_openvr import FakeIVROverlay, HmdMatrix34_t

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

