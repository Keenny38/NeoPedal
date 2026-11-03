"""UI/UX audit 2026-11-01, lot 4 (dense pages): calculator key figures folded on short pages, lap viewer toolbar
without lasting modes (Live as a switch, Time Axis in Show), Driver Stats toolbar & View menu (export in Share,
page feature apart, colorblind colors of the app), Results list folded on narrow pages, Overlays header on narrow
pages, charts by keyboard & axis titles of the positions chart"""

import os
import re

from PySide6.QtCore import QCoreApplication

from tests.test_race_calculator import host, page  # noqa: F401  (fixtures)
from tests.test_ui_audit_2026_10_29_analysis_calc import child, click, root_of, settle

QML = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "neopedal", "ui", "qml")


def code(path: str) -> str:
    """QML text without comments"""
    with open(os.path.join(QML, path), encoding="utf-8") as file:
        return "\n".join(line.split("//")[0] for line in file.read().splitlines())


# 1. Race calculator: key figures & timeline folded by room, or as chosen
def test_calculator_overview_folds_on_short_pages(page):  # noqa: F811
    root = root_of(page)
    page.show()
    page.resize(1300, 1000)
    settle()
    figures, toggle = child(root, "keyFigures"), child(root, "overviewToggle")
    assert figures.property("visible") and toggle.property("checked")
    page.resize(1300, 420)  # short page: inputs of the tabs keep the room
    settle()
    assert root.property("shortPage") and not figures.property("visible")
    click(toggle)  # shown anyway
    assert figures.property("visible") and root.property("overviewMode") == 1
    click(toggle)  # folded again, whatever the height
    page.resize(1300, 1000)
    settle()
    assert not figures.property("visible") and root.property("overviewMode") == 2
    assert not page.ensure_view().errors()
    QCoreApplication.processEvents()


# 2. Lap viewer: lasting modes out of the toolbar
def test_lap_viewer_toolbar_without_modes():
    viewer = code("telemetry/LapViewer.qml")
    assert 'name: "liveButton"' not in viewer and 'name: "timeAxisButton"' not in viewer
    live = viewer[viewer.index('objectName: "liveSwitch"') - 60:]
    assert live.lstrip().startswith("TpSwitch {") or "TpSwitch {" in live[:80]
    assert viewer.index('objectName: "liveSwitch"') < viewer.index('objectName: "lapToolbar"')  # next to the track
    show = code("telemetry/ShowPicker.qml")
    assert 'objectName: "timeAxisSwitch"' in show and "backend.setTimeAxis(!backend.timeAxis)" in show


# 3. Driver Stats: export in Share, page feature apart from the View menu, colorblind colors of the app
def test_stats_toolbar_and_menus():
    text = code("analysis/DriverStats.qml")
    assert 'name: "exportButton"' not in text and "id: exportMenu" not in text
    share = text[text.index("id: shareMenu"):]
    share = share[:share.index("TpMenu {")]
    assert "backend.exportCsv(false)" in share and 'backend.exportHistory("json")' in share
    view = text[text.index("id: viewMenu"):]
    view = view[:view.index("id: referenceMenu")]
    assert "Colorblind Colors" not in view
    assert "Official Races to Come" not in text  # card removed: same races on Upcoming Races & the Home card


def test_stats_colorblind_follows_app_setting(ui_env):
    from neopedal.ui import set_colorblind
    from neopedal.ui.quick import stats_core

    calls = []

    class Fake(stats_core.StatsCore):  # colorblind part only: no stats read
        _released = False

        def __init__(self):  # no QObject: property & handler read on the class
            pass

        def viewer_config(self):
            return {}

        def refresh_table(self):
            calls.append("table")

    fake = Fake.__new__(Fake)
    fake.optionsChanged = type("Signal", (), {"emit": staticmethod(lambda: calls.append("options"))})()
    try:
        set_colorblind(True)
        assert stats_core.StatsCore.colorblind_colors.fget(fake)  # type: ignore[attr-defined]
        set_colorblind(False)
        assert not stats_core.StatsCore.colorblind_colors.fget(fake)  # type: ignore[attr-defined]
        stats_core.StatsCore.colorblind_changed(fake)
        assert calls == ["options", "table"]
    finally:
        set_colorblind(False)


# 4. Results list folded on narrow pages, Overlays header icons only
def test_results_list_folds_on_narrow_pages():
    text = code("analysis/RaceResults.qml")
    assert 'objectName: "listFold"' in text and "visible: !page.wide" in text
    assert "visible: page.wide || !page.listFolded" in text
    assert "page.listFolded ? listMode.implicitHeight" in text


def test_overlays_header_icons_when_narrow():
    text = code("overlays/Overlays.qml")
    assert "readonly property bool tightHeader: width < theme.bpNarrow" in text
    assert 'text: page.tightHeader ? "" : backend.presetName' in text
    assert 'text: page.tightHeader ? "" : i18n.tr("Share")' in text


# 5. Charts by keyboard, axis titles
def test_charts_by_keyboard():
    for path, name in (("telemetry/XYView.qml", "root"), ("telemetry/GCircle.qml", "circle")):
        text = code(path)
        assert "activeFocusOnTab:" in text and "Keys.onPressed" in text, path
        assert f"{name}.zoomAt(1.25" in text and f"{name}.resetZoom()" in text and "Qt.Key_Left" in text, path
        assert "FocusRing { anchors.margins: gap; z: 3; visible: plot.activeFocus }" in text, path
    positions = code("analysis/ResultsPositions.qml")
    assert "Keys.onUpPressed: pickStep(-1)" in positions and "activeFocusOnTab: true" in positions
    assert 'objectName: "placeAxisTitle"' in positions and 'objectName: "lapAxisTitle"' in positions
    assert "Other cars, in their class color" in positions
    assert not re.search(r'"P" \+|: P"', positions)  # place text translated (i18n "P%1")
