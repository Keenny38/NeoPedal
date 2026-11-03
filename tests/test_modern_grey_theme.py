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


def test_theme_data_is_the_single_source():
    """Four themes with the same palette roles, read by the window palettes, overlay tables & theme names"""
    from neopedal import regex_pattern, theme_data
    from neopedal.ui import palette_dark, palette_grey, palette_legacy_grey, palette_light, window_palette
    from neopedal.widget import _style

    assert regex_pattern.THEME_NAMES == theme_data.THEME_NAMES == tuple(theme_data.WINDOW_PALETTES)
    roles = {name: tuple(rows) for name, rows in theme_data.WINDOW_PALETTES.items()}
    assert len(set(roles.values())) == 1 and len(next(iter(roles.values()))) == 20
    for name, function in (("Modern Dark", palette_dark), ("Modern Grey", palette_grey),
                           ("Modern White", palette_light), ("Legacy Grey", palette_legacy_grey)):
        assert function() == window_palette(name)
    assert window_palette("Modern Light") == window_palette("Modern Dark")  # unknown name: the default
    assert _style.MODERN_PALETTE is theme_data.MODERN_PALETTE and _style.MODERN_GREY_NEUTRALS is theme_data.MODERN_GREY_NEUTRALS


def test_style_sheet_kept_per_theme(ui_env, monkeypatch):
    """Same theme, font size & look: the style sheet is built once; another palette builds its own"""
    from neopedal import ui
    from neopedal.ui import set_style_palette, set_style_window

    built = []
    original = ui.build_style_window
    monkeypatch.setattr(ui, "build_style_window", lambda size: built.append(size) or original(size))
    ui._STYLE_SHEETS.clear()
    try:
        set_style_palette("Modern Grey")
        first = set_style_window(9)
        assert set_style_window(9) is first and built == [9]
        set_style_palette("Modern White")
        white = set_style_window(9)
        assert white != first and len(built) == 2
        set_style_palette("Modern Dark")
        set_style_palette("Modern Grey")
        assert set_style_window(9) == first  # content of the former sheet, whether kept or built again
    finally:
        set_style_palette("Modern Dark")
        ui._STYLE_SHEETS.clear()


def test_old_config_theme_names_through_the_validator():
    """A config.json saved by an older version (or imported from its settings folder) with former theme names:
    renamed once while loading, an unknown name afterwards falls back to the default theme"""
    from neopedal import setting_validator, version
    from neopedal.template.setting_global import GLOBAL_DEFAULT
    from neopedal.userfile.json_setting import copy_setting

    default = copy_setting(GLOBAL_DEFAULT)
    for old_version in ("2.50.9", "2.51.11"):
        for before, after in (("Modern Light", "Modern White"), ("Legacy Dark", "Legacy Grey"),
                              ("Legacy Light", "Legacy Grey"), ("Modern Dark", "Modern Dark")):
            old = copy_setting(default)
            old["preset"]["version"] = old_version
            old["application"]["window_color_theme"] = before
            old["overlay_style"]["overlay_theme"] = before
            updated = setting_validator.PresetValidator.global_preset(old, default)
            assert updated["application"]["window_color_theme"] == after, (old_version, before)
            assert updated["overlay_style"]["overlay_theme"] == after, (old_version, before)
            assert updated["preset"]["version"] == version.SETTING_VERSION
    current = copy_setting(default)
    current["application"]["window_color_theme"] = "Modern Light"  # written by hand after the update
    current["overlay_style"]["overlay_theme"] = "Legacy Dark"
    fixed = setting_validator.PresetValidator.global_preset(current, default)
    assert fixed["application"]["window_color_theme"] == default["application"]["window_color_theme"]
    assert fixed["overlay_style"]["overlay_theme"] == default["overlay_style"]["overlay_theme"]
