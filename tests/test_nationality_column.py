"""Driver lists (modern design): nationality column, flag of each driver (game profile, RaceControl, real AI drivers)"""

import pytest

from neopedal.template.setting_widget import WIDGET_DEFAULT
from neopedal.widget._modern import modern_module
from neopedal.widget._modern.table import EMPTY_CELL, FLAG
from tests.test_design_parity import shown_options
from tests.test_modern_option_parity import column_cells
from tests.test_modern_parity import reader, widgets  # noqa: F401 (fixture)
from tests.test_modern_table_rows import sample


def test_name_key_ignores_accents_dots_and_suffixes():
    from neopedal.driver_nations import name_key

    assert name_key("Jean-Éric Vergne") == name_key("jean eric vergne")
    assert name_key("P. J. Hyett") == name_key("PJ Hyett") == "pj hyett"
    assert name_key("Horst Felbermayr Jr.") == "horst felbermayr"
    assert name_key("Cem Bölükba\u015f\u0131") == "cem bolukbasi"  # dotless i
    assert name_key("Kevin Estre#1234") == "kevin estre"  # online suffix


def test_real_drivers_known():
    from neopedal.driver_nations import known_nationality

    assert known_nationality("Kévin Estre") == "FR"
    assert known_nationality("Alessandro Pier Guidi") == "IT"
    assert known_nationality("Ant�nio F�lix da Costa") == "PT"  # accents not decoded (game encoding)
    assert known_nationality("Fran�ois Perrodo") == "FR"
    assert known_nationality("Somebody Unknown") == "" and known_nationality("") == ""


def test_bundled_codes_have_flags(ui_env):
    from neopedal.driver_nations import known_drivers
    from neopedal.flags import flag_code

    codes = set(known_drivers().values())
    assert len(known_drivers()) > 400
    assert {code for code in codes if not flag_code(code)} == set()


@pytest.mark.parametrize(("value", "code"), [
    ("FR", "fr"), ("fr", "fr"), ("FRA", "fr"), ("GER", "de"), ("NED", "nl"), ("DEU", "de"), ("gb-sct", "gb-sct"),
    ("", ""), ("ZZ", ""), ("XYZW", ""), (None, ""),
])
def test_flag_codes(ui_env, value, code):
    from neopedal.flags import flag_code

    assert flag_code(value) == code


def test_flag_pixmap_cut_out_of_sheet(ui_env):
    from neopedal.flags import flag_clip, flag_pixmap

    pixmap = flag_pixmap("FR", 12, 2.0)
    assert (pixmap.width(), pixmap.height(), pixmap.devicePixelRatio()) == (32, 24, 2.0)
    image = pixmap.toImage()
    blue, red = image.pixelColor(2, 12), image.pixelColor(29, 12)  # French flag: blue left, red right
    assert blue.blue() > 2 * blue.red() and red.red() > 2 * red.blue()
    assert flag_pixmap("FR", 12, 2.0) is pixmap  # cut out once per size
    assert flag_pixmap("ZZ", 12).isNull() and flag_pixmap("FR", 0).isNull()
    assert len(flag_clip("FR")) == 4 and flag_clip("ZZ") == []


def test_player_nation_read_in_background(monkeypatch):
    from neopedal import driver_nations as dn

    now = [0.0]
    reads = []
    monkeypatch.setattr(dn, "read_player_code", lambda: reads.append(1) or "FR")
    monkeypatch.setattr(dn.threading, "Thread", lambda target, **_: type("T", (), {"start": staticmethod(target)}))
    nation = dn.PlayerNation(lambda: now[0])
    assert nation.code() == "FR" and reads == [1]  # thread run at once here
    assert nation.code() == "FR" and reads == [1]  # not read again before PLAYER_SECONDS
    now[0] = dn.PLAYER_SECONDS
    nation.code()
    assert reads == [1, 1]


def test_nationality_sources(monkeypatch):
    from neopedal import driver_nations as dn
    from neopedal import rank_info
    from neopedal.process.driver_ranks import DriverRanks

    monkeypatch.setattr(dn.player_nation, "code", lambda: "BE")
    online = {"Online Racer": DriverRanks("Online Racer", "", "", "ES", None, None, "")}
    monkeypatch.setattr(rank_info, "driver_ranks", online.get)
    assert dn.nationality("Steven Vezzu", True) == "BE"  # game profile
    assert dn.nationality("Online Racer", False) == "ES"  # RaceControl profile
    assert dn.nationality("Kévin Estre", False) == "FR"  # AI: real driver
    assert dn.nationality("Nobody", False) == ""
    monkeypatch.setattr(dn.player_nation, "code", lambda: "")
    assert dn.nationality("Kévin Estre", True) == "FR"  # profile not read yet


@pytest.mark.parametrize("name", ["relative", "standings"])
def test_nationality_column_off_by_default_and_modern_only(ui_env, name):
    assert WIDGET_DEFAULT[name]["column_nationality"] is False
    options = modern_module(name).Realtime.options
    assert "column_nationality" in options and "display_order_nationality" in options
    assert "column_nationality" in shown_options(name, True)
    assert "column_nationality" not in shown_options(name, False)  # classic layout has no such column
    orders = [value for key, value in WIDGET_DEFAULT[name].items() if key.startswith("display_order_")]
    assert len(orders) == len(set(orders))  # every column at its own place once order changed


@pytest.mark.parametrize("name", ["relative", "standings"])
def test_flag_before_driver_name(widgets, name):  # noqa: F811
    widget = widgets(name, column_nationality=True, column_car_number=True)
    keys = [column.key for column in widget.table.columns]
    assert keys.index("car_number") + 1 == keys.index("nationality")
    assert keys.index("nationality") + 1 == keys.index("driver_name")  # design order: flag, then name
    assert "nationality" not in {column.key for column in widgets(name, column_nationality=False).table.columns}


@pytest.mark.parametrize("name", ["relative", "standings"])
def test_sample_flags_in_previews(widgets, name):  # noqa: F811
    widget = widgets(name, column_nationality=True)
    widget.show_sample()
    cells = column_cells(widget, "nationality")
    assert cells and all(cell.kind == FLAG and cell.text for cell in cells)
    widget.grab()


@pytest.mark.parametrize("name", ["relative", "standings"])
def test_live_flags(widgets, name, monkeypatch):  # noqa: F811
    from neopedal import driver_nations

    widget = widgets(name, column_nationality=True)
    field, context = sample(widget)
    first, second = field.vehicles[:2]
    nations = {first.driverName: "FR"}
    monkeypatch.setattr(driver_nations, "nationality", lambda name, player: nations.get(name, ""))
    widget.demo = False
    build = widget.nation_builder()
    cell = build(first, context, False, "", None, {})
    assert (cell.kind, cell.text) == (FLAG, "FR")
    assert build(first, context, True, "", None, {}) is cell  # same cell object: row unchanged
    assert build(second, context, False, "", None, {}) is EMPTY_CELL  # unknown: no flag
    widget.show_field(field, context)
    widget.grab()


def test_flag_column_polls_field_ranks(widgets, monkeypatch):  # noqa: F811
    from neopedal import rank_info

    polls = []
    monkeypatch.setattr(rank_info, "poll_field", lambda names: polls.append(1))
    monkeypatch.setattr("neopedal.widget._modern.drivers.drawing_demo", lambda: False)
    widgets("standings").poll_columns([])
    assert not polls
    widgets("standings", column_nationality=True).poll_columns([])  # RaceControl profiles of online drivers
    assert polls == [1]


def test_column_header_label(widgets):  # noqa: F811
    widget = widgets("standings", column_nationality=True, show_column_headers=True)
    column = next(column for column in widget.table.columns if column.key == "nationality")
    assert column.label == "Nat"
    widget.grab()
