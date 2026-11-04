"""Track layout names: one name per layout on every page (process.track_names), stored names untouched"""

import json
from typing import Any

import pytest

from neopedal.process import results_file as rf
from neopedal.process import results_index as ri
from neopedal.process import track_names as tn

# Entries of /rest/sessions/getTracksAll as LMU 1.3 sends them (fields used only)
GAME_TRACKS = [
    {"sceneDesc": "PORTIMAOELMS", "properTrackName": "Algarve International Circuit", "cmpName": "PortimaoWEC_2023",
     "trackName": "Algarve International Circuit", "eventName": "4 Hours of Portimao"},
    {"sceneDesc": "PORTIMAOWEC", "properTrackName": "Algarve International Circuit", "cmpName": "PortimaoWEC_2023",
     "trackName": "Algarve International Circuit", "eventName": "6 Hours of Portimao"},
    {"sceneDesc": "LEMANSWEC", "properTrackName": "Circuit de la Sarthe", "cmpName": "LeMans_2023",
     "trackName": "Circuit de la Sarthe", "eventName": "24 Heures du Mans"},
    {"sceneDesc": "LEMANSWEC_MULSANNE", "properTrackName": "Circuit de la Sarthe Mulsanne", "cmpName": "LeMans_2023",
     "trackName": "Circuit de la Sarthe", "eventName": "Circuit de la Sarthe Mulsanne",
     "layoutName": "Mulsanne Circuit"},
    {"sceneDesc": "BAHRAINWEC", "properTrackName": "Bahrain International Circuit", "cmpName": "BahrainWEC_2023",
     "trackName": "Bahrain International Circuit", "eventName": "8 Hours of Bahrain"},
    {"sceneDesc": "BAHRAINWEC_OUTER", "properTrackName": "Bahrain Outer Circuit", "cmpName": "BahrainWEC_2023",
     "trackName": "Bahrain International Circuit", "eventName": "Bahrain Outer Circuit",
     "layoutName": "Outer Circuit"},
    {"sceneDesc": "SILVERSTONEELMS", "properTrackName": "Silverstone Grand Prix Circuit - ELMS",
     "cmpName": "Silverstone_2025", "trackName": "Silverstone Circuit", "eventName": "4 Hours of Silverstone"},
    {"sceneDesc": "SILVERSTONEWEC", "properTrackName": "Silverstone Grand Prix Circuit - WEC",
     "cmpName": "Silverstone_2025", "trackName": "Silverstone Circuit", "eventName": "6 Hours of Silverstone"},
    {"sceneDesc": "PAULRICARDELMS", "properTrackName": "Paul Ricard - ELMS", "cmpName": "PaulRicard_2025",
     "trackName": "Paul Ricard Circuit", "eventName": "4 Hours of Castellet"},
    {"sceneDesc": "INTERLAGOSWEC", "properTrackName": "Aut�dromo Jos� Carlos Pace",
     "cmpName": "Interlagos_2024", "eventName": "Rolex 6 Hours Of Sao Paulo"},
    {"sceneDesc": "BROKEN"}, "junk",
]
NAMES = tn.parse_track_names(GAME_TRACKS)


@pytest.mark.parametrize(("candidates", "scene", "shown"), [
    (("Circuit de la Sarthe",), "", "Circuit de la Sarthe"),  # layout name (shared memory, stats key)
    (("24 Heures du Mans",), "", "Circuit de la Sarthe"),  # event name (results, RaceControl)
    (("6 Hours of Portimao",), "", "Algarve International Circuit"),  # ELMS & WEC events of one layout
    (("4 Hours of Castellet",), "", "Paul Ricard - ELMS"),
    (("x",), "BahrainWEC_Outer", "Bahrain Outer Circuit"),  # scene in RaceControl case
    (("PortimaoWEC_2023",), "", "Algarve International Circuit"),  # folder of one main layout name
    (("LeMans_2023",), "", "Circuit de la Sarthe"),  # Mulsanne has a layoutName: not a main layout
    (("Silverstone_2025",), "", "Silverstone 2025"),  # folder of two main layouts: unknown, spaced
    (("Algarve International Circuit 1.27",), "", "Algarve International Circuit"),  # version cut
    (("Nowhere",), "UNKNOWN_SCENE", "Nowhere"),  # scene never shown
    (("", "  ", "Long Beach"), "", "Long Beach"),
    ((), "", ""),
])
def test_layout_name_of_any_name(candidates, scene, shown):
    assert tn.layout_name(NAMES, *candidates, scene=scene) == shown


def test_venue_names_never_lead_to_another_layout():
    # Venue shared by layouts: a venue that is not itself a layout name is unknown
    assert "silverstone circuit" not in NAMES and "paul ricard circuit" not in NAMES
    assert tn.layout_name(NAMES, "Silverstone Circuit") == "Silverstone Circuit"
    # Each layout keeps its own name (stats keys of both Silverstone layouts stay apart)
    assert NAMES["silverstoneelms"] != NAMES["silverstonewec"]
    assert NAMES["bahrain outer circuit"] == "Bahrain Outer Circuit"
    assert "broken" not in NAMES


def test_lost_characters_spelled_by_shared_memory_name():
    right = "Autódromo José Carlos Pace"
    assert tn.layout_name(NAMES, right) == right  # unknown spelling: as given
    assert tn.layout_name(NAMES, "Rolex 6 Hours Of Sao Paulo", right) == right  # lost characters fit the name
    assert tn.layout_name(NAMES, "x", scene="InterlagosWEC") == "x"  # unknown name without lost characters
    assert tn.layout_name(NAMES, scene="InterlagosWEC") == NAMES["interlagoswec"]  # nothing better


def test_clean_unknown_names():
    assert tn.clean("PortimaoWEC_2023") == "PortimaoWEC 2023"
    assert tn.clean("Paul Ricard - 1A-V2-Short") == "Paul Ricard - 1A-V2-Short"
    assert tn.clean(" Fuji Speedway v1.29 ") == "Fuji Speedway"
    assert tn.clean(None) == ""  # type: ignore[arg-type]


def test_game_catalog_keeps_names_for_next_runs(ui_env, monkeypatch):
    from neopedal.process import game_images as gi
    from neopedal.userfile import game_images

    answers = {gi.TRACKS_ROUTE: (200, json.dumps(GAME_TRACKS).encode())}
    monkeypatch.setattr(game_images, "fetch_from_game", lambda resource, max_body=None: answers.get(resource, (404, b"")))
    cache = game_images.GameImages()
    monkeypatch.setattr(game_images, "images", cache)  # fetch thread ended after the test
    assert cache.track_name("24 Heures du Mans") == "24 Heures du Mans"  # game lists not read yet
    assert cache.read_game_lists()
    assert cache.track_name("24 Heures du Mans") == "Circuit de la Sarthe"
    assert cache.track_name("6 Hours of Silverstone", scene="SilverstoneWEC") == "Silverstone Grand Prix Circuit - WEC"
    later = game_images.GameImages()  # game not running: names read from catalog.json
    answers.clear()
    later.load_catalog()
    assert later.track_names == cache.track_names
    assert later.track_name("x", scene="paulricardelms") == "Paul Ricard - ELMS"
    assert later.stop()


# Results files: layout name as title, event name under it
def result(course: str, track: str, venue: str) -> rf.SessionResult:
    return rf.SessionResult(path="2026-11-01-R1.xml", game="LMU", setting="", server="", time=0.0, tag="Race",
                            kind="Race", track=track, venue=venue, course=course, track_length=0.0,
                            game_version="", minutes=0, lap_limit=0, most_laps=0, entries=(), events=())


@pytest.mark.parametrize(("course", "track", "venue", "layout", "event"), [
    ("Circuit de la Sarthe", "24 Heures du Mans", "Circuit de la Sarthe", "Circuit de la Sarthe",
     "24 Heures du Mans"),
    ("Bahrain Outer Circuit", "Bahrain Outer Circuit", "Bahrain International Circuit", "Bahrain Outer Circuit",
     "Bahrain International Circuit"),
    ("Michelin Raceway Road Atlanta", "Michelin Raceway Road Atlanta", "Michelin Raceway Road Atlanta",
     "Michelin Raceway Road Atlanta", ""),
    ("", "Mills Metropark", "Mills Metropark", "Mills Metropark", ""),  # rFactor 2 file without course
])
def test_results_layout_and_event(course, track, venue, layout, event):
    session = result(course, track, venue)
    assert rf.layout_of(session) == layout and rf.event_of(session) == event


def summary(course: str, track: str, venue: str) -> ri.ResultSummary:
    values: dict[str, Any] = {name: 0 for name in ri.ResultSummary._fields if name not in ri.ResultSummary._field_defaults}
    values.update(path="2026-11-01-R1.xml", game="LMU", kind="Race", code="R", track=track, venue=venue,
                  game_version="", setting="", server="", driver="", vehicle="Car #1", car="Car", car_class="Hyper",
                  status="", best_lap=97.0, end=1000.0)
    return ri.ResultSummary(**values, course=course)


def test_results_matched_to_stats_and_replays_by_layout():
    paul_ricard = summary("Paul Ricard - ELMS", "4 Hours of Castellet", "Paul Ricard Circuit")
    # Driver stats key is the layout name: neither event nor venue name
    assert ri.same_track("Paul Ricard - ELMS", paul_ricard)
    stats = {"Paul Ricard - ELMS": {"Hyper": {"pb": 99.0, "rb": 96.0}}}
    fixes = ri.best_lap_fixes([paul_ricard], stats, {paul_ricard.path: "Hyper"}, "Class", {})
    assert [(fix.track, fix.stat) for fix in fixes] == [("Paul Ricard - ELMS", "pb")]
    # Replays are named after the layout
    session = ri.replay_session(paul_ricard)
    replay = ri.ReplayFile("Paul Ricard - ELMS R1 2", "x.Vcr", session.end + 60)
    assert ri.match_replays([session], [replay]) == {paul_ricard.path: replay}


def test_summary_cache_of_former_version_read_again(tmp_path):
    path = tmp_path / ri.SUMMARY_CACHE_NAME
    fields = [name for name in ri.ResultSummary._fields if name != "course"]
    path.write_text(json.dumps({"version": ri.SUMMARY_CACHE_VERSION, "fields": fields, "files": {}}),
                    encoding="utf-8")
    assert ri.load_summary_cache(str(path)) == {}


def test_director_race_history_names_layout(tmp_path, monkeypatch):
    from neopedal.process import driver_history as dh

    session = result("Paul Ricard - ELMS", "4 Hours of Castellet", "Paul Ricard Circuit")
    monkeypatch.setattr(ri, "kept_file", lambda path: None)
    monkeypatch.setattr(rf, "read_results", lambda path, keep=False: session)
    monkeypatch.setattr(ri, "race_cars", lambda found: (ri.CarResult(("Alice",), "Hyper", 1, True),))
    records = dh.DriverHistory.read(str(tmp_path / "2026-11-01-R1.xml"))
    assert records["alice"].track == "Paul Ricard - ELMS"
    assert dh.same_track("Paul Ricard - ELMS", records["alice"].track)  # REST sessionInfo trackName


def test_upcoming_race_matches_layout_not_venue(ui_env, monkeypatch):
    from neopedal.ui.quick import stats_analysis
    from neopedal.userfile import game_images

    # /rest/race/track gives the venue as short name of both Bahrain layouts
    venue_names: dict[str, tuple[str, ...]] = {"bahrainwec_outer": ("Bahrain Outer Circuit",
                                                                 "Bahrain International Circuit")}
    monkeypatch.setattr(game_images.images, "track_names", dict(NAMES))
    monkeypatch.setattr(game_images.images, "_loaded_folder", game_images.images.folder)
    assert stats_analysis.scene_names("BahrainWEC_Outer", venue_names) == {"bahrain outer circuit"}
    monkeypatch.setattr(game_images.images, "track_names", {})  # game lists never read: names of /rest/race/track
    assert stats_analysis.scene_names("BahrainWEC_Outer", venue_names) == {
        "bahrain outer circuit", "bahrain international circuit"}


def test_upcoming_races_page_shows_layout_name(ui_env, monkeypatch):
    from neopedal.process import race_schedule as rs
    from neopedal.ui.quick import schedule_view
    from neopedal.userfile import game_images

    schedule = rs.EMPTY._replace(tracks={"bahrainwec_outer": rs.TrackInfo("Bahrain International Circuit", True)})
    # Game lists never read: name /rest/race/track gives the scene (as before)
    assert schedule_view.track_of("BahrainWEC_Outer", "Bahrain Outer Circuit", schedule) == (
        "Bahrain International Circuit", True)
    monkeypatch.setattr(game_images.images, "track_names", dict(NAMES))
    monkeypatch.setattr(game_images.images, "_loaded_folder", game_images.images.folder)
    assert schedule_view.track_of("BahrainWEC_Outer", "Bahrain Outer Circuit", schedule) == (
        "Bahrain Outer Circuit", True)
    assert schedule_view.track_of("LeMansWEC", "24 Heures du Mans", schedule) == ("Circuit de la Sarthe", None)
