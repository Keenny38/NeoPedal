"""Home page review 2026-11-01: game card on track only, card spans filling each row (no hole), rank tooltip,
rank over time zoomed (hidden when flat), old remembered ranks told"""

import time

import pytest
from PySide6.QtCore import QCoreApplication

from neopedal import i18n
from neopedal.process import driver_ranks as dr
from neopedal.ui.home_driver import STALE_RANKS_DAYS, driver_card, next_rank_text, rank_tip, zoomed_chart
from tests.test_audit_g_qml_pages import item_named, pump
from tests.test_home_driver_card import PLAYER
from tests.test_perf_page_state import qml_warnings  # noqa: F401
from tests.test_ui_audit_2026_10_29_home import home, on_track  # noqa: F401

LAST = {"track": "Sebring International Raceway", "vehicle": "LMP3", "session": "Practice", "best": "1:58.978",
        "date": "11/1/26"}
DRIVER = {"name": "Keenny Hess", "identity": "France", "ranks": [], "badge": {}, "figures": [], "note": "",
          "noteStale": False, "others": []}
WEEK = {"summary": "9 sessions · 33 min · 15 laps", "highlights": []}


def test_next_rank_and_tip():
    assert next_rank_text(dr.Rank("Silver", 2, 25)) == "Silver 3"
    assert next_rank_text(dr.Rank("Silver", 3, 25)) == "Gold 1"
    assert next_rank_text(dr.Rank("Platinum", 3, 25)) == "" and next_rank_text(dr.Rank("Wood", 1, 0)) == ""
    assert rank_tip(dr.Rank("Silver", 2, 25), "-9%") == (
        "25% of the way to Silver 3\n-9% of a tier since the previous rank seen")
    assert rank_tip(dr.Rank("Platinum", 3, 80), "") == "Top rank reached"
    i18n.set_language("Français")
    try:
        assert rank_tip(dr.Rank("Silver", 2, 25), "+17%") == (
            "25 % du chemin vers Silver 3\n+17 % d'un palier depuis le rang vu précédemment")
        assert rank_tip(dr.Rank("Platinum", 3, 80), "") == "Rang maximal atteint"
    finally:
        i18n.set_language("English")


def test_rank_chart_zoomed_or_hidden():
    flat = [{"x": 0.0, "y": 0.3, "text": "Silver 2"}, {"x": 1.0, "y": 0.3, "text": "Silver 2"}]
    assert zoomed_chart(flat) == [] and zoomed_chart(flat[:1]) == []  # never moved: nothing to draw
    top = len(dr.RANK_ORDER) * 3
    small = [{"x": 0.0, "y": 4.34 / top, "text": "Silver 2"}, {"x": 1.0, "y": 4.25 / top, "text": "Silver 2"}]
    zoomed = zoomed_chart(small)  # -9% of a tier: a third of the height (quarter of a tier at least), centered
    assert zoomed[0]["y"] - zoomed[1]["y"] == pytest.approx(0.36)
    assert (zoomed[0]["y"] + zoomed[1]["y"]) / 2 == pytest.approx(0.5) and zoomed[0]["text"] == "Silver 2"
    wide = [{"x": 0.0, "y": 0.2, "text": ""}, {"x": 0.5, "y": 0.6, "text": ""}, {"x": 1.0, "y": 0.4, "text": ""}]
    assert [point["y"] for point in zoomed_chart(wide)] == pytest.approx([0.0, 1.0, 0.5])  # whole height


def test_driver_card_tips_charts_and_old_note():
    history = [dr.HistoryEntry(1.0, dr.Rank("Silver", 2, 40), dr.Rank("Platinum", 3, 50)),
               dr.HistoryEntry(2.0, dr.Rank("Silver", 2, 55), dr.Rank("Platinum", 3, 50))]
    card = driver_card(PLAYER, False, 2.0, history, None)
    driver, safety = card["ranks"]
    assert driver["tip"] == "55% of the way to Silver 3\n+15% of a tier since the previous rank seen"
    assert safety["tip"] == "Top rank reached"
    assert len(driver["chart"]) == 2 and safety["chart"] == []  # safety rank never moved: no flat line
    assert card["noteStale"] is False
    recent = driver_card(PLAYER, True, time.time() - 86400, [], None)
    old = driver_card(PLAYER, True, time.time() - 86400 * (STALE_RANKS_DAYS + 1), [], None)
    assert recent["note"] and not recent["noteStale"]
    assert old["note"] and old["noteStale"]


def show_cards(backend, last=True, driver=True, week=True):
    backend.publish("lastSession", LAST if last else {}, backend.lastSessionChanged)
    backend.publish("driver", DRIVER if driver else {}, backend.driverChanged)
    backend.publish("week", WEEK if week else {}, backend.weekChanged)
    for name in ("driver", "week", "debrief"):
        backend.set_loading(name, False)
    QCoreApplication.processEvents()
    pump(0.2)  # layout polished


def rows_of(root, names) -> dict[float, list]:
    """Cards shown, by row (top), each with its x & width"""
    rows: dict[float, list] = {}
    for name in names:
        card = item_named(root, name)
        if card.isVisible():
            rows.setdefault(round(card.y()), []).append((name, card.x(), card.width()))
    return rows


CARDS = ("gameCard", "overlaysCard", "presetCard", "weekCard", "driverCard", "lastSessionCard")


@pytest.mark.parametrize("columns", [3, 2])
@pytest.mark.parametrize("shown", [(True, True, True), (True, True, False), (True, False, True),
                                   (False, True, True), (True, False, False)])
def test_cards_fill_each_row(qml_warnings, home, columns, shown):  # noqa: F811
    from neopedal.ui.quick import BREAKPOINTS, UIScaler

    em = UIScaler.FONT_PIXEL_SCALED
    home.resize(round(em * (BREAKPOINTS["bpWide"] + 10 if columns == 3 else BREAKPOINTS["bpNarrow"])), 1000)
    show_cards(home.backend, *shown)
    root = home.view.rootObject()
    assert root.property("columns") == columns
    assert not item_named(root, "gameCard").isVisible()  # off track: the banner tells the game
    grid = item_named(root, "overlaysCard").parentItem()
    for row in rows_of(root, CARDS).values():  # every row filled from edge to edge: no hole
        left = min(x for _, x, _ in row)
        right = max(x + w for _, x, w in row)
        assert left == pytest.approx(0, abs=1) and right == pytest.approx(grid.width(), abs=1), row
    assert not qml_warnings, qml_warnings


def test_game_card_whole_row_on_track(qml_warnings, home, monkeypatch):  # noqa: F811
    on_track(monkeypatch)
    home.backend.refresh_live()
    show_cards(home.backend)
    root = home.view.rootObject()
    game = item_named(root, "gameCard")
    assert game.isVisible() and game.width() == pytest.approx(item_named(root, "overlaysCard").parentItem().width())
    assert item_named(root, "openModules").isVisible()  # modules link kept on track (lock button in game card)
    assert not qml_warnings, qml_warnings


def test_old_ranks_note_and_rank_tooltip_on_page(qml_warnings, home):  # noqa: F811
    rank = {"label": "Driver Rank", "value": "Silver 2", "color": "", "lightColor": "", "progress": 0.25,
            "progressText": "25%", "change": "-9%", "changeTone": -1, "chart": [], "tip": "25% of the way to Silver 3"}
    show_cards(home.backend)
    home.backend.publish("driver", {**DRIVER, "ranks": [rank], "note": "Last ranks seen in game menu, 10/20/26",
                                    "noteStale": True}, home.backend.driverChanged)
    pump(0.2)
    root = home.view.rootObject()
    note = item_named(root, "driverNote")
    assert note.isVisible() and note.property("stale") is True
    assert not qml_warnings, qml_warnings
