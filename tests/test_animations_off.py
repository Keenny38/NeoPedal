"""Pages with Windows "Animation effects" off (motion tokens 0, no popup transitions): GitHub Windows runners have
them off, so menus & dialogs once behaved there unlike on a desktop (post-mortem 0.28.0, P2 #14)

Without an exit transition, Popup.closed comes inside close(); without an enter transition, opened comes inside
open(), before bindings follow what made the page open it.
"""

import pytest
from PySide6.QtTest import QTest

from tests.test_ui_audit_2026_10_29_foundations import bridged, click, named, page, settle  # noqa: F401


@pytest.fixture
def animations_off(monkeypatch):
    """Motion tokens of pages built during the test are 0, as with the Windows setting off"""
    from neopedal.ui import quick

    monkeypatch.setattr(quick, "_ANIMATIONS", [False])


def test_motion_tokens_zero(animations_off, page):  # noqa: F811
    _view, root, _warnings = page("    readonly property int fast: theme.motionFast")
    assert root.property("fast") == 0


def test_menu_closed_by_second_click(animations_off, page):  # noqa: F811
    view, root, warnings = page('''
    TpButton {
        id: source; objectName: "source"; x: 100; y: 100; text: "More"
        onClicked: menu.toggleBelow(source)
    }
    TpButton { id: other; objectName: "other"; x: 300; y: 100; text: "Other"; onClicked: menu.toggleBelow(other) }
    TpMenu { id: menu; objectName: "menu"; TpMenuItem { text: "One" } }
''')
    source, other, menu = named(root, "source"), named(root, "other"), named(root, "menu")
    click(view, source)
    assert menu.property("visible")
    click(view, source)  # same button: closed, not opened again (closed came inside close())
    assert not menu.property("visible")
    click(view, source)
    assert menu.property("visible")
    click(view, other)  # another button: moved under it
    assert menu.property("visible") and menu.property("toggleSource") == other
    assert warnings == []


def test_number_dialog_focused(animations_off, bridged):  # noqa: F811
    from neopedal.ui.quick import dialogs as page_dialogs

    view, root, bridge, host = bridged
    numbers = []
    page_dialogs.ask_number(host, "Go to lap", "Lap:", numbers.append, 3, 1, 9)
    settle()
    number = named(root, "bridgeNumber")
    assert number.property("activeFocus")  # opened came before kind & visible followed the request
    QTest.keyClick(view, "\r")
    settle()
    assert numbers == [3] and bridge.pending == 0


def test_text_dialog_focused_after_number(animations_off, bridged):  # noqa: F811
    from neopedal.ui.quick import dialogs as page_dialogs

    _view, root, _bridge, host = bridged
    page_dialogs.ask_number(host, "Go to lap", "Lap:", lambda value: None, 3, 1, 9)
    settle()
    named(root, "host").accept()
    settle()
    page_dialogs.ask_text(host, "New Theme", "Theme name:", lambda text: True, "Dusk")
    settle()
    field = named(root, "bridgeField")
    assert field.property("activeFocus") and field.property("selectedText") == "Dusk"
