"""UI/UX audit 2026-11-01, lot 1 (quick wins): overlay descriptions shown without hovering (Overlays cards & setup
wizard tiles), reset of pending options without question (Undo in the notice), focus rings of Overlay Options lists,
field help on keyboard focus, Director modes explained, on / off switches, page error with Try Again, toast held
while its button has focus"""

import os
import re

from PySide6.QtCore import QCoreApplication, QEvent, QObject
from PySide6.QtWidgets import QPushButton, QStackedWidget, QWidget

from neopedal.i18n.fr import TRANSLATION
from tests.test_broadcast_director import director_page  # noqa: F401  (fixture)
from tests.test_ui_audit_2026_10_29_overlays import children, control, overlays_page  # noqa: F401  (fixtures)

QML = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "neopedal", "ui", "qml")


def qml(path: str) -> str:
    with open(os.path.join(QML, path), encoding="utf-8") as file:
        return file.read()


def flush():
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    QCoreApplication.processEvents()


# 1. Descriptions without hovering
def test_overlay_cards_show_their_description(overlays_page):  # noqa: F811
    quick = overlays_page.view
    assert not quick.errors(), [error.toString() for error in quick.errors()]
    texts = [item for item in children(quick, "cardDescription") if item.property("visible")]
    assert texts, "no description shown on the cards"
    for item in texts:
        assert item.property("text") and item.property("maximumLineCount") == 2
        # Inside its card: never drawn over the next row of the grid
        card = item.parentItem()
        while card is not None and card.property("current") is None:
            card = card.parentItem()
        assert card is not None
        bottom = item.mapToItem(card, 0, item.property("height")).y()
        assert bottom <= card.property("height"), (bottom, card.property("height"))


def test_overlay_card_switch_names_the_overlay():
    text = qml("overlays/OverlayCard.qml")
    assert 'i18n.tr("Disable %1")' in text and 'i18n.tr("Enable %1")' in text and ".arg(card.label)" in text
    assert TRANSLATION["Enable %1"] == "Activer %1" and TRANSLATION["Disable %1"] == "Désactiver %1"


def test_setup_wizard_tiles_describe_overlays(ui_env, monkeypatch):
    from PySide6.QtGui import QImage

    from neopedal import i18n
    from neopedal.ui.quick import setup_backend

    def render(name, setting, style):
        image = QImage(40, 20, QImage.Format.Format_ARGB32)
        image.fill(0xFF336699)
        return image

    monkeypatch.setattr(setup_backend, "render_overlay", render)
    backend = setup_backend.SetupBackend(detect_games=False)
    try:
        rows = {row["key"]: row for row in backend.tiles.rows}
        assert rows["relative"]["description"] == "Cars just ahead and behind you on track, with gaps."
        assert "description" in setup_backend.TILE_ROLES
        backend.setLanguage("Français")  # wizard language: description follows
        rows = {row["key"]: row for row in backend.tiles.rows}
        assert rows["relative"]["description"].startswith("Voitures juste devant")
    finally:
        backend.stop_previews()
        backend.deleteLater()
        i18n.set_language("English")
        flush()
    text = qml("config/SetupOverlays.qml")
    assert 'objectName: "tileDescription"' in text and "Accessible.description: description" in text


# 2. Reset of pending options: no "Save Button" that doesn't exist
def test_no_save_button_named_on_qml_pages():
    for folder in ("overlays", "config"):
        for name in os.listdir(os.path.join(QML, folder)):
            if name.endswith(".qml"):
                assert "Apply or Save" not in qml(f"{folder}/{name}"), name
    root = os.path.dirname(QML)
    for name in ("quick/settings_backend.py", "quick/overlay_options_backend.py"):
        with open(os.path.join(root, name), encoding="utf-8") as file:
            assert "Save Button" not in file.read(), name


def test_reset_notice_translated():
    from neopedal import i18n

    i18n.set_language("Français")
    try:
        text = i18n.trm("<b>Units</b> options reset to default, saved with Apply")
    finally:
        i18n.set_language("English")
    assert text == "Options <b>Units</b> remises par défaut, à enregistrer avec Appliquer"


# 3. Focus rings of Overlay Options lists
def test_overlay_options_lists_have_focus_rings():
    text = qml("overlays/OverlayOptions.qml")
    assert "FocusRing { anchors.margins: gap; visible: nav.activeFocus && backend.overlay === entry.key }" in text
    assert 'objectName: "optionsFocusRing"' in text and "list.activeFocus && list.keyboardFocus" in text


# 4. Field help on keyboard focus
def test_number_field_help_on_keyboard_focus():
    text = qml("components/NumberField.qml")
    assert "keyboardTip = activeFocus && (focusReason === Qt.TabFocusReason" in text
    assert "onTextEdited: keyboardTip = false" in text
    assert "|| (keyboardTip && (tip !== \"\" || rangeText !== \"\"))" in text


# 5. Director modes explained, switches for on / off
def test_director_modes_explained():
    text = qml("director/BroadcastDirector.qml")
    modes = re.search(r"options: \[\n(.*?)\n\s*\]", text, re.S)
    assert modes and modes[1].count("tip: i18n.tr(") == 3
    desk = qml("director/DirectorDesk.qml")
    block = desk[desk.index('objectName: "modeExplanation"'):]
    block = block[:block.index("wrapMode")]
    assert "visible:" not in block  # every mode
    assert 'desk.mode === "auto"' in block and "Assisted mode:" in block
    for key in ("You cut alone: pick the car and the camera",
                "The director cuts to the best story by itself",
                "Try Again"):
        assert key in TRANSLATION


def test_director_on_off_is_a_switch(director_page):  # noqa: F811
    page = director_page
    root = page.view.rootObject()
    switch = root.findChild(QObject, "enabledSwitch")
    assert switch is not None and switch.metaObject().className().startswith("TpSwitch")
    options = root.findChild(QObject, "modeSwitch").property("options")
    options = options.toVariant() if hasattr(options, "toVariant") else options
    assert len(options) == 3 and all(option["tip"] for option in options)
    assert not page.view.errors(), [error.toString() for error in page.view.errors()]


def test_calculator_on_off_is_a_switch():
    text = qml("analysis/RaceCalculator.qml")
    block = text[text.index('objectName: "gameDataSwitch"') - 300:text.index('objectName: "gameDataSwitch"')]
    assert "TpSwitch {" in block
    assert 'name: "gameDataSwitch"' not in text  # no longer a toolbar action


# 6. Error states never a dead end
def test_state_view_keeps_actions_in_error():
    text = qml("components/TpStateView.qml")
    assert "actionText: view.actionText" in text and 'view.error ? "" : view.actionText' not in text


def test_lazy_page_failure_offers_try_again(ui_env):
    from neopedal.ui.lazy_page import LazyPage

    calls = []

    def factory(parent):
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("broken page module")
        return QWidget(parent)

    stack = QStackedWidget()
    page = LazyPage(stack, factory)
    stack.addWidget(page)
    try:
        stack.show()
        QCoreApplication.processEvents()
        assert page.build_failed()
        retry = page.findChild(QPushButton, "retryButton")
        log = page.findChild(QPushButton, "viewLogButton")
        assert retry is not None and retry.isVisible() and log is not None and log.isVisible()
        retry.click()
        assert page.page is not None and not page.build_failed() and calls == [1, 1]
        assert not retry.isVisible() and not page._placeholder.isVisible()
    finally:
        stack.deleteLater()
        flush()


# 7. Toast held while its button has keyboard focus
def test_toast_held_by_focused_button():
    text = qml("components/TpToast.qml")
    assert "readonly property bool held: hover.hovered || actionButton.activeFocus" in text
    assert "onHeldChanged" in text
