"""Driver lists (modern design): team name after driver name, from game Rest API or livery name"""

import json

import pytest
from PySide6.QtCore import QRectF
from PySide6.QtGui import QImage, QPainter

from tests.test_modern_option_parity import column_cells
from tests.test_modern_table_rows import new_table, sample

STANDINGS = [
    {"slotID": 0, "fullTeamName": "Garage 21", "vehicleName": "Z06GT3R Custom Team 2026 #397:CS"},
    {"slotID": 3, "fullTeamName": "Vector Sport #10", "vehicleName": "Vector Sport #10:ELMS2"},
    {"slotID": 5, "fullTeamName": "VLMDH Custom Team 2026", "vehicleName": "VLMDH Custom Team 2026 #397"},
    {"slotID": 7, "fullTeamName": "Vista AF Corse 2026 #21"},
    {"slotID": True, "fullTeamName": "Bool slot"},
    {"slotID": 9, "fullTeamName": None},
    "not a car",
]


@pytest.mark.parametrize(("name", "team"), [
    ("BMW M Team WRT", "BMW M Team WRT"),
    ("Vector Sport #10", "Vector Sport"),
    ("Vista AF Corse 2026 #21", "Vista AF Corse"),
    ("Aston Martin THOR Team 2025 #007:LM", "Aston Martin THOR Team"),
    ("VLMDH Custom Team 2026", ""),  # custom livery, no team chosen
    ("Old Style Racing Old Style Racing  OSR", "Old Style Racing Old Style Racing  OSR"),
    ("Team 2000", "Team"),
    ("  ", ""),
])
def test_clean_team_name(name, team):
    from neopedal.team_names import clean_team_name

    assert clean_team_name(name) == team


@pytest.mark.parametrize(("vehicle", "team"), [
    ("BMW M Team WRT 2025 #15:LM", "BMW M Team WRT"),
    ("WTM by Rinaldi Racing 2025 #12:ELMS", "WTM by Rinaldi Racing"),
    ("Z06GT3R Custom Team 2026 #397:CS", ""),  # online custom livery: team only from the game Rest API
    ("Ferrari 499P", ""),  # no car number: not a team livery name
    ("", ""),
])
def test_team_of_vehicle(vehicle, team):
    from neopedal.team_names import team_of_vehicle

    assert team_of_vehicle(vehicle) == team


def test_team_names_from_rest_and_vehicle_fallback():
    from neopedal.team_names import TeamNames, parse_teams

    assert parse_teams(STANDINGS) == {0: "Garage 21", 3: "Vector Sport", 7: "Vista AF Corse"}
    assert parse_teams(None) == {} and parse_teams({}) == {}
    poller = TeamNames(lambda: (200, json.dumps(STANDINGS).encode()))
    poller.check()
    assert poller.team(0, "Z06GT3R Custom Team 2026 #397:CS") == "Garage 21"
    assert poller.team(5, "VLMDH Custom Team 2026 #397") == ""
    assert poller.team(42, "Porsche Penske Motorsport 2025 #6:LM") == "Porsche Penske Motorsport"  # not in answer


def test_team_name_after_driver_name(ui_env, bundled_fonts, monkeypatch):
    from neopedal.setting import cfg
    from neopedal.team_names import team_names
    from neopedal.widget._modern.table import TEXT, Cell

    setting = cfg.user.setting["standings"]
    plain = new_table(cfg, "standings")
    setting["show_team_name"] = True
    widget = new_table(cfg, "standings")
    assert not plain.team_shown and widget.team_shown
    width = {table.table.columns[[c.key for c in table.table.columns].index("driver_name")].width
             for table in (plain, widget)}
    assert len(width) == 2  # room added for team name
    field, context = sample(widget)
    widget.show_field(field, context)  # sample teams in previews
    cells = column_cells(widget, "driver_name")
    assert cells and all(cell.kind == TEXT and cell.extra for cell in cells)
    plain.show_field(field, context)
    assert not any(cell.extra for cell in column_cells(plain, "driver_name"))
    # Live: team of slot from game, else from livery name, nothing if unknown
    monkeypatch.setattr(team_names, "value", {4: "Garage 21"})
    widget.demo = False
    car = field.vehicles[0]
    car.slotID, car.vehicleName = 4, "Z06GT3R Custom Team 2026 #397:CS"
    assert widget.team_of(car) == "Garage 21"
    car.slotID = 8
    assert widget.team_of(car) == ""
    car.vehicleName = "BMW M Team WRT 2025 #15:LM"
    assert widget.team_of(car) == "BMW M Team WRT"
    # Drawn after the name; left out when the name fills the cell
    image = QImage(400, 40, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(0)
    painter = QPainter(image)
    calls = []
    original = widget.draw_text
    monkeypatch.setattr(widget, "draw_text", lambda *args, **kwargs: (calls.append(args[2]), original(*args, **kwargs)))
    rect = QRectF(0, 0, 300, 30)
    widget.draw_name_and_team(painter, rect, Cell(TEXT, "A. Driver", "value", extra="Garage 21"))
    assert calls == ["A. Driver", "Garage 21"]
    calls.clear()
    widget.draw_name_and_team(painter, QRectF(0, 0, widget.text_width("value", "A. Driver"), 30),
                              Cell(TEXT, "A. Driver", "value", extra="Garage 21"))
    assert calls == ["A. Driver"]
    painter.end()
    widget.deleteLater()
    plain.deleteLater()


def test_team_poll_only_when_shown(ui_env, bundled_fonts, monkeypatch):
    from neopedal.setting import cfg
    from neopedal.team_names import team_names

    polls = []
    monkeypatch.setattr(team_names, "poll", lambda: polls.append(1))
    monkeypatch.setattr("neopedal.widget._modern.drivers.drawing_demo", lambda: False)
    plain = new_table(cfg, "standings")
    plain.poll_columns([])
    assert not polls
    cfg.user.setting["standings"]["show_team_name"] = True
    widget = new_table(cfg, "standings")
    widget.poll_columns([])
    assert polls == [1]
    widget.deleteLater()
    plain.deleteLater()
