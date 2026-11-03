"""UI/UX audit 2026-11-01, lot 6 (left from lots 4 & 5): progression chart of Driver Stats by keyboard, Driver Stats
table on the shared TpTable (titles, sideways scroll, keyboard picking, Tab stop)"""

import os

from PySide6.QtCore import QCoreApplication, QObject, Qt, qInstallMessageHandler
from PySide6.QtTest import QTest

from tests.test_audit_g_qml_keys import component  # noqa: F401  (fixture)
from tests.test_audit_g_qml_pages import item_named, item_of_type, items_of, objects_of_type, pump, wait_until
from tests.test_driver_stats_viewer import OREGA, SPA, dialogs, page, settle  # noqa: F401  (fixtures)

QML = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "neopedal", "ui", "qml")


def code(path: str) -> str:
    """QML text without comments"""
    with open(os.path.join(QML, path), encoding="utf-8") as file:
        return "\n".join(line.split("//")[0] for line in file.read().splitlines())


# 1. Progression chart by keyboard
CHART = """
Item {
    width: 600; height: 300
    property int clicked: -2
    StatsChart {
        id: chart
        objectName: "chart"
        anchors.fill: parent
        chartData: ({ "points": [%s], "ticks": [], "limits": [], "dates": [], "pbY": 0.2, "top": "1:29" })
        onPointClicked: function(session) { parent.clicked = session }
    }
}"""


def chart_points(count: int) -> str:
    return ", ".join(f'{{ "x": {index / max(count - 1, 1)}, "y": 0.5, "pbY": 0.2, "session": {index * 10}, '
                     f'"tip": "Session {index}" }}' for index in range(count))


def test_stats_chart_by_keyboard(component):  # noqa: F811
    view = component(CHART % chart_points(10))
    root = view.rootObject()
    chart = root.findChild(QObject, "chart")
    ring = root.findChild(QObject, "statsChartFocus")
    assert chart.property("activeFocusOnTab") and not ring.property("visible")
    chart.forceActiveFocus()
    QCoreApplication.processEvents()
    assert ring.property("visible")  # focus shown on the chart

    def press(key, modifier=Qt.KeyboardModifier.NoModifier):
        QTest.keyClick(view, key, modifier)
        QCoreApplication.processEvents()
        return chart.property("hovered")

    assert press(Qt.Key.Key_Right) == 0  # nothing shown yet: first session
    assert press(Qt.Key.Key_Right) == 1
    assert press(Qt.Key.Key_End) == 9
    assert press(Qt.Key.Key_Right) == 9  # past the end: stays on the last
    assert press(Qt.Key.Key_Left) == 8
    assert press(Qt.Key.Key_Home) == 0
    assert press(Qt.Key.Key_Left) == 0
    assert press(Qt.Key.Key_Left, Qt.KeyboardModifier.AltModifier) == 0  # Alt+Left: page key (back), not taken
    QTest.keyClick(view, Qt.Key.Key_Right)
    QTest.keyClick(view, Qt.Key.Key_Return)  # as a click: session of the point shown
    assert root.property("clicked") == 10
    chart.setProperty("hovered", -1)
    chart.setProperty("linkedPoint", 4)  # session hovered in the sessions list: arrows go on from it
    assert press(Qt.Key.Key_Right) == 5
    QTest.keyClick(view, Qt.Key.Key_Enter)
    assert root.property("clicked") == 50
    root.forceActiveFocus()  # focus gone: keyboard readout hidden
    QCoreApplication.processEvents()
    assert chart.property("hovered") == -1 and not ring.property("visible")


def test_stats_chart_without_data_skipped_by_tab(component):  # noqa: F811
    view = component(CHART % chart_points(1))  # no chart drawn under 2 sessions
    assert not view.rootObject().findChild(QObject, "chart").property("activeFocusOnTab")
    text = code("analysis/StatsChart.qml")
    assert "Accessible.description:" in text and "Keys.onPressed" in text


# 2. Driver Stats table on TpTable
def test_stats_table_on_tptable():
    text = code("analysis/StatsTable.qml")
    start = text.index('listName: "statsList"')
    assert "TpTable {" in text[text.rindex("TpTable {", 0, start):start]
    assert "flickableDirection" not in text and "header:" not in text  # TpTable's scroll & titles
    assert "headerPositioning" not in text and "ListView {" not in text
    for kept in ("backend.sortBy(headerCell.modelData.key)", "backend.setColumnWidth(", "table.headerMenu(",
                 "table.cellMenu(", "backend.openRow(", "backend.deleteSelected()", "backend.showAllTracks()",
                 "table.openSelectedMenu()", "backend.moveSelection(", "switchFade.restart()",
                 "move: Transition", "moveDisplaced: Transition", "displaced: Transition", "populate: Transition"):
        assert kept in text, kept
    tptable = code("components/TpTable.qml")
    for alias in ("move", "moveDisplaced", "displaced", "populate"):
        assert f"property alias {alias}: list.{alias}" in tptable, alias


def test_stats_table_keyboard_on_page(page):  # noqa: F811
    messages = []
    previous = qInstallMessageHandler(lambda mode, context, text: messages.append(text))
    try:
        page.resize(1400, 860)
        page.show()
        pump(0.1)
        backend = page.backend
        root = page.view.rootObject()
        table = item_of_type(root, "StatsTable")
        rows = item_named(root, "statsList")
        assert wait_until(lambda: rows.property("activeFocus"))  # list focused in the table's scope
        assert table.property("activeFocus")
        assert rows.property("activeFocusOnTab")  # one Tab stop
        # Column titles: one per shown column, over the rows
        titles = [item for item in items_of(table) if "TpHeaderCell" in item.metaObject().className()]
        assert len(titles) == len(backend.columns)
        assert rows.property("y") >= table.property("rowHeight")
        assert table.property("neededHeight") >= rows.property("y") + table.property("rowHeight") * 2
        keys = backend.row_keys()
        assert len(keys) == 2
        backend.selectRow(keys[0])
        pump()
        assert rows.property("currentIndex") == 0
        for key, expected in ((Qt.Key.Key_Down, 1), (Qt.Key.Key_Down, 1), (Qt.Key.Key_Home, 0),
                              (Qt.Key.Key_End, 1), (Qt.Key.Key_Up, 0)):
            QTest.keyClick(page.view, key)
            pump()
            assert backend.selectedKey == keys[expected], key
            assert rows.property("currentIndex") == expected, key
        backend.sortBy("pb")  # rows moved: current row follows the selection
        pump(0.1)
        assert rows.property("currentIndex") == backend.selectedIndex == backend.row_keys().index(keys[0])
        backend.selectTrack("")  # All Tracks: Enter opens the track picked, Backspace comes back
        pump(0.1)
        backend.selectRow("Monza")
        pump()
        assert rows.property("currentIndex") == backend.selectedIndex
        QTest.keyClick(page.view, Qt.Key.Key_Return)
        pump(0.1)
        assert not backend.allTracks and backend.currentTrack == "Monza"
        QTest.keyClick(page.view, Qt.Key.Key_Backspace)
        pump(0.1)
        assert backend.allTracks
        backend.selectTrack(SPA)
        pump(0.1)
        # Keys left by the rows' list reach the table: Menu opens the row menu, Delete removes the row
        menus = [menu for menu in objects_of_type(root, "TpMenu") if "TpMenuItem" not in menu.metaObject().className()]
        QTest.keyClick(page.view, Qt.Key.Key_Menu)
        assert wait_until(lambda: any(menu.property("opened") for menu in menus))
        QTest.keyClick(page.view, Qt.Key.Key_Escape)
        assert wait_until(lambda: not any(menu.property("opened") for menu in menus))
        assert wait_until(lambda: rows.property("activeFocus"))
        removed = backend.selectedKey
        QTest.keyClick(page.view, Qt.Key.Key_Delete)
        settle(backend)
        assert removed not in backend.stats_temp[SPA]
        backend.undo()
        settle(backend)
        assert removed in backend.stats_temp[SPA]
        page.resize(640, 860)  # narrow page: rows scroll sideways under their titles
        pump(0.2)
        flick = next(item for item in items_of(table)  # TpTable's sideways scroll (the list: QQuickListView)
                     if item.metaObject().className().startswith("QQuickFlickable"))
        assert flick.property("contentWidth") >= table.property("totalWidth")
        assert flick.property("interactive") == (flick.property("contentWidth") > flick.property("width"))
        page.resize(1400, 860)
        pump(0.1)
        assert backend.selectedKey in (OREGA, "Hyper - Ferrari")
    finally:
        qInstallMessageHandler(previous)
    assert not [text for text in messages if ".qml" in text], messages
