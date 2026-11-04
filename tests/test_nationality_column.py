"""Driver lists (modern design): nationality column, flag of each driver (game profile, RaceControl, real AI drivers)"""


from tests.test_modern_parity import reader, widgets  # noqa: F401 (fixture)


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


def test_column_header_label(widgets):  # noqa: F811
    widget = widgets("standings", column_nationality=True, show_column_headers=True)
    column = next(column for column in widget.table.columns if column.key == "nationality")
    assert column.label == "Nat"
    widget.grab()
