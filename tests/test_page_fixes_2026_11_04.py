"""Page fixes 2026-11-04: Home debrief without a valid lap & lap count in the plural rule, rank refresh offered only
while the game runs; Upcoming Races details telling why they were not read, co-op tab without class chips, timeline
footnote without a color name & empty state; Lap viewer lost-corner stepper; shared laps dropped on the app"""

import os

from PySide6.QtCore import QCoreApplication, QEvent

from neopedal import i18n
from neopedal.ui import home_debrief
from tests.test_audit_g_qml_pages import item_named, items_of, pump
from tests.test_home_2026_11_03 import publish_cards
from tests.test_lap_viewer import wait_loaded
from tests.test_lap_viewer_features import laps  # noqa: F401
from tests.test_lap_viewer_fix_qml import named, opener, warnings  # noqa: F401
from tests.test_perf_page_state import qml_warnings  # noqa: F401
from tests.test_race_schedule import fresh_info, page  # noqa: F401
from tests.test_session_debrief import record
from tests.test_ui_audit_2026_10_29_home import home  # noqa: F401
from tests.test_ui_audit_2026_10_29_telemetry import chart_of, shown_slower_lap


# --- Home
def test_debrief_without_valid_lap_says_so(qml_warnings, home):  # noqa: F811
    root = home.view.rootObject()
    publish_cards(home.backend, {"best": "", "track": "Spa", "figures": ["3 laps"], "tips": [], "laps": [],
                                 "canOpen": False})
    pump(0.2)
    best = item_named(root, "debriefBest")
    assert best.property("text") == "No valid lap" and best.property("role") == "body"  # never the track name
    publish_cards(home.backend, {"best": "1:30.000", "track": "Spa", "figures": ["3 laps"], "tips": [], "laps": [],
                                 "canOpen": False})
    pump(0.1)
    assert best.property("text") == "1:30.000" and best.property("role") == "display"
    assert not qml_warnings, qml_warnings


def test_debrief_lap_count_singular_and_plural(ui_env):
    from neopedal.userfile.session_debrief import build_debrief

    def first_figure(valid: int) -> str:
        debrief = build_debrief(record(best=0.0, valid=valid, invalid=0), [], "")
        card = home_debrief.debrief_card(home_debrief.DebriefData(debrief, [], None))
        assert card["best"] == ""
        return card["figures"][0]

    assert (first_figure(1), first_figure(2)) == ("1 lap", "2 laps")
    i18n.set_language("Français")
    try:
        assert (first_figure(1), first_figure(2)) == ("1 tour", "2 tours")
        assert i18n.tr("No valid lap") == "Aucun tour valide"
    finally:
        i18n.set_language("English")


def test_timeline_empty_state_and_footnote(qml_warnings, page, monkeypatch):  # noqa: F811
    backend = page.backend
    backend.setView(2)
    pump(0.2)
    root = page.view.rootObject()
    timeline = item_named(root, "raceTimeline")
    assert timeline.isVisible()
    texts = [item.property("text") for item in items_of(timeline) if isinstance(item.property("text"), str)]
    assert any("Click a race for its menu" in text for text in texts)
    backend.setSearch("no race has this name")
    pump(0.2)
    assert backend.count == 0 and not timeline.isVisible()
    states = [item for item in items_of(root) if "TpStateView" in item.metaObject().className() and item.isVisible()]
    assert [state.property("title") for state in states] == ["No daily race to come"]
    assert states[0].property("text") == "No race matches the filters."
    # Centered in the shown room of its pane, not on the empty content (top half was cut off)
    pane = states[0].parentItem()
    assert pane.objectName() == "racePane"
    top = states[0].mapToItem(pane, 0, 0).y()
    assert top >= 0 and abs(top + states[0].height() / 2 - pane.height() / 2) < 2
    backend.setSearch("")
    pump(0.2)
    assert timeline.isVisible()
    QCoreApplication.processEvents()
    assert not qml_warnings, qml_warnings


# --- Lap Telemetry Viewer
def test_lost_corner_stepper_same_rule_for_both_arrows(opener, laps, warnings):  # noqa: F811
    dialog = opener()
    view, backend = dialog.view, dialog.backend
    shown_slower_lap(dialog, laps)
    chart = chart_of(view)
    table = backend.cornerTable
    summary = dict(table.summary)
    assert summary.get("corners")

    def stepper() -> list[bool]:
        pump(0.1)
        return [named(view, name).property("visible") for name in ("previousLost", "lostPosition", "nextLost")]

    table.set_summary({**summary, "corners": summary["corners"][:1]})  # one corner: its chip zooms on it
    assert stepper() == [False, False, False]
    chart.stepLost(-1)  # Shift+[ still goes to it
    assert chart.property("lostIndex") == 0
    if len(summary["corners"]) > 1:
        table.set_summary(summary)
        assert stepper() == [True, True, True]


def test_shared_lap_dropped_on_app_shown_in_lap_viewer(laps, tmp_path):  # noqa: F811
    from PySide6.QtWidgets import QWidget

    from neopedal.ui import file_drop
    from neopedal.ui._common import BaseDialog
    from neopedal.userfile.telemetry_lap import share_lap_job

    shared = tmp_path / "Atlanta - Porsche 963 - Steven 1m10.000s.csv.gz"  # as Share Lap… writes it
    assert share_lap_job(laps[1], str(shared), "Steven") == ""
    other = tmp_path / "notes.csv"
    other.write_text("a,b\n1,2\n", encoding="utf-8")
    assert file_drop.classify(str(shared)) == file_drop.DROP_LAP
    assert file_drop.classify(laps[2]) == file_drop.DROP_LAP  # recorded lap (.csv)
    assert file_drop.classify(str(other)) == ""  # any other CSV file: not a lap
    window = QWidget()
    try:
        messages = file_drop.handle_drop(window, [str(shared), str(other)])
        assert len(messages) == 1 and "Unsupported file" in messages[0] and "notes.csv" in messages[0]
        viewer = next(dialog for dialog in window.findChildren(BaseDialog) if type(dialog).__name__ == "LapViewer")
        wait_loaded(viewer)
        assert os.path.normpath(str(shared)) in [entry.file.path for entry in viewer.backend.external]
        viewer.close()
    finally:
        window.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
