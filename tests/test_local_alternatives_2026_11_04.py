#  NeoPedal is an open-source overlay application for racing simulation.
#  Copyright (C) 2022-2026 TinyPedal developers, see contributors.md file
#
#  This file is part of NeoPedal.
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""Without RaceOS (never signed in with the game ticket): daily races of the public page of RaceControl, your online
races from the results files of the game, nationalities of an online server from the game, registration in the game"""

from __future__ import annotations

import calendar

import pytest

from neopedal import driver_nations
from neopedal import race_schedule_info as info
from neopedal.process import local_online
from neopedal.process import public_schedule as ps
from neopedal.process import race_schedule as rs
from neopedal.process import results_file as rf
from tests.test_race_schedule import fresh_info  # noqa: F401

NOW = float(calendar.timegm((2026, 11, 4, 14, 14, 0)))
READ = ps.read  # real read of the public page (fresh_info answers it: put back here, fetch faked)


def card(tier: str, title: str, duration: str, track: str, starts: list[str]) -> str:
    badges = "".join(f'<span class="badge text-yellow bg-gray-900-40">{start}</span> ' for start in starts)
    return (f'<li class="glide__slide"> <div class="scheduled-race-card position-relative"> <div> '
            f'<span class="badge tier-badge"> <i class="fa-solid fa-medal"></i> {tier} </span> '
            f'<div class="race-info"> <h4 class="text-white fs-xl mb-2">{title}</h4> '
            f'<div class="race-header"> <span class="x"> <i class="fa-solid fa-timer me-1"></i> Duration </span> '
            f'<hr class="w-100"> <span class="x"> {duration} </span> </div> '
            f'<div class="race-header"> <span class="x"> <i class="fa-solid fa-route me-1"></i> Track </span> '
            f'<hr class="w-100"> <span class="x"> {track} </span> </div> '
            f'<div class="marquee"> {badges}</div> </div> </div> </div> </li>')


PAGE = ('<html><h2 class="fs-xxl mb-0">Upcoming Daily Races</h2> <div class="powered-by"> <img src="/assets/clients/'
        'race_control/rc_logo_symbol.png" /> </div>' + card("beginner", "rF2 Race", "20 minutes", "Spa", ["4 Nov at 3:00pm"])
        + '<h2 class="fs-xxl mb-0">Upcoming Daily Races</h2> <div class="powered-by"> <img src="/assets/clients/'
        'race_control/lmu_logo_dark-b0.png" /> </div> <ul>'
        + card("beginner", "LMGT3 Fixed", "32 minutes", "Monza", ["4 Nov at 3:15pm", "4 Nov at 4:00pm"])
        + card("beginner", "LMP3 Fixed", "32 minutes", "Fuji Wec 2023", ["4 Nov at 3:00pm", "4 Nov at 3:45pm"])
        + card("advanced", "ELMS Super 60", "1 h 13", "Bahrain Wec 2023", ["4 Nov at 3:25pm"])
        + card("expert", "Unknown tier", "10 minutes", "Imola", ["4 Nov at 3:00pm"])
        + "</ul> <h2>Featured Community Events</h2></html>")


def test_public_page_daily_races_of_lmu_only():
    events = ps.parse_daily(PAGE, NOW)
    assert [(event.tier, event.title) for event in events] == [
        ("beginner", "LMP3 Fixed"), ("beginner", "LMGT3 Fixed"), ("advanced", "ELMS Super 60")]  # rF2 & unknown left out
    lmp3 = events[0]
    assert lmp3.track == "Fuji Wec 2023" and lmp3.total == 32 * 60 and lmp3.kind == "daily"
    assert [start.time for start in lmp3.starts] == [NOW + 46 * 60, NOW + 91 * 60]  # UTC
    assert all(not start.event_id and start.registrations == -1 for start in lmp3.starts)  # nothing of RaceControl
    assert events[2].total == 73 * 60
    assert ps.frequency(events) == {"beginner": 900.0}


def test_public_page_changed_shows_nothing():
    assert ps.parse_daily("<html>new design</html>", NOW) == ()
    assert ps.parse_daily(PAGE.replace("lmu_logo", "other_logo"), NOW) == ()


def test_start_of_next_year():
    december = float(calendar.timegm((2026, 12, 31, 22, 0, 0)))
    assert ps.start_time(1, "Jan", 1, 0, "am", december) == calendar.timegm((2027, 1, 1, 1, 0, 0))
    assert ps.start_time(4, "Nov", 12, 5, "pm", NOW) == calendar.timegm((2026, 11, 4, 12, 5, 0))
    assert ps.start_time(4, "Nov", 12, 5, "am", NOW) == calendar.timegm((2026, 11, 4, 0, 5, 0))


def test_track_scene_from_the_game_catalog():
    scenes = ["lemanswec", "fujiwec", "monzawec", "monzaelms", "portimaowec", "portimaoelms", "roadatlanta", "daytonarc"]
    assert ps.scene_of("Le Mans", scenes) == "lemanswec" and ps.scene_of("Fuji Wec 2023", scenes) == "fujiwec"
    assert ps.scene_of("Monza", scenes) == "monzawec" and ps.scene_of("Road Atlanta 2026", scenes) == "roadatlanta"
    assert ps.scene_of("Portimao Wec 2023", scenes) == "portimaowec" and ps.scene_of("Daytona", scenes) == "daytonarc"
    assert ps.scene_of("Nowhere", scenes) == "" and ps.scene_of("", scenes) == ""


@pytest.fixture
def public_info(ui_env, fresh_info, monkeypatch):  # noqa: F811
    monkeypatch.setattr(ps, "read", READ)
    pages = []

    def fetch(timeout=ps.TIMEOUT, path=""):
        if path:  # hosted races & community events: none (see test_public_pages_field_pace_2026_11_04)
            return "<html></html>"
        pages.append(1)
        return PAGE

    monkeypatch.setattr(ps, "fetch", fetch)
    monkeypatch.setattr(ps.time, "time", lambda: NOW)
    return fresh_info, pages


def test_public_page_read_once_an_hour(public_info, monkeypatch):
    _page, pages = public_info
    state = info.read()
    assert state.status == info.PUBLIC and [event.title for event in state.schedule.events] == [
        "LMP3 Fixed", "LMGT3 Fixed", "ELMS Super 60"]
    assert pages == [1] and not state.schedule.missing  # reminders judge every race read
    assert [event.scene for event in state.schedule.events][:2] == ["", "monzawec"]  # scene of the game catalog
    assert not info.due()  # read again an hour later
    assert info.due(info._state.tried + info.READ_SECONDS)
    assert info.read() is state and pages == [1]


def test_public_page_not_read_keeps_the_races_shown(public_info, monkeypatch):
    _client, _pages = public_info
    state = info.read()
    monkeypatch.setattr(ps, "fetch", lambda timeout=ps.TIMEOUT, path="": (_ for _ in ()).throw(OSError("offline")))
    monkeypatch.setattr(info.time, "monotonic", lambda: state.tried + info.FORCE_SECONDS)
    again = info.read(force=True)
    assert again.status == info.PUBLIC and again.schedule is state.schedule and again.failures == 1
    assert info.due(again.tried + info.RETRY_SECONDS)  # tried again soon


def test_public_page_off_reads_nothing(public_info, monkeypatch):
    _page, pages = public_info
    monkeypatch.setattr(info, "enabled", lambda: False)
    assert info.read().status == info.OFF and not pages


def test_status_tells_the_public_site(public_info):
    from neopedal.ui.quick import schedule_backend

    info.read()
    level, note = schedule_backend.status_note(info.PUBLIC, info.state().schedule)
    assert level == "info" and "public" in note and "Register in the game" in note
    level, note = schedule_backend.status_note(info.FAILED, info.state().schedule)
    assert level == "warning" and "did not answer" in note


def entry(name: str, position: int, player: bool = False) -> rf.Entry:
    laps = tuple(rf.Lap(number, position, 100.0 + number, -1.0, (0.0, 0.0, 0.0), 0.0, "", False, -1.0, 0.0, -1.0, 0.0,
                        ()) for number in range(1, 4))
    return rf.Entry(name, "Team", "Livery", "Oreca 07", "LMP2", "7", position, position, position, position, 3,
                    101.0, 400.0, 0, "Finished Normally", "", True, player, "", laps, ())


def session(path: str, setting: str = "Multiplayer") -> rf.SessionResult:
    return rf.SessionResult(path, "LMU", setting, "LMP2 Fixed", NOW, "Race", "Race", "Monza", "Monza", "Monza",
                            5793.0, "1.3", 30, 0, 3, (entry("Keenny Hess", 1, True), entry("Other", 2)), ())


def test_online_races_from_results_files(tmp_path, monkeypatch):
    for name, setting in (("2026_11_03_14_42_57-81R1.xml", "Multiplayer"), ("2026_11_03_14_10_00-81P1.xml", "Multiplayer"),
                          ("2026_11_02_20_00_00-80R1.xml", "Race Weekend"), ("2026_11_01_20_00_00-80R1.xml", "Multiplayer")):
        (tmp_path / name).write_text(f"<?xml version='1.0'?><rFactorXML><RaceResults><Setting>{setting}</Setting>",
                                     encoding="utf-8")
    monkeypatch.setattr(local_online, "_online", {})
    races = local_online.online_races([str(tmp_path)])
    assert [race.rsplit("\\", 1)[-1].rsplit("/", 1)[-1] for race in races] == [
        "2026_11_03_14_42_57-81R1.xml", "2026_11_01_20_00_00-80R1.xml"]  # races of online servers only, newest first
    monkeypatch.setattr(rf, "read_results", lambda path, names=(), keep=True: session(path))
    page, answered = local_online.read_page([str(tmp_path)], 1, 5)
    assert len(page) == answered == 2 and page[0].path == races[0] and page[0].title == "LMP2 Fixed"
    row = page[0].rows[0]
    assert (row.position, row.name, row.laps, row.lap_times, row.lap_positions) == (
        1, "Keenny Hess", 3, (101.0, 102.0, 103.0), (1, 1, 1))
    assert local_online.player_name() == "Keenny Hess"
    assert local_online.read_page([str(tmp_path)], 2, 5) == ([], 0)
    assert local_online.read_race(page[0].path).rows[1].name == "Other"


def test_unreadable_results_file_does_not_end_the_online_list(tmp_path, monkeypatch):
    names = [f"2026_11_0{day}_20_00_00-80R1.xml" for day in range(1, 4)]
    for name in names:
        (tmp_path / name).write_text("<?xml version='1.0'?><rFactorXML><RaceResults><Setting>Multiplayer</Setting>",
                                     encoding="utf-8")
    monkeypatch.setattr(local_online, "_online", {})

    def read_results(path, names=(), keep=True):
        if path.endswith(names_[1]):
            raise ValueError("broken file")
        return session(path)

    names_ = names
    monkeypatch.setattr(rf, "read_results", read_results)
    page, answered = local_online.read_page([str(tmp_path)], 1, 3)
    assert len(page) == 2 and answered == 3  # a full page of files: More Results still offered


def test_online_results_page_from_files(ui_env, fresh_info, monkeypatch):  # noqa: F811
    monkeypatch.setattr(info, "_local_folders", lambda: ("folder",))
    monkeypatch.setattr(info, "_local_names", lambda: ())
    races = [rs.OnlineResult("a.xml", NOW, "Race", "Monza", ())]
    monkeypatch.setattr(local_online, "read_page",
                        lambda folders, page, take, names=(): (races, 2) if page == 1 else ([], 0))
    monkeypatch.setattr(local_online, "read_race", lambda path, names=(): races[0] if path == "a.xml" else None)
    found = info.read_results(1)
    assert list(found) == races and found.answered == 2  # files of the page, one unreadable
    assert list(info.read_results(2)) == []
    assert info.read_result("a.xml") is races[0] and info.read_result("b.xml") is None


def test_nationalities_of_an_online_server_from_the_game(monkeypatch):
    answer = {"teams": [{"name": "A", "drivers": {"Keenny Hess": {"nationality": "FR", "badge": "none"},
                                                  "Other Driver": {"nationality": "", "teamName": "X"}}},
                        {"drivers": {"Third One": {"nationality": "DEU"}}}]}
    found = driver_nations.team_nationalities(answer)
    assert found == {driver_nations.name_key("Keenny Hess"): "FR", driver_nations.name_key("Third One"): "DEU"}
    assert driver_nations.team_nationalities(None) == {} and driver_nations.team_nationalities([1, "x"]) == {}


def test_team_nations_read_in_background(monkeypatch):
    from neopedal import game_rest_cache

    clock = [0.0]
    asked = []

    class Cache:
        def json(self, route, max_age):
            asked.append(route)
            return {"drivers": {"Keenny Hess": {"nationality": "FR"}}}

    monkeypatch.setattr(game_rest_cache, "rest_cache", Cache())
    nations = driver_nations.TeamNations(clock=lambda: clock[0])
    nations.code("Keenny Hess")  # first call starts the read
    for _ in range(200):
        if not nations._busy:
            break
        import time

        time.sleep(0.01)
    assert nations.code("Keenny Hess") == "FR" and asked == [driver_nations.TEAMS_ROUTE]
    clock[0] += driver_nations.TEAMS_SECONDS
    nations.code("x")
    for _ in range(200):
        if not nations._busy:
            break
        import time

        time.sleep(0.01)
    assert len(asked) == 2


def test_badges_of_an_online_server_from_the_game():
    answer = {"teams": [{"drivers": {"Keenny Hess": {"nationality": "FR", "badge": "trusted_racer"},
                                     "Other Driver": {"badge": "none"}, "Third": {"badge": ""}}}]}
    assert driver_nations.team_values(answer, "badge") == {driver_nations.name_key("Keenny Hess"): "trusted_racer"}
    nations = driver_nations.TeamNations(clock=lambda: 0.0)
    nations._codes, nations._badges, nations._read_at = {}, driver_nations.team_values(answer, "badge"), 0.0
    assert nations.badge("Keenny Hess") == "trusted_racer" and nations.badge("Other Driver") == ""
