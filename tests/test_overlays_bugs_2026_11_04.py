"""Overlays page & Overlay Options bugs (2026-11-04): "1 enabled overlay not running" singular, Unlock Overlays,
unlock prompt without file extension, locked preset told on switches & before Apply, empty states of the Active
choice & options filters, reset tip French, card menu Test on Screen stopping told"""

from pathlib import Path

from PySide6.QtCore import QMetaObject

from neopedal import i18n
from neopedal.setting import cfg
from tests.test_overlays_page_more import settle
from tests.test_ui_audit_2026_10_29_overlays import (  # noqa: F401  (fixtures)
    backend,
    child,
    control,
    options_page,
    overlays_page,
)

QML_FOLDER = Path(__file__).resolve().parent.parent / "neopedal" / "ui" / "qml" / "overlays"


def french(function, *args):
    i18n.set_language("Français")
    try:
        return function(*args)
    finally:
        i18n.set_language("English")


def test_screen_view_not_running_count_singular_and_unlock_overlays():
    text = (QML_FOLDER / "OverlayScreenView.qml").read_text(encoding="utf-8")
    assert '"%1 enabled overlay not running"' in text and '" enabled overlays not running")' not in text
    assert 'i18n.tr("Unlock Overlays")' in text and 'i18n.tr("Unlock Overlay")' not in text
    one = ("%1 enabled overlay not running", "%1 enabled overlays not running")
    assert i18n.plural(1, *one) == one[0] and i18n.plural(2, *one) == one[1]
    assert french(i18n.plural, 1, *one) == "%1 overlay activé non démarré"
    assert french(i18n.plural, 3, *one) == "%1 overlays activés non démarrés"
    assert french(i18n.tr, "Unlock Overlays") == "Déverrouiller les overlays"


def test_unlock_preset_prompt_names_preset_without_extension(backend, monkeypatch):  # noqa: F811
    monkeypatch.setattr(cfg.filename, "setting", "my<preset>.json")
    monkeypatch.setitem(cfg.user.filelock, "my<preset>.json", {"version": "1"})
    asked = []
    backend._confirm = lambda text: asked.append(text) or False
    backend.unlockPreset()
    assert asked == ["Unlock <b>my&lt;preset&gt;</b> preset?"]


def test_locked_preset_switches_told_not_saved(backend, monkeypatch):  # noqa: F811
    toasts = []
    monkeypatch.setattr(backend, "_toast", lambda text, undo=None: toasts.append((text, undo)))
    backend.toggle("fuel")  # preset not locked: the switch shows it, no toast
    assert toasts == [] and cfg.user.setting["fuel"]["enable"]
    monkeypatch.setitem(cfg.user.filelock, cfg.filename.setting, {"version": "1"})
    backend.toggle("fuel")
    assert toasts[-1][0] == "Overlay disabled, not saved (locked preset): Fuel" and toasts[-1][1] is not None
    told = []
    backend.bulkToggled.connect(told.append)
    backend.setSearch("brake")
    backend.disableShown()
    assert told == ["1 overlay disabled, not saved (locked preset)"] and toasts[-1][0] == told[0]
    assert french(i18n.trm, "Overlay enabled, not saved (locked preset): Carburant") == (
        "Overlay activé, non enregistré (preset verrouillé) : Carburant")
    assert french(i18n.trm, "3 overlays enabled, not saved (locked preset)") == (
        "3 overlays activés, non enregistrés (preset verrouillé)")
    assert french(i18n.trm, "1 overlay disabled, not saved (locked preset)") == (
        "1 overlay désactivé, non enregistré (preset verrouillé)")


def test_active_choice_without_enabled_overlay_says_so(overlays_page):  # noqa: F811
    quick = overlays_page.view
    page = overlays_page.backend
    page.disableShown()
    page.refresh()  # app refresh of the switch (rows follow the setting)
    page.setStateFilter(1)
    settle(5)
    assert page.activeCount == 0
    state = child(quick, "overlaysEmptyState")
    assert state.property("empty")
    assert state.property("title") == "No overlay enabled" and state.property("actionText") == "Show All"
    QMetaObject.invokeMethod(state, "action")
    settle(5)
    assert page.stateFilter == 0 and child(quick, "overlayGrid").property("count") == 5  # every overlay
    assert state.property("title") != "No overlay enabled"
    page.setSearch("no such overlay")
    settle(5)
    assert state.property("title") == "No overlay matches the filters"
    assert state.property("actionText") == "Clear Filters"


def test_card_menu_test_entry_follows_running_test(backend, monkeypatch):  # noqa: F811
    from neopedal.ui import overlay_test

    class Test:
        running = False

    test = Test()
    monkeypatch.setattr(overlay_test, "overlay_test", lambda: test)
    assert backend.testingOnScreen() is False
    test.running = True
    assert backend.testingOnScreen() is True
    text = (QML_FOLDER / "Overlays.qml").read_text(encoding="utf-8")
    assert 'cardMenu.testing ? i18n.tr("Stop Test") : i18n.tr("Test on Screen")' in text


def test_options_apply_in_locked_preset_asks_first(ui_env, monkeypatch):
    from neopedal.ui.quick.overlay_options_backend import OverlayOptionsBackend
    from tests.test_overlay_options import Control, Host

    host = Host()
    options = OverlayOptionsBackend(None, host, Control())
    try:
        options.setNumber(f"{options.overlay}/update_interval", 77)
        monkeypatch.setitem(cfg.user.filelock, cfg.filename.setting, {"version": "1"})
        host.answer = False
        assert not options.apply()
        assert options.pendingCount == 1 and options.canUndo and not host.applied_names  # edits kept
        assert "is locked" in host.questions[-1] and ".json" not in host.questions[-1]
        host.answer = True
        assert options.apply() and options.pendingCount == 0 and host.applied_names
    finally:
        options.close()
        options.deleteLater()
    name = "<b>default</b>"
    question = (f"Preset {name} is locked: changed options last until the app is closed, they are not saved."
                "<br><br>Apply them anyway?")
    assert french(i18n.trm, question).startswith("Le preset <b>default</b> est verrouillé")


def test_reset_tip_french_not_past_tense():
    assert french(i18n.trm, "Back to default: 12") == "Revenir à la valeur par défaut : 12"


def test_options_filter_empty_state_has_text(options_page):  # noqa: F811
    quick = options_page.view
    assert not quick.errors(), [error.toString() for error in quick.errors()]
    text = (QML_FOLDER / "OverlayOptions.qml").read_text(encoding="utf-8")
    assert 'page.filterCount > 0 ? i18n.tr("No option matches the filters")' in text
    assert french(i18n.tr, "No option matches the filters") == "Aucune option ne correspond aux filtres"
