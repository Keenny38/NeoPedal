"""Bug audit of the Overlays page & overlay options (2026-11-02): regression tests of the fixed bugs

See audit_bugs_overlays_options_2026-11-02.md (B-xxx numbers).
"""

import copy

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QPoint, QRect

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


# B-004: Ctrl+Z of a screen view move undid the last change of the edit mode history (any overlay)
def screen_move(page, monkeypatch):
    """Running speedometer moved from the screen view (as Base.move_overlay: edit mode history & setting)"""
    from neopedal.widget._base import position_values
    from neopedal.widget._edit_mode import edit_mode

    monkeypatch.setattr(overlay_backend, "positions_locked", lambda: False)
    monkeypatch.setattr(overlay_backend, "screen_rects", lambda: [("Main", QRect(0, 0, 1920, 1080), True)])
    page._positions_locked = False
    edit_mode().history.clear()
    widget = page.test_control.widgets["speedometer"]
    widget.rect = QRect(100, 100, 200, 100)

    def move_overlay(pos, action, merge=False):
        before = position_values(widget.rect.topLeft())
        widget.rect.moveTopLeft(pos)
        cfg.user.setting["speedometer"].update(position_values(pos))
        edit_mode().record("speedometer", action, before, position_values(pos), merge)

    widget.move_overlay = move_overlay
    page.moveOverlay("speedometer", 500, 400)
    assert widget.rect.topLeft() == QPoint(500, 400)
    return widget


def test_b004_page_undo_of_move_keeps_later_change_of_another_overlay(page, monkeypatch):
    from neopedal.widget._edit_mode import edit_mode

    widget = screen_move(page, monkeypatch)
    cfg.user.setting["fuel"]["opacity"] = 0.5  # then, in game: opacity of fuel changed from its menu
    edit_mode().record("fuel", "Opacity", {"opacity": 0.9}, {"opacity": 0.5})
    page.undo()
    assert cfg.user.setting["fuel"]["opacity"] == 0.5  # was: put back to 0.9
    assert widget.rect.topLeft() == QPoint(100, 100)  # the move of the page undone
    edit_mode().history.clear()


def test_b004_page_undo_of_move_with_nothing_since(page, monkeypatch):
    from neopedal.widget._edit_mode import edit_mode

    screen_move(page, monkeypatch)
    page.undo()  # undone in edit mode history (moves the running overlay, redo kept)
    setting = cfg.user.setting["speedometer"]
    assert (setting["position_x"], setting["position_y"]) == (100, 100)
    assert edit_mode().history.peek_redo() is not None
    edit_mode().history.clear()


def test_b004_page_undo_of_move_never_undoes_later_move(page, monkeypatch):
    from neopedal.widget._edit_mode import edit_mode

    widget = screen_move(page, monkeypatch)
    widget.move_overlay(QPoint(700, 300), "Centering")  # moved again in game since
    page.undo()
    assert widget.rect.topLeft() == QPoint(700, 300)
    edit_mode().history.clear()


# B-005: friction circle (modern) drew one reference ring per G: a big Display Radius G froze the app
def test_b005_friction_circle_modern_big_radius_drawn_at_once(ui_env, bundled_fonts):
    import time

    from neopedal.ui.widget_preview import render_widget

    cfg.user.config["overlay_style"]["overlay_theme"] = "Modern Dark"
    values = dict(cfg.user.setting["friction_circle"], enable_classic_layout=False, show_reference_circle=True)
    normal = render_widget(cfg, "friction_circle", values).toImage()
    started = time.perf_counter()
    huge = render_widget(cfg, "friction_circle", dict(values, display_radius_g=1e6)).toImage()
    assert time.perf_counter() - started < 5  # was: about 50 s (one million rings & labels)
    assert not huge.isNull() and huge.size() == normal.size()
