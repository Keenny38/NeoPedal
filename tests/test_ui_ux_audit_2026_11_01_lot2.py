"""UI/UX audit 2026-11-01, lot 2 (component consistency): tabs for views & segmented controls for filters, counts
apart from texts, lists of cards on TpListRow card, one hover per role, focus ring on TpCombo, class filter chips in
Driver Stats, Director surfaces on card tokens, no raw pixels in components"""

import os
import re

from PySide6.QtCore import QCoreApplication, QObject

from tests.test_audit_g_qml_keys import component  # noqa: F401  (fixture)
from tests.test_ui_audit_2026_10_29_overlays import children, control, overlays_page  # noqa: F401  (fixtures)

QML = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "neopedal", "ui", "qml")


def qml(path: str) -> str:
    with open(os.path.join(QML, path), encoding="utf-8") as file:
        return file.read()


def code(path: str) -> str:
    """QML text without comments"""
    return "\n".join(line.split("//")[0] for line in qml(path).splitlines())


def stack_items(root) -> list:
    found, stack = [], [root]
    while stack:
        item = stack.pop()
        found.append(item)
        stack.extend(item.childItems())
    return found


def texts_of(root) -> set:
    return {item.property("text") for item in stack_items(root) if isinstance(item.property("text"), str)}


# 1. Tabs for views, segmented for filters, counts apart from texts
def test_tab_bar_counts_and_squeeze(component):  # noqa: F811
    view = component("""
Item {
    width: 600; height: 100
    property alias bar: bar
    TpTabBar {
        id: bar
        objectName: "bar"
        width: parent.width
        model: [{ text: "Sessions", count: 12 }, { text: "Replays", count: -1 }, { text: "Third view" }]
    }
}""")
    bar = view.rootObject().findChild(QObject, "bar")
    texts = set()
    stack = [bar]
    while stack:
        item = stack.pop()
        if isinstance(item.property("text"), str):
            texts.add(item.property("text"))
        stack.extend(item.childItems())
    assert {"Sessions", "12", "Replays"} <= texts and "Sessions  12" not in texts
    buttons = [item for item in stack_items(bar) if item.property("contentWidth") is not None
               and item.property("current") is not None]
    bar.setProperty("counts", [3, 7])  # counts apart from the model: the same tab buttons, new counts
    QCoreApplication.processEvents()
    assert texts_of(bar) >= {"3", "7"} and "12" not in texts_of(bar)
    assert [item for item in stack_items(bar) if item.property("contentWidth") is not None
            and item.property("current") is not None] == buttons
    natural, minimum = bar.property("naturalWidth"), bar.property("minimumWidth")
    assert 0 < minimum < natural and not bar.property("squeezed")
    bar.setProperty("width", (natural + minimum) / 2)  # between both: tabs keep their texts, less padding
    QCoreApplication.processEvents()
    assert bar.property("squeezed")


def test_segmented_counts_apart(component):  # noqa: F811
    view = component("""
TpSegmented {
    objectName: "seg"
    options: [{ text: "All", count: 5 }, { text: "Chat", count: 0 }, "Plain"]
}""")
    seg = view.rootObject()
    texts = set()
    stack = [seg]
    while stack:
        item = stack.pop()
        if isinstance(item.property("text"), str):
            texts.add(item.property("text"))
        stack.extend(item.childItems())
    assert {"All", "5", "Chat", "0", "Plain"} <= texts
    assert seg.property("textsWidth") > 0


def test_views_use_tabs_not_glued_counts():
    for path, name in (("analysis/RaceResults.qml", "listMode"), ("analysis/RaceResults.qml", "resultTabs"),
                       ("analysis/ReplayView.qml", "replayPanels"), ("director/DirectorCommentary.qml", "commentaryTabs"),
                       ("telemetry/LapViewer.qml", "sideTabs")):
        text = code(path)
        start = text.index(f'objectName: "{name}"')
        head = text[text.rindex("{", 0, start) - 30:start]
        assert "TpTabBar" in head, (path, name)
    for path in ("analysis/RaceResults.qml", "analysis/ReplayView.qml", "analysis/ResultsEvents.qml",
                 "director/DirectorCommentary.qml"):
        assert not re.search(r'i18n\.tr\("[^"]+"\) \+ (\(.*\? )?"  " \+', code(path)), path  # "Text  12"
    for path in ("analysis/RaceResults.qml", "analysis/ReplayView.qml", "director/DirectorCommentary.qml"):
        assert "counts: [" in code(path), path  # changing counts never make the tabs again
    assert '"count": counts[1] || 0' in code("analysis/ResultsEvents.qml")  # a filter: segmented with counts


# 2. Lists of cards on TpListRow card
def test_cards_on_list_row_card():
    for path in ("overlays/OverlayCard.qml", "config/ModuleCard.qml", "config/SetupOverlays.qml",
                 "director/DirectorCommentary.qml"):
        text = code(path)
        assert re.search(r"TpListRow \{[^}]*card: true", text, re.S), path
    for path in ("overlays/OverlayCard.qml", "config/ModuleCard.qml"):
        block = code(path)[code(path).index("TpListRow {"):]
        block = block[:block.index("\n\n")]
        assert "card.hovered" not in block and "card.active" not in block, path  # "card" is TpListRow's own bool


def test_overlay_cards_render_on_list_row(overlays_page):  # noqa: F811
    quick = overlays_page.view
    assert not quick.errors(), [error.toString() for error in quick.errors()]
    surfaces = [item for item in children(quick, "") if item.metaObject().className().startswith("TpListRow")
                and item.property("card")]
    assert surfaces
    states = {bool(item.property("emphasized")) for item in surfaces}
    assert states == {True, False}  # overlays on & off told apart (control fixture: two on)


# 3. One hover per role, focus ring on TpCombo, no raw pixels in components
def test_hover_and_focus_of_controls():
    seg = code("components/TpSegmented.qml")
    assert "opacity: optionArea.containsMouse && !option.current ? 1 : 0" in seg
    combo = code("components/TpCombo.qml")
    assert "FocusRing { visible: box.visualFocus }" in combo and "border.width: box.visualFocus" not in combo
    assert combo.count("ColorDot {") == 2
    assert "implicitHeight: Math.round(theme.controlHeight)" in code("components/TpTabBar.qml")


def test_no_raw_pixel_paddings_in_components():
    folder = os.path.join(QML, "components")
    for name in os.listdir(folder):
        if name.endswith(".qml"):
            text = code(f"components/{name}")
            assert not re.search(r"\b(padding|spacing): [2-9]\d*\s*$", text, re.M), name
            assert not re.search(r"implicitHeight \+ \d+\b", text), name


# 4. Class filter of Driver Stats as chips (as on the Results page)
def test_stats_class_filter_chips():
    text = code("analysis/DriverStats.qml")
    block = text[text.index('objectName: "statsClassFilter"') - 200:]
    block = block[:block.index("StatsTable {")]
    assert "TpChip {" in block and "TpCombo" not in block
    assert "backend.setClassFilter(modelData)" in block


# 5. Director surfaces on card tokens (raised & border stay for controls)
def test_director_card_surfaces():
    assert "color: theme.surfaceCard" in code("director/DirectorSheet.qml")
    assert "theme.raised" not in code("director/DirectorSheet.qml")
    commentary = code("director/DirectorCommentary.qml")
    assert "Qt.tint(theme.raised" not in commentary and "color: theme.raised" not in commentary
    assert "color: theme.surfaceFlyout" in code("director/IncidentPanel.qml")
