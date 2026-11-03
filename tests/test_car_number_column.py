"""Driver lists (modern design): car number column, number the game gives each car (online: per split)"""

import json

import pytest

from neopedal.template.setting_widget import WIDGET_DEFAULT
from neopedal.widget._modern import modern_module
from neopedal.widget._modern.table import TEXT
from tests.test_design_parity import shown_options
from tests.test_modern_option_parity import column_cells
from tests.test_modern_parity import reader, widgets  # noqa: F401 (fixture)
from tests.test_modern_table_rows import sample

STANDINGS = [
    {"slotID": 0, "carNumber": "4", "vehicleName": "McLaren Custom Team 2025 #397"},
    {"slotID": 3, "carNumber": "#12"},
    {"slotID": 5, "carNumber": 7},
    {"slotID": 6, "carNumber": "007"},
    {"slotID": 7, "carNumber": "  "},
    {"slotID": 8, "carNumber": None},
    {"slotID": 9, "carNumber": True},
    {"slotID": 10, "carNumber": "123456"},
    {"slotID": True, "carNumber": "1"},
    {"carNumber": "2"},
    "not a car",
]


def test_parse_numbers():
    from neopedal.car_numbers import parse_numbers

    assert parse_numbers(STANDINGS) == {0: "4", 3: "12", 5: "7", 6: "007", 10: "1234"}
    assert parse_numbers(None) == {} and parse_numbers({}) == {} and parse_numbers([]) == {}


def test_poller_keeps_numbers_by_slot():
    from neopedal.car_numbers import CarNumbers

    answers = [(200, json.dumps(STANDINGS).encode())]
    poller = CarNumbers(lambda: answers[-1])
    poller.check()
    assert poller.number(0) == "4" and poller.number(42) == ""
    answers.append((0, b""))  # game closed: nothing known
    poller.check()
    assert poller.number(0) == ""


@pytest.mark.parametrize("name", ["relative", "standings"])
def test_car_number_column_off_by_default_and_modern_only(ui_env, name):
    assert WIDGET_DEFAULT[name]["column_car_number"] is False
    options = modern_module(name).Realtime.options
    assert "column_car_number" in options and "display_order_car_number" in options
    assert "column_car_number" in shown_options(name, True)
    assert "column_car_number" not in shown_options(name, False)  # classic layout has no such column
    orders = [value for key, value in WIDGET_DEFAULT[name].items() if key.startswith("display_order_")]
    assert len(orders) == len(set(orders))  # every column at its own place once order changed


@pytest.mark.parametrize("name", ["relative", "standings"])
def test_car_number_before_driver_name(widgets, name):  # noqa: F811
    widget = widgets(name, column_car_number=True)
    keys = [column.key for column in widget.table.columns]
    assert keys.index("car_number") + 1 == keys.index("driver_name")  # design order: number, then name
    assert widget.numbers_shown
    assert "car_number" not in {column.key for column in widgets(name, column_car_number=False).table.columns}


@pytest.mark.parametrize("name", ["relative", "standings"])
def test_sample_numbers_in_previews(widgets, name):  # noqa: F811
    widget = widgets(name, column_car_number=True)
    widget.show_sample()
    cells = column_cells(widget, "car_number")
    texts = [cell.text for cell in cells]
    assert cells and all(cell.kind == TEXT for cell in cells)
    assert all(text.startswith("#") and text[1:].isdigit() for text in texts)
    assert len(set(texts)) == len(texts)  # one number per car
    widget.grab()


@pytest.mark.parametrize("name", ["relative", "standings"])
def test_live_numbers_by_slot(widgets, name, monkeypatch):  # noqa: F811
    from neopedal.car_numbers import car_numbers
    from neopedal.widget._modern.rows import DASH

    widget = widgets(name, column_car_number=True)
    field, context = sample(widget)
    first, second = field.vehicles[:2]
    first.slotID, second.slotID = 12, 3
    monkeypatch.setattr(car_numbers, "value", {12: "4"})
    widget.demo = False  # live session: numbers of the game by car slot
    build = widget.number_builder()
    own = build(first, context, True, "", None, {})
    assert (own.text, own.color) == ("#4", widget.theme.text)  # own number brighter
    other = build(first, context, False, "", None, {})
    assert (other.text, other.color) == ("#4", widget.theme.text_dim)
    assert build(first, context, False, "", None, {}) is other  # same cell object: row unchanged
    assert build(second, context, False, "", None, {}).text == DASH  # no number from the game
    widget.show_field(field, context)
    widget.grab()


def test_numbers_polled_only_when_shown(widgets, monkeypatch):  # noqa: F811
    from neopedal.car_numbers import car_numbers

    polls = []
    monkeypatch.setattr(car_numbers, "poll", lambda: polls.append(1))
    monkeypatch.setattr("neopedal.widget._modern.drivers.drawing_demo", lambda: False)
    widgets("standings").poll_columns([])
    assert not polls
    widgets("standings", column_car_number=True).poll_columns([])
    assert polls == [1]
    monkeypatch.setattr("neopedal.widget._modern.drivers.drawing_demo", lambda: True)
    widgets("relative", column_car_number=True).poll_columns([])  # overlay pictures: nothing read
    assert polls == [1]


def test_column_header_label(widgets):  # noqa: F811
    widget = widgets("standings", column_car_number=True, show_column_headers=True)
    column = next(column for column in widget.table.columns if column.key == "car_number")
    assert column.label == "#"
    widget.grab()
