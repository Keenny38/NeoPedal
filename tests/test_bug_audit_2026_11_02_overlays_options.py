"""Bug audit of the Overlays page & overlay options (2026-11-02): regression tests of the fixed bugs

See audit_bugs_overlays_options_2026-11-02.md (B-xxx numbers).
"""

import copy

import pytest
from PySide6.QtCore import QCoreApplication, QEvent

from neopedal.setting import cfg
from neopedal.ui.quick import overlay_backend
from neopedal.ui.quick.overlay_backend import OverlayBackend
from tests.test_overlays_page_more import NAMES, FakeControl, solid


@pytest.fixture
def page(ui_env, monkeypatch):
    for name in NAMES:
        cfg.user.setting[name]["enable"] = name in ("brake_temperature", "speedometer")
    monkeypatch.setattr(overlay_backend, "render_preview", lambda name: solid("#336699"))
    monkeypatch.setattr(overlay_backend, "make_live_preview", lambda name: None)
    control = FakeControl(NAMES)
    backend = OverlayBackend(None, control, lambda name: None, lambda text: True)
    backend.test_control = control
    yield backend
    backend.close()
    backend.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    QCoreApplication.processEvents()


# B-003: page undo history kept across preset loads, undo inverting the state
def test_b003_toggle_undo_never_switches_overlay_of_another_preset(page, monkeypatch):
    """Overlay switched on in preset A, preset B loaded, Ctrl+Z: overlay of B left as it is (was: switched off)"""
    monkeypatch.setattr(cfg.filename, "setting", "A.json")
    page.toggle("fuel")
    assert cfg.user.setting["fuel"]["enable"] and page.canUndo
    loaded = copy.deepcopy(cfg.user.setting)  # preset B: fuel on there by the user's choice
    monkeypatch.setattr(cfg.user, "setting", loaded)
    monkeypatch.setattr(cfg.filename, "setting", "B.json")
    page.refresh()
    assert not page.canUndo
    page.undo()
    assert cfg.user.setting["fuel"]["enable"]


def test_b003_toggle_undo_restores_state_switched_elsewhere(page):
    """Overlay switched on from the page, then off elsewhere (tray, options page): Ctrl+Z leaves it off (was: on)"""
    page.toggle("fuel")
    assert cfg.user.setting["fuel"]["enable"]
    page.test_control.toggle("fuel")
    page.refresh()
    page.undo()
    assert not cfg.user.setting["fuel"]["enable"]
    page.toggle("fuel")  # plain undo still switches back
    page.undo()
    assert not cfg.user.setting["fuel"]["enable"]


def test_b003_toast_undo_of_another_preset_does_nothing(page, monkeypatch):
    """Undo button of a toast clicked once another preset is loaded: nothing switched"""
    monkeypatch.setattr(cfg.filename, "setting", "A.json")
    toast_undo = page._push_undo("toggle", "fuel", lambda: page.test_control.toggle("fuel"))
    monkeypatch.setattr(cfg.filename, "setting", "B.json")
    before = cfg.user.setting["fuel"]["enable"]
    toast_undo()
    assert cfg.user.setting["fuel"]["enable"] == before
