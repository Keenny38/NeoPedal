"""UX bug fixes 2026-11-04: Edit Hotkeys… of the shortcuts sheet opens the Hotkeys category of Settings, setup wizard
opened again keeps the loaded preset and shows the Screen view once (saved view kept), end toast true with or without
the on-screen test, tray Reset Data confirmed by a tray message while the window is hidden, "@" alone in the command
palette shows a hint instead of Nothing found"""

from types import SimpleNamespace

import pytest
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QMessageBox, QWidget

from neopedal.i18n.fr import TRANSLATION
from neopedal.setting import cfg
from tests.test_audit_c_app import answers  # noqa: F401  (fixture)
from tests.test_perf_page_state import qml_warnings  # noqa: F401  (fixture)
from tests.test_ui_audit_2026_10_29_shell import flush, window  # noqa: F401  (fixture: main window)


@pytest.fixture
def renders(monkeypatch):
    """Overlay pictures of the wizard: small picture instead of real rendering"""
    from neopedal.ui.quick import setup_backend

    def render(name, setting, style):
        image = QImage(40, 20, QImage.Format.Format_ARGB32)
        image.fill(0xFF336699)
        return image

    monkeypatch.setattr(setup_backend, "render_overlay", render)


# 1. Shortcuts sheet: Edit Hotkeys… (Hotkeys page merged into Settings 2026-11-03)
def test_shortcuts_edit_hotkeys_opens_settings_category(window):  # noqa: F811
    from neopedal.ui.app_settings import AppSettings
    from neopedal.ui.quick.shell_shortcuts_backend import ShortcutsBackend

    window.show()
    backend = ShortcutsBackend(window)
    closed = []
    backend.closeRequested.connect(lambda: closed.append(True))
    backend.openHotkeys()  # was KeyError: "hotkey" no longer a main page
    flush()
    settings = window.centralWidget().current_page().dialog
    assert closed and isinstance(settings, AppSettings) and settings.backend.category == "hotkeys"


# 2. Setup wizard opened again: loaded preset kept (first run: new preset proposed)
def test_wizard_opened_again_keeps_loaded_preset(ui_env, renders, monkeypatch):
    from neopedal.ui import setup_wizard
    from neopedal.ui.quick import setup_backend

    monkeypatch.setattr(cfg.filename, "setting", "default.json")
    backend = setup_backend.SetupBackend(detect_games=False)
    try:
        assert not backend.newPreset and backend.nameError == ""
        choices = backend.choices()
        assert choices.new_preset == "" and choices.preset == "default.json"
        created = []
        monkeypatch.setattr(type(cfg), "create", lambda self, filename: created.append(filename))
        assert setup_wizard.apply_global_choices(choices) == ""  # loaded preset: nothing created, no preset load
        assert created == []
    finally:
        backend.stop_previews()
        backend.deleteLater()
    first = setup_backend.SetupBackend(detect_games=False, first_run=True)
    try:
        assert first.newPreset and first.choices().new_preset == "my overlay"
    finally:
        first.stop_previews()
        first.deleteLater()
    flush()


def test_wizard_first_run_only_from_first_launch(window, monkeypatch):  # noqa: F811
    from neopedal.ui import setup_wizard
    from neopedal.ui.menu import HelpMenu

    opened = []

    class Wizard:
        def __init__(self, parent, detect_games=True, first_run=False):
            opened.append(first_run)

        def open(self):
            pass

    monkeypatch.setattr(setup_wizard, "SetupWizard", Wizard)
    window.open_setup_wizard()  # first launch
    HelpMenu.show_setup_wizard(SimpleNamespace(_parent=window))  # Help > Setup Wizard
    assert opened == [True, False]


# 3. Screen view shown once, saved view unchanged
def test_wizard_screen_view_once_keeps_saved_view(window, monkeypatch):  # noqa: F811
    from neopedal.ui import setup_wizard
    from neopedal.ui.nav_rail import PAGE_INDEX
    from neopedal.ui.overlay_view import OverlayView
    from neopedal.ui.quick.overlay_backend import VIEW_LIST, VIEW_SCREEN, OverlayBackend

    monkeypatch.setattr(OverlayBackend, "view_once", None)  # restored after the test
    cfg.application["show_overlay_screen_view"] = False
    cfg.application["show_overlay_previews"] = False
    window.show()
    window.centralWidget().select_page(PAGE_INDEX["widget"])  # page built before
    backend = window.findChild(OverlayView).backend
    assert backend._view == VIEW_LIST
    setup_wizard.show_overlays_page(window, True)
    assert backend._view == VIEW_SCREEN and cfg.application["show_overlay_screen_view"] is False
    backend.follow_saved_view()  # refresh (or page rebuilt for a new language): still Screen view
    assert backend._view == VIEW_SCREEN and OverlayBackend._saved_view() == VIEW_SCREEN
    backend.setViewMode(VIEW_SCREEN)  # picked by the user: saved from now on
    assert cfg.application["show_overlay_screen_view"] is True and OverlayBackend.view_once is None
    backend.setViewMode(VIEW_LIST)
    assert backend._view == VIEW_LIST and cfg.application["show_overlay_screen_view"] is False


def test_wizard_choices_never_save_screen_view(ui_env):
    from neopedal.ui import setup_wizard

    cfg.application["show_overlay_screen_view"] = False
    choices = setup_wizard.SetupChoices(
        language="English", api_name="", window_theme="Modern Dark", overlay_theme="Modern Dark",
        modern_font=True, preset="", new_preset="", widgets=(), open_screen_view=True)
    setup_wizard.apply_global_choices(choices)
    assert cfg.application["show_overlay_screen_view"] is False


# 4. End toast true with or without the on-screen test
def test_wizard_end_toast(ui_env, renders, monkeypatch):
    from neopedal.ui import setup_wizard, toast

    monkeypatch.setattr(setup_wizard, "run_setup", lambda choices, done=None: None)
    toasts = []
    monkeypatch.setattr(toast, "show_toast", lambda parent, text, *args, **kwargs: toasts.append(text))
    parent = QWidget()
    try:
        wizard = setup_wizard.SetupWizard(parent, detect_games=False)
        wizard.backend.setOpenScreenView(False)
        wizard.accept()
        text = "Setup complete. Enabled overlays show on screen while you drive."
        assert toasts == [text] and text in TRANSLATION
    finally:
        parent.deleteLater()
        flush()


# 5. Tray Reset Data: tray message while the window is hidden or minimized, toast while shown
def test_reset_data_confirmed_in_tray_when_hidden(ui_env, monkeypatch, tmp_path, answers):  # noqa: F811
    from neopedal.ui import menu, notification

    answers.reply = QMessageBox.StandardButton.Yes
    messages, toasts = [], []
    shown = [True]
    monkeypatch.setattr(notification, "tray_message",
                        lambda text, *args, **kwargs: messages.append((text, kwargs.get("window"))) or shown[0])
    monkeypatch.setattr(menu, "show_toast", lambda parent, text, *args, **kwargs: toasts.append(text))
    parent = QWidget()
    reset = menu.ResetDataMenu("Reset", parent)

    def reset_map() -> bool:
        (tmp_path / "Spa.svg").write_text("x", encoding="utf-8")
        return reset._ResetDataMenu__confirmation(  # type: ignore[attr-defined]
            data_type="track map", extension="svg", filepath=f"{tmp_path}/", filename="Spa")

    try:
        assert reset_map()  # window hidden (tray menu)
        assert messages == [("Track map data has been reset for\nSpa", parent)] and toasts == []
        shown[0] = False  # no tray icon: toast kept
        assert reset_map()
        assert len(toasts) == 1
        parent.show()
        assert reset_map()  # window shown: toast only
        assert len(messages) == 2 and len(toasts) == 2 and "<b>Spa</b>" in toasts[-1]
    finally:
        parent.hide()
        reset.deleteLater()
        parent.deleteLater()
        flush()


# 6. Command palette: option prefix alone shows a hint
def test_palette_option_prefix_alone_shows_hint(window, qml_warnings):  # noqa: F811
    from neopedal.ui.command_palette import CommandPalette

    palette = CommandPalette(window)
    flush()
    backend = palette.backend
    assert not backend.optionPrompt
    palette.set_search("@")
    assert backend.results == [] and backend.optionPrompt
    palette.set_search("@zzzzqqq")  # name typed, nothing found: usual empty state
    assert backend.results == [] and not backend.optionPrompt
    palette.set_search(" @ ")
    assert backend.optionPrompt
    palette.set_search("@font color")
    assert backend.results and not backend.optionPrompt
    flush()
    palette.close()
    assert "Type an option name" in TRANSLATION and "Options show as you type." in TRANSLATION
    assert not [warning for warning in qml_warnings if "CommandPalette" in warning]
