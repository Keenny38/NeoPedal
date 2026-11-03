"""Modern Grey & the four themes: what follows the window theme (offer for overlays), pages, selector"""

from PySide6.QtWidgets import QApplication, QWidget

from neopedal.setting import cfg


class FakeAppWindow(QWidget):
    """Stands for the main window: the offer looks it up by class name"""


def test_matching_overlay_theme_offered_after_window_theme_change(ui_env, monkeypatch):
    from neopedal.ui import app_settings

    window = FakeAppWindow()
    window.show()
    shown = []
    monkeypatch.setattr(app_settings, "show_toast", lambda widget, text, **kwargs: shown.append((widget, text, kwargs)))
    applied = []
    monkeypatch.setattr(app_settings, "run_after_saving", applied.append)
    cfg.application["window_color_theme"] = "Modern Grey"
    cfg.user.config["overlay_style"]["overlay_theme"] = "Modern Dark"
    try:
        app_settings.offer_matching_overlay_theme()
        assert len(shown) == 1 and shown[0][0] is window
        assert "Modern Dark" in shown[0][1] or "Moderne" in shown[0][1]
        shown[0][2]["action"]()  # button: the overlays get the window theme, saved, overlays restarted
        assert cfg.user.config["overlay_style"]["overlay_theme"] == "Modern Grey" and len(applied) == 1
        app_settings.offer_matching_overlay_theme()  # same theme now: nothing offered
        assert len(shown) == 1
    finally:
        window.close()
        window.deleteLater()
        assert QApplication.instance() is not None


def test_no_offer_without_main_window(ui_env, monkeypatch):
    from neopedal.ui import app_settings

    shown = []
    monkeypatch.setattr(app_settings, "show_toast", lambda *args, **kwargs: shown.append(args))
    cfg.application["window_color_theme"] = "Modern White"
    cfg.user.config["overlay_style"]["overlay_theme"] = "Modern Dark"
    app_settings.offer_matching_overlay_theme()
    assert shown == []


def test_theme_option_applies_offer(ui_env, monkeypatch):
    """Saving window_color_theme in Settings runs the offer after refreshing, other options do not"""
    from neopedal.ui import app_settings

    offered = []
    monkeypatch.setattr(app_settings, "offer_matching_overlay_theme", lambda: offered.append(1))
    app_settings.apply_saved_sections(["application"], ["application/language"])()
    assert offered == []
    app_settings.apply_saved_sections(["application"], ["application/window_color_theme"])()
    assert offered == [1]
