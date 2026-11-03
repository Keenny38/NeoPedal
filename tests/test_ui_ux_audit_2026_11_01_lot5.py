"""UI/UX audit 2026-11-01, lot 5 (typography & shared table): TpText in the components & audited pages, ratchet on
raw Text, TpTable for the tables of Results & the Team tab, column titles on the stints card"""

import os
import re

from PySide6.QtCore import QCoreApplication, QObject, Qt
from PySide6.QtTest import QTest

from tests.test_audit_g_qml_keys import component  # noqa: F401  (fixture)

QML = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "neopedal", "ui", "qml")
RAW_TEXT = re.compile(r"(^\s*|[:{;]\s*)Text \{", re.M)
# Components drawing glyphs or letters at pixel sizes keep a raw Text (TpText sizes come from its role)
# (TpToolTip: its text takes the whole font of the tooltip control, TpText sets the font part by part)
RAW_TEXT_COMPONENTS = {"Icon.qml", "TpText.qml", "TpLetterBadge.qml", "TpClassBadge.qml", "TpIconTile.qml",
                       "TpToolTip.qml"}
# Raw Text left in pages: chart labels & cells of big lists (TpText adds two bindings per item, made by thousands
# there). Lower when converting some, never raise
RAW_TEXTS = 637


def qml(path: str) -> str:
    with open(os.path.join(QML, path), encoding="utf-8") as file:
        return file.read()


def code(path: str) -> str:
    return "\n".join(line.split("//")[0] for line in qml(path).splitlines())


def all_files() -> list[str]:
    found = []
    for folder, _, names in os.walk(QML):
        found += [os.path.relpath(os.path.join(folder, name), QML) for name in names if name.endswith(".qml")]
    return sorted(found)


# 1. Typography
def test_components_use_tptext():
    for name in os.listdir(os.path.join(QML, "components")):
        if name.endswith(".qml") and name not in RAW_TEXT_COMPONENTS:
            assert not RAW_TEXT.search(code(f"components/{name}")), name
    dialog = code("components/TpDialog.qml")
    assert 'role: "title"' in dialog  # dialog titles in the display face, told as headings


def test_raw_text_does_not_grow():
    count = sum(len(RAW_TEXT.findall(code(path))) for path in all_files() if not path.startswith("components"))
    assert count <= RAW_TEXTS, count


def test_audited_pages_use_tptext():
    for path in ("analysis/DriverStats.qml", "analysis/StatsDriverCard.qml", "analysis/StatsReferenceCard.qml"):
        text = code(path)
        assert len(RAW_TEXT.findall(text)) <= 3, (path, len(RAW_TEXT.findall(text)))  # left: texts that may hold markup


# 2. Shared table
def test_tables_on_tptable():
    for path, name in (("analysis/ResultsTable.qml", "classification"), ("analysis/ResultsLaps.qml", "lapList"),
                       ("analysis/RaceTeamTab.qml", "teamStints"), ("analysis/RaceTeamTab.qml", "stintPlanList")):
        text = code(path)
        start = text.index(f'listName: "{name}"')
        assert "TpTable {" in text[text.rindex("TpTable {", 0, start):start], (path, name)
    for path in ("analysis/ResultsTable.qml", "analysis/ResultsLaps.qml"):
        assert "flickableDirection: Flickable.HorizontalFlick" not in code(path), path  # TpTable's scroll
    assert 'text: "±"' in code("analysis/ResultsTable.qml")  # places gained: never an empty title


def test_stints_card_column_titles():
    text = code("analysis/DriverStats.qml")
    card = text[text.index("Stints & Consistency"):]
    assert card.count("TpHeaderCell {") >= 12
    assert 'i18n.tr("Per lap")' in card and "Lap time change per lap: + slower each lap" in card


def test_tptable_keyboard_and_scroll(component):  # noqa: F811
    view = component("""
Item {
    width: 300; height: 200
    property int picked: -1
    property int activated: -1
    TpTable {
        id: table
        objectName: "table"
        anchors.fill: parent
        rowWidth: 900  // wider than the view (600 px)
        model: 20
        TpHeaderCell { width: 450; text: "First" }
        TpHeaderCell { width: 450; text: "Second"; align: Qt.AlignRight }
        delegate: Item { required property int index; width: table.rowWidth; height: 24 }
        onPicked: function(index) { parent.picked = index }
        onActivated: function(index) { parent.activated = index }
    }
}""")
    root = view.rootObject()
    table = root.findChild(QObject, "table")
    flick = next(item for item in table.childItems() if item.metaObject().className().startswith("QQuickFlickable"))
    assert flick.property("interactive")  # rows wider than the table: sideways scroll
    found, stack = [], [table]
    while stack:
        item = stack.pop()
        if item.metaObject().className().startswith("QQuickListView"):
            found.append(item)
        stack.extend(item.childItems())
    rows = found[0]  # the rows' ListView (table.list: no Python converter for its type)
    rows.forceActiveFocus()
    QCoreApplication.processEvents()
    for key, expected in ((Qt.Key.Key_Down, 0), (Qt.Key.Key_Down, 1), (Qt.Key.Key_End, 19), (Qt.Key.Key_Home, 0),
                          (Qt.Key.Key_PageDown, None)):
        QTest.keyClick(view, key)
        QCoreApplication.processEvents()
        if expected is not None:
            assert root.property("picked") == expected, key
    assert root.property("picked") >= 1  # a page of rows down (one row in this small view)
    QTest.keyClick(view, Qt.Key.Key_Return)
    assert root.property("activated") == root.property("picked")
