"""Upcoming Races: RaceControl answers parsed, disk copy, shared reads, details read on demand, reminders, your
laps, rows of the page & Home card, filters, menu, calendar export, QML page"""

import json
import time

import pytest
from PySide6.QtCore import QCoreApplication

from neopedal import race_schedule_info as info
from neopedal.process import race_schedule as rs
from tests.test_audit_g_qml_pages import item_named, items_of, pump
from tests.test_perf_page_state import qml_warnings  # noqa: F401

NOW = 1_793_580_000.0  # 2026-11-02 00:40 UTC


def iso(seconds: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(seconds))


def race_config(title: str, start: float, tier: str = "beginner", rank: str = "Bronze", level: int = 0) -> dict:
    """Daily race of a list answer, as RaceControl gives it (shortened)"""
    return {
        "id": f"id-{title}", "type": "daily", "registrations": [{"name": "Somebody"}, {"name": "Other"}],
        "configuration": {
            "title": title, "starts": iso(start), "registrationOpens": iso(start - 1800),
            "tier": {"name": tier, "entryRequirement": {"rank": rank, "tier": level}},
            "content": {
                "track": {"friendly": "PortimaoWEC_2023", "name": "PortimaoWEC", "sig": "abc",
                          "subItems": [{"name": "6 Hours of Portimao", "scn": "PortimaoWEC"}]},
                "cars": [{"friendly": "Oreca_07_ELMS_2023", "subItems": [{"name": "Vector #10", "veh": "x.VEH"}]}],
            },
            "sessions": [
                {"type": "Practice", "duration": "3m", "timeOfDay": "19h0m"},
                {"type": "Qualifying", "duration": "10m"},
                {"type": "Race", "duration": "20m", "timeOfDay": "19h20m",
                 "weather": [{"temperature": "22", "rainChange": "30"}, {"temperature": "21", "rainChange": "30"},
                             {"temperature": "19", "rainChange": "0"}]},
            ],
            "settings": {"fixedSetup": True, "tyreWarmers": True, "maxPlayers": 20},
        },
    }


SCHEDULE = {"tiers": {
    "beginner": [{"eventname": "LMP2 Fixed", "track": "PortimaoWEC_2023", "scene": "PortimaoWEC",
                  "cars": ["Oreca_07_ELMS_2023"], "duration": "31m30s",
                  "times": [iso(NOW - 1800), iso(NOW + 600), iso(NOW + 3300)]}],
    "advanced": [{"eventname": "Hyper Hour", "track": "Monza", "scene": "MonzaWEC",
                  "cars": ["Ferrari_499P_2023"], "duration": "1h12m30s", "times": [iso(NOW + 1200)]}],
}, "frequency": {"beginner": "15 mins", "advanced": "30 mins"}}

CARS = [
    {"vehFile": "C:\\LMU\\Installed\\Vehicles\\Oreca_07_ELMS_2023\\1.61\\10.VEH",
     "fullPathTree": "ELMS 2025, LMP2_ELMS, Oreca 07", "manufacturer": "Oreca", "owned": True},
    {"vehFile": "C:\\LMU\\Installed\\Vehicles\\Ferrari_499P_2023\\1.6\\50.VEH",
     "fullPathTree": "WEC 2023, Hypercar, Ferrari 499P", "manufacturer": "Ferrari", "owned": False},
]
TRACKS = [
    {"sceneDesc": "PORTIMAOWEC", "displayProperties": {"shortName": "Algarve International Circuit"},
     "shortName": "Algarve International Circuit 1.27", "owned": True},
    {"sceneDesc": "MONZAWEC", "shortName": "Aut\ufffddromo Monza 1.2", "owned": False},
    {"sceneDesc": "SPAELMS", "shortName": "Circuit de Spa-Francorchamps 1.3", "owned": True},
]


def answers() -> dict:
    return {
        "schedule": SCHEDULE,
        "daily_beginner": [race_config("LMP2 Fixed", NOW + 600)],
        "daily_intermediate": None,
        "daily_advanced": [race_config("Hyper Hour", NOW + 1200, "advanced")],
        "weekly": [{"title": "WEC Weekly", "tier": {"name": "weekly", "entryRequirement": {"rank": "Silver", "tier": 2}},
                    "configuration": race_config("x", 0)["configuration"],
                    "events": [{"id": "weekly-1", "starts": iso(NOW + 7200), "registrations": 9, "isRegistered": True,
                                "registrationOpens": iso(NOW - 86400), "entries": [{"name": "Private"}]}]}],
        "special": None,
        "championships": [{
            "id": "champ-1", "name": "Prototype Challenge", "type": "solo", "registrations": 1217, "registered": False,
            "attempts": 3, "dropRounds": 1,
            "tier": {"name": "intermediate", "entryRequirement": {"rank": "Gold", "tier": 1}},
            "entries": [{"name": "Private Person", "avatar": "https://avatars/x.jpg"}],
            "cars": [{"friendly": "Oreca_07_ELMS_2023"}],
            "schedule": [iso(NOW - 3600), iso(NOW + 900)],
            "rounds": [
                {"no": 2, "current": True, "startsAt": iso(NOW - 86400), "endsAt": iso(NOW + 86400),
                 "pointsMultiplier": 2, "track": {"friendly": "Monza", "name": "MonzaWEC",
                           "subItems": [{"name": "Monza", "scn": "MonzaWEC"}]},
                 "sessions": [{"type": "Race", "duration": "30m"}]},
                {"no": 1, "current": False, "startsAt": iso(NOW - 9 * 86400), "endsAt": iso(NOW - 2 * 86400),
                 "track": {"friendly": "Le Mans"}, "sessions": []},
            ]}],
        "championships_upcoming": [],
        "coop": [{"name": "10 Hours of Road Atlanta", "track": "RoadAtlanta", "trackScene": "RoadAtlanta",
                  "length": "10h", "starts": iso(NOW - 86400), "ends": iso(NOW + 86400 * 40)}],
        "hosted": [
            {"name": "Quiet", "track": "Spa_2023", "session": "PRACTICE1", "currentPlayers": 0, "maxPlayers": 20,
             "public": True, "hasPassword": False, "region": "us-west-1", "taskPublicIP": "10.0.0.1",
             "serverPort": 30053, "configuration": {"track": {"friendly": "Spa_2023", "subItems": [
                 {"name": "6 Hours of Spa-Francorchamps", "scn": "SpaELMS"}]}, "cars": [{"friendly": "Ferrari_499P_2023"}]}},
            {"name": "Busy", "track": "Spa_2023", "session": "RACE1", "currentPlayers": 35, "maxPlayers": 38,
             "public": True, "hasPassword": True, "region": "eu-west-1", "taskPublicIP": "10.0.0.2"},
            {"name": "Hidden", "public": False, "currentPlayers": 50},
        ],
    }


def schedule(now_read: float = NOW) -> rs.Schedule:
    return rs.parse_schedule(answers(), rs.parse_car_catalog(CARS), rs.parse_track_catalog(TRACKS), now_read)


def logo(_track):
    return ""


# Parsing
def test_daily_races_merge_schedule_and_details():
    found = schedule()
    beginner = next(event for event in found.events if event.title == "LMP2 Fixed")
    assert beginner.kind == "daily" and beginner.tier == "beginner"
    assert beginner.track == "6 Hours of Portimao"  # folder name of the schedule replaced by the race details
    assert [start.time for start in beginner.starts] == [NOW - 1800, NOW + 600, NOW + 3300]
    assert [start.registrations for start in beginner.starts] == [-1, 2, -1]  # details of listed starts only
    detailed = beginner.starts[1]
    assert (detailed.opens, detailed.event_id, detailed.registered) == (NOW - 1200, "id-LMP2 Fixed", False)
    assert beginner.total == 1890 and beginner.race_seconds == 1200
    assert (beginner.temperature, beginner.rain, beginner.fixed_setup, beginner.max_players) == (22, 30, True, 20)
    assert [session.time_of_day for session in beginner.sessions] == ["19:00", "", "19:20"]
    assert beginner.requirement == rs.Requirement("Bronze", 0) and beginner.entry_type == "daily"
    advanced = next(event for event in found.events if event.title == "Hyper Hour")
    assert advanced.requirement == rs.Requirement("Gold", 0)  # Bronze 0 of a daily tier: tier default
    assert found.missing == ("daily_intermediate", "special")
    assert found.frequency == {"beginner": 900, "advanced": 1800}


def test_requirements_follow_game_menu():
    assert rs.entry_requirement({"name": "intermediate", "entryRequirement": {"rank": "Bronze", "tier": 0}}) == (
        "Silver", 0)
    assert rs.entry_requirement({"name": "weekly", "entryRequirement": {"rank": "Silver", "tier": 2}}) == ("Silver", 2)
    assert rs.entry_requirement({"name": "beginner"}) == ("", 0)
    assert rs.can_enter(rs.Requirement("Silver", 2), "Silver", 2) is True
    assert rs.can_enter(rs.Requirement("Silver", 2), "Silver", 1) is False
    assert rs.can_enter(rs.Requirement("Gold", 0), "Platinum", 0) is True
    assert rs.can_enter(rs.Requirement("Gold", 0), "", 0) is None  # rank unknown
    assert rs.can_enter(rs.Requirement("", 0), "", 0) is True


@pytest.mark.parametrize("text, seconds", [("1h12m30s", 4350), ("90m", 5400), ("30s", 30), ("10h", 36000),
                                           ("0h5m", 300), ("", 0), (None, 0), ("soon", 0), (3, 180)])
def test_durations(text, seconds):
    assert rs.duration_seconds(text) == seconds


@pytest.mark.parametrize("text, shown", [("19h20m", "19:20"), ("9h0m", "09:00"), ("0h0m", "00:00"),
                                         ("25h0m", "01:00"), ("", ""), (None, ""), ("noon", "")])
def test_time_of_day(text, shown):
    assert rs.time_of_day(text) == shown


def test_weekly_championship_coop_and_servers():
    found = schedule()
    weekly = next(event for event in found.events if event.kind == "weekly")
    start = weekly.starts[0]
    assert (start.registrations, start.registered, start.event_id) == (9, True, "weekly-1")
    assert weekly.requirement == ("Silver", 2) and weekly.entry_type == "specialevent"
    champ = found.championships[0]
    assert [item.number for item in champ.rounds] == [1, 2]  # sorted
    assert champ.current_round(NOW).track == "Monza" and champ.requirement == ("Gold", 1)
    assert (champ.key, champ.attempts, champ.drop_rounds, champ.rounds[1].points) == ("champ-1", 3, 1, 2.0)
    assert found.coop[0].length == 36000
    assert [server.name for server in found.servers] == ["Busy", "Quiet"]  # most players first, private left out
    busy = found.servers[0]
    assert (busy.session, busy.password, busy.region) == ("Race", True, "eu-west-1")
    quiet = found.servers[1]
    assert (quiet.track, quiet.scene) == ("6 Hours of Spa-Francorchamps", "SpaELMS")


def test_game_catalogs():
    cars = rs.parse_car_catalog(CARS)
    assert cars["oreca_07_elms_2023"] == rs.CarInfo("LMP2_ELMS", "Oreca 07", True)
    assert rs.classes_of(("Ferrari_499P_2023", "Oreca_07_ELMS_2023", "Unknown"), cars) == ("Hypercar", "LMP2_ELMS")
    assert rs.owned_state(("Ferrari_499P_2023",), cars) is False
    assert rs.owned_state(("Ferrari_499P_2023", "Oreca_07_ELMS_2023"), cars) is True
    assert rs.owned_state(("Unknown",), cars) is None
    tracks = rs.parse_track_catalog(TRACKS)
    assert rs.track_of("PortimaoWEC", "x", tracks) == ("Algarve International Circuit", True)  # version cut
    assert rs.track_of("MonzaWEC", "Monza", tracks) == ("Monza", False)  # name broken by the game (U+FFFD)
    assert rs.track_of("Nowhere", "Nowhere", tracks) == ("Nowhere", None)


def test_unreadable_answers_give_nothing():
    found = rs.parse_schedule({"schedule": {"tiers": [1]}, "hosted": {"a": 1}, "championships": [None, 3, {}],
                               "weekly": "text", "coop": [{"name": 5}]}, {}, {}, NOW)
    assert found.empty


def test_disk_copy_trimmed_and_same_schedule():
    data = rs.cache_data(answers(), rs.parse_car_catalog(CARS), rs.parse_track_catalog(TRACKS), NOW)
    text = json.dumps(data)
    for private in ("10.0.0.1", "serverPort", "Private Person", "avatars", "Somebody", '"sig"'):
        assert private not in text, private
    back = rs.from_cache(json.loads(text))
    assert back is not None
    assert rs.parse_schedule(back[0], back[1], back[2], back[3]) == schedule()
    assert rs.from_cache({"version": 0}) is None and rs.from_cache([]) is None


def test_next_starts_keep_running_race():
    event = next(event for event in schedule().events if event.title == "LMP2 Fixed")
    assert [start.time for start in rs.next_starts(event, NOW)] == [NOW - 1800, NOW + 600, NOW + 3300]  # 31 min
    assert [start.time for start in rs.next_starts(event, NOW + 300)] == [NOW + 600, NOW + 3300]


# Details read on demand
def test_field_counts_only():
    pages = [[{"name": "A#1", "class": "GT3", "dr": {"rank": "Silver", "tier": 1}, "sr": {"rank": "Gold"}},
              {"name": "B", "class": "GT3", "dr": {"rank": "Bronze"}, "sr": {"rank": "Gold"}}],
             [{"name": "C", "class": "LMP3", "dr": {"rank": "Silver"}}, "junk"]]
    field = rs.parse_field(pages, True)
    assert field.drivers == 3 and field.classes == (("GT3", 2), ("LMP3", 1))
    assert field.driver_ranks == (("Silver", 2), ("Bronze", 1)) and field.safety_ranks == (("Gold", 2),)
    assert "A#1" not in repr(field)  # names never kept


def test_championship_detail_and_coop_board():
    detail = rs.parse_championship_detail(
        {"attempts": {"total": 3, "used": 1},
         "events": [{"eventId": "b", "registrations": 5, "time": iso(NOW + 7200)},
                    {"eventId": "a", "registrations": 3, "time": iso(NOW + 3600)}]},
        [{"host": "1.2.3.4", "password": "secret", "currentPlayers": 6, "maxPlayers": 30, "endsAt": iso(NOW + 600)}])
    assert [start.event_id for start in detail.sessions] == ["a", "b"]
    assert (detail.attempts_used, detail.attempts_total) == (1, 3)
    assert detail.practice == (rs.PracticeServer(6, 30, NOW + 600),)
    assert "secret" not in repr(detail) and "1.2.3.4" not in repr(detail)
    entry = {"position": 2, "name": "team x", "metadata": {"drivers": [{"name": "Keenny Hess#12"}, {"name": "Bob"}],
                                                           "vehicleClass": "LMP2", "fastestLap": 72.39,
                                                           "averageLapTime": 80.5}}
    board = rs.parse_coop_board([{"count": 303, "entries": [{"position": 1, "name": "od"}, entry]}], "keenny hess")
    assert board.teams == 303 and [item.position for item in board.top] == [1, 2]
    assert board.mine is not None and board.mine.drivers == ("Keenny Hess#12", "Bob")
    assert rs.parse_coop_board([{"entries": []}], "nobody").mine is None


def test_calendar_file():
    text = rs.ics_text([{"uid": "a b", "title": "LMP2, Fixed; x", "start": NOW, "end": NOW + 1800,
                         "location": "Monza", "description": "line1\nline2 " + "x" * 120}], NOW - 60)
    lines = text.split("\r\n")
    assert lines[0] == "BEGIN:VCALENDAR" and lines[-2] == "END:VCALENDAR" and text.endswith("\r\n")
    assert "SUMMARY:LMP2\\, Fixed\\; x" in lines and "DTSTART:20261102T004000Z" in lines
    assert all(len(line.encode()) <= 75 for line in lines)
    assert any(line.startswith(" ") for line in lines)  # long description folded


# Shared reads
class FakeClient:
    def __init__(self, data):
        self.data = data
        self.no_account = False
        self.paths = []

    def get(self, path, account=""):
        self.paths.append(path)
        key = next((key for key, route in rs.ROUTES.items() if route == path), None)
        if key is None:
            return self.data.get(path.split("?", 1)[0])
        return self.data.get(key)

    player = ("me-id", "Keenny Hess")
    posts: list

    def room(self):
        return 12

    def post(self, path, payload, account=""):
        self.__dict__.setdefault("posts", []).append(payload)
        answer = self.data.get(path)
        return answer(payload) if callable(answer) else answer


def settle_schedule_reads(timeout: float = 10.0):
    """Schedule reads started by earlier tests ended: the app's race watch (made by the first Home or Upcoming
    Races page of the process, read every CHECK_MS while events run) and Home pages read it on page jobs, with
    the patches of whichever test runs then (none: no game). One ending after this test set the state wrote its
    own over it (NO_GAME, read just now: no read due, test_live_read_every_minute_while_page_shows)."""
    from neopedal.jobs import page_pool

    pool = page_pool()
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        with pool._lock:  # nothing waiting, every worker idle: no read about to start either
            if not pool._queue and pool._idle == pool._workers:
                break
        time.sleep(0.01)
    assert info._lock.acquire(timeout=30.0), "schedule read of an earlier test stuck"  # one running ends first
    info._lock.release()


@pytest.fixture
def fresh_info(monkeypatch, tmp_path):
    from neopedal import rank_info
    from neopedal.setting import cfg
    from neopedal.ui.quick import race_watch as rw

    watch = rw._watch
    paused = watch is not None and watch._timer.isActive()
    if paused:  # app's race watch reads nothing during the test (events run by page tests), started again after
        watch._timer.stop()
    settle_schedule_reads()
    monkeypatch.setattr(info, "_state", info.State(rs.EMPTY, "", -1.0, 0))
    monkeypatch.setattr(info, "_disk_read", False)
    monkeypatch.setattr(cfg.path, "config", f"{tmp_path.as_posix()}/")
    monkeypatch.setattr(info, "_game_lists", lambda: (rs.parse_car_catalog(CARS), rs.parse_track_catalog(TRACKS)))
    client = FakeClient(answers())
    monkeypatch.setattr(rank_info, "online_client", lambda: client)
    monkeypatch.setattr(rank_info, "online_enabled", lambda: True)
    yield client
    if paused:
        watch._timer.start()


def test_read_saves_and_waits(fresh_info, monkeypatch):
    state = info.read()  # routes only the Upcoming Races page shows not asked
    asked = len(rs.ROUTES) - len(info.PAGE_ROUTES)
    assert state.status == info.READ and len(state.schedule.events) == 3
    assert len(fresh_info.paths) == asked
    assert not info.due()  # read again only after READ_SECONDS
    assert info.read() is state and len(fresh_info.paths) == asked
    # Next run: disk copy shown before any read
    monkeypatch.setattr(info, "_state", info.State(rs.EMPTY, "", -1.0, 0))
    monkeypatch.setattr(info, "_disk_read", False)
    info.load_disk()
    assert info.state().schedule.championships == state.schedule.championships


def test_read_status_without_game_or_option(fresh_info, monkeypatch):
    from neopedal import rank_info

    fresh_info.data = {}
    monkeypatch.setattr(info, "_game_running", lambda: False)
    assert info.read().status == info.NO_GAME
    fresh_info.no_account = True
    assert info.read(force=True).status == info.NO_ACCOUNT
    monkeypatch.setattr(rank_info, "online_enabled", lambda: False)
    monkeypatch.setattr(info, "public_enabled", lambda: False)  # public page: see test_local_alternatives_2026_11_04
    calls = len(fresh_info.paths)
    assert info.read(force=True).status == info.OFF and len(fresh_info.paths) == calls  # nothing asked
    assert info.read_field("daily", "x") is None and len(fresh_info.paths) == calls


def test_details_read_on_demand(fresh_info, monkeypatch):
    monkeypatch.setattr(info, "FIELD_TAKE", 2)
    fresh_info.data = {
        "api/v1/event/entries/daily/id-1": [{"class": "GT3"}, {"class": "GT3"}],
        "api/v1/championship/champ-1": {"attempts": {"total": 3, "used": 0}, "events": []},
        "api/v1/championships/champ-1/practice/2": [],
        "api/v1/coop/event/leaderboard/list": {"count": 1, "entries": [{"position": 1, "name": "od"}]},
    }
    field = info.read_field("daily", "id-1")  # same page answered each time: pages read until FIELD_PAGES
    assert field is not None and field.drivers == 2 * info.FIELD_PAGES and not field.complete
    assert info.read_championship("champ-1", 2).attempts_total == 3
    assert info.read_coop_board("10 Hours", "me").teams == 1


# Rows, reminders, your laps
def test_event_rows_next_start_and_lock(ui_env):
    from neopedal.ui.quick import schedule_view as view

    found = schedule()
    event = next(event for event in found.events if event.title == "LMP2 Fixed")
    row = view.event_row(event, found, ("Bronze", 1), NOW, logo)
    assert row["startTime"] == NOW + 600 and not row["running"] and row["soon"]  # running one skipped
    assert row["until"] == "in 10 min" and row["registered"] == "2 drivers registered"
    assert row["track"] == "Algarve International Circuit" and row["open"] == 1
    assert row["classes"][0]["full"] == "LMP2_ELMS" and row["owned"] == "" and row["carsOwned"]
    assert row["registration"] == "Registration open" and row["eventId"] == "id-LMP2 Fixed"
    assert row["trackTime"] == "Track time 19:20"
    assert row["weather"] == "22 → 19 °C · Rain 30% → Dry"
    hyper = next(event for event in found.events if event.title == "Hyper Hour")
    row = view.event_row(hyper, found, ("Silver", 3), NOW, logo)
    assert row["open"] == 0 and row["requirement"] == "SR Gold" and row["owned"] == "Car & track not owned"
    assert not row["carsOwned"]
    assert view.event_row(hyper, found, ("", 0), NOW, logo)["open"] == -1
    assert view.event_row(event, found, ("", 0), NOW + 4 * 3600, logo) is None  # all over
    cards = view.home_card(found, ("Silver", 3), NOW, logo, 3)
    assert [card["title"] for card in cards] == ["LMP2 Fixed", "WEC Weekly"]  # Gold race left out
    assert view.until_text(NOW + 3 * 86400, NOW) == "in 3 days"
    assert view.until_text(NOW - 60, NOW, 600) == "Running"
    assert view.length_text(5400) == "1 h 30" and view.length_text(36000) == "10 h"
    weekly = next(event for event in found.events if event.kind == "weekly")
    assert view.event_row(weekly, found, ("Silver", 3), NOW, logo)["registration"] == "Registered"


def test_day_names_and_timeline(ui_env):
    from neopedal.ui.quick import schedule_view as view

    noon = time.mktime((2026, 11, 2, 12, 0, 0, 0, 0, -1))
    assert view.start_text(noon + 3600, noon) == time.strftime("%H:%M", time.localtime(noon + 3600))
    assert view.start_text(noon + 86400, noon).startswith("Tomorrow ")
    assert view.start_text(noon + 3 * 86400, noon) != view.start_text(noon + 86400, noon)
    found = schedule()
    rows = [row for event in found.events if event.kind == "daily"
            if (row := view.event_row(event, found, ("Silver", 3), NOW, logo))]
    line = view.timeline([("beginner", [rows[0]]), ("advanced", rows[1:])], found, NOW)
    assert [lane["tierText"] for lane in line["lanes"]] == ["Beginner", "Advanced"]
    blocks = line["lanes"][0]["items"]
    # start & end only (the page places them from now: lanes unchanged while time goes by)
    places = [((max(block["start"], NOW) - NOW) / line["period"],
               (min(block["end"], NOW + line["period"]) - max(block["start"], NOW)) / line["period"])
              for block in blocks]
    assert [round(at, 3) for at, _width in places] == [0.0, round(600 / 21600, 3), round(3300 / 21600, 3)]
    assert blocks[0]["running"] and all(0 < width <= 1 for _at, width in places) and line["now"] == NOW
    later = view.timeline([("beginner", [rows[0]]), ("advanced", rows[1:])], found, NOW + 5)
    assert later["lanes"] == line["lanes"]  # a tick later: same lanes, nothing made again
    assert all(0 <= mark["at"] <= 1 for mark in line["marks"])


def test_rows_in_french(ui_env):
    from neopedal import i18n
    from neopedal.ui.quick import schedule_view as view

    i18n.set_language("Français")
    try:
        assert view.until_text(NOW + 600, NOW) == "dans 10 min"
        assert view.until_text(NOW - 60, NOW, 600) == "En cours"
        assert view.tier_text("beginner") == "Débutant"
        assert view.weather_text(22, 0).endswith("Sec")
        assert view.frequency_text(900) == "toutes les 15 min"
    finally:
        i18n.set_language("English")


def test_details_worded(ui_env):
    from neopedal.ui.quick import schedule_view as view

    field = view.field_view(rs.FieldLevel(3, (("GT3", 2), ("LMP3", 1)), (("Silver", 2), ("Bronze", 1)), (), False))
    assert field["text"] == "3 drivers registered+" and field["classes"] == "GT3 2 · LMP3 1"
    assert [share["rank"] for share in field["driverRanks"]] == ["Silver", "Bronze"]
    detail = view.championship_detail_view(rs.ChampionshipDetail(
        (rs.Start(NOW - 60, 4), rs.Start(NOW + 600, 5)), 1, 3, (rs.PracticeServer(6, 30, NOW - 10),)), NOW)
    assert [session["registered"] for session in detail["sessions"]] == ["5 drivers"]  # started one left out
    assert detail["attempts"] == "Attempts used: 1 of 3"
    assert detail["practice"] == ["Practice server: 6/30 players"]  # end over: not told
    board = view.coop_board_view(rs.CoopBoard(2, (rs.CoopEntry(1, "od", ("A", "B"), "LMP2", 72.39, 80.5),), None))
    assert board["count"] == "2 teams ranked" and board["top"][0]["fastest"] == "1:12.390" and board["mine"] == {}


def test_reminders_told_once(ui_env, monkeypatch):
    from neopedal.ui.quick import schedule_reminders as sr

    now = [NOW]
    told = []
    from neopedal.ui.notification import message_text

    monkeypatch.setattr(sr.RaceReminders, "tell",
                        staticmethod(lambda message, *args, **kwargs: told.append(message_text(message))))
    reminders = sr.RaceReminders(clock=lambda: now[0])
    reminders.set("race@1", "LMP2 Fixed", "Monza", NOW + 1200, 10)
    reminders.set("race@2", "Old", "", NOW - 60, 10)  # started: never set
    assert reminders.keys() == {"race@1": 10}
    reminders.check()
    assert told == []
    now[0] = NOW + 600
    reminders.check()
    assert told == ["LMP2 Fixed starts in 10 min (Monza)"] and reminders.keys() == {}
    reminders.check()
    assert len(told) == 1
    again = sr.RaceReminders(clock=lambda: now[0])  # saved file read back
    assert again.keys() == {}
    reminders.set("race@3", "Late", "", NOW + 700, 30)
    now[0] = NOW + 700 - 30 * 60 + 660  # app started past the reminder, start to come: told with the real time left
    reminders.check()
    assert told[-1] == "Late starts in 19 min" and reminders.keys() == {}
    reminders.set("race@4", "Gone", "", now[0] + 60, 5)
    now[0] += 120  # start passed while closed: dropped untold
    reminders.check()
    assert len(told) == 2 and reminders.keys() == {}
    assert sr._valid({"key": "a", "start": "x", "minutes": 5}) is None
    assert sr._valid({"key": "a", "start": 1.0, "minutes": True}) is None


def test_your_laps_on_the_track(ui_env):
    from neopedal.ui.quick.schedule_personal import PersonalData, personal_row
    from neopedal.userfile.lap_reference import LapReferenceTable

    data = PersonalData({"Algarve International Circuit": {"GT3 - Porsche": {"pb": 102.314},
                                                           "GT3 - Ferrari": {"pb": 103.0}, "LMP3": {"pb": 0}}},
                        {"GT3 - Porsche": "GT3", "GT3 - Ferrari": "GT3"}, {"Algarve International Circuit": NOW},
                        LapReferenceTable(), {"portimaowec": ("Algarve International Circuit",)},
                        frozenset({"Algarve International Circuit - GT3"}))
    row = personal_row(data, "6 Hours of Portimao", "PortimaoWEC", lambda level: "")
    assert row["known"] and row["statsTrack"] == "Algarve International Circuit"
    assert [(best["vehicleClass"], best["vehicle"], best["best"]) for best in row["bests"]] == [
        ("GT3", "GT3 - Porsche", "1:42.314")]  # fastest of the class, lap time 0 left out
    assert row["bests"][0]["lapsFolder"] == "Algarve International Circuit - GT3"
    assert personal_row(data, "Nowhere", "x", lambda level: "") == {
        "known": False, "statsTrack": "", "bests": [], "lastDriven": 0.0}


# Page
@pytest.fixture
def page(ui_env, fresh_info, monkeypatch):
    from neopedal.ui.quick import schedule_backend, schedule_reminders
    from neopedal.ui.quick.schedule_personal import EMPTY
    from neopedal.ui.race_schedule_viewer import RaceScheduleViewer

    monkeypatch.setattr(schedule_reminders, "_reminders", None)  # file of this test's config folder
    monkeypatch.setattr(time, "time", lambda: NOW)
    monkeypatch.setattr(schedule_backend, "player_safety", lambda: ("Silver", 2))
    monkeypatch.setattr(schedule_backend, "read_personal", lambda: EMPTY)
    monkeypatch.setattr(info, "_state", info.State(schedule(NOW), info.READ, time.monotonic(), 1))
    monkeypatch.setattr(info, "_disk_read", True)
    viewer = RaceScheduleViewer(None)
    viewer.resize(1200, 800)
    viewer.show()
    pump(0.3)
    yield viewer
    viewer.close()
    pump(0.1)
    schedule_reminders._reminders = None


def test_page_shows_every_tab_and_view(qml_warnings, page, monkeypatch):  # noqa: F811
    backend = page.backend
    backend.setOpenOnly(False)
    assert backend.counts == [2, 1, 1, 1, 2]
    assert [group["tier"] for group in backend.daily] == ["beginner", "advanced"]
    assert backend.daily[0]["frequency"] == "every 15 min"
    root = page.view.rootObject()
    for index in range(5):
        backend.setTab(index)
        for view in range(3):
            backend.setView(view)
            pump(0.05)
    assert item_named(root, "serverRow").isVisible()
    backend.setTab(0)
    backend.setView(2)
    pump(0.1)
    assert item_named(root, "timelineBlock") is not None
    assert backend.page_settings()["view"] == 2
    backend.setOpenOnly(True)  # Gold race & Gold 1 championship, locked server hidden
    assert backend.counts == [1, 1, 0, 1, 1]
    QCoreApplication.processEvents()
    assert not qml_warnings, qml_warnings


def test_open_to_me_on_by_default_and_filters(page, monkeypatch):
    backend = page.backend
    assert backend.openOnly  # first use: races your Safety Rank opens
    backend.setOpenOnly(False)
    backend.setSearch("hyper")
    assert backend.counts[0] == 1 and backend.daily[0]["races"][0]["title"] == "Hyper Hour"
    backend.setSearch("")
    backend.toggleClass("LMP2_ELMS")
    assert backend.counts[:3] == [1, 1, 1] and backend.counts[4] == 0
    assert [choice["name"] for choice in backend.classChoices if choice["selected"]] == ["LMP2_ELMS"]
    backend.clearFilters()
    backend.setOwnedOnly(True)  # Ferrari not owned, Monza not owned
    assert backend.counts[0] == 1
    backend.clearFilters()
    backend.setServerSort(2)
    assert [row["name"] for row in backend.servers] == ["Busy", "Quiet"]
    backend.setServerSort(1)
    assert [row["region"] for row in backend.servers] == ["Europe", "US West"]


def test_menu_actions(page, monkeypatch, tmp_path):
    from PySide6.QtWidgets import QFileDialog

    from neopedal.ui.quick import schedule_reminders

    backend = page.backend
    backend.setOpenOnly(False)
    key = backend.daily[0]["races"][0]["key"]
    entries = backend.raceActions(key)
    ids = [entry["id"] for entry in entries]
    # Race first (field), then planning (reminders in one submenu, calendar), then my own stats & calculator
    assert ids[-2:] == ["stats", "prepare"] and ids.index("field") < ids.index("remind:10") < ids.index("export")
    assert [entry["section"] for entry in entries] == sorted(
        (entry["section"] for entry in entries), key=["race", "plan", "mine"].index)
    assert {entry["menu"] for entry in entries if entry["id"].startswith("remind:")} == {
        f"Remind Me Before {next(entry for entry in entries if entry['id'] == 'field')['detailTitle'].split(' · ')[0]}"}
    assert not entries[-2]["enabled"]  # never driven there
    start_key = backend.daily[0]["races"][0]["startKey"]
    backend.runRaceAction(key, "remind:10", "")
    assert schedule_reminders.reminders().minutes_of(start_key) == 10
    assert backend.daily[0]["races"][0]["reminder"] == 10
    assert next(entry for entry in backend.raceActions(key) if entry["id"] == "remind:10")["checked"]
    backend.runRaceAction(key, "remind:0", "")
    assert schedule_reminders.reminders().minutes_of(start_key) == 0
    path = tmp_path / "race.ics"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args, **kwargs: (str(path), ""))
    backend.runRaceAction(key, "export", "")
    assert "BEGIN:VEVENT" in path.read_text(encoding="utf-8")
    champ = backend.championships[0]["key"] if backend.championships else None
    if champ is not None:
        assert backend.calendar_events(champ)[0]["title"].startswith("Prototype Challenge · Round 2")


def test_menu_sections_and_submenus(qml_warnings, page):  # noqa: F811
    from PySide6.QtCore import Q_ARG, Q_RETURN_ARG, QEvent, QMetaObject, QObject

    backend = page.backend
    backend.setOpenOnly(False)
    key = backend.daily[0]["races"][0]["key"]
    backend.runRaceAction(key, "remind:10", "")  # rows made again: personal laps set after
    backend._sources[key][0]["personal"] = {"known": True, "statsTrack": "Portimao", "lastDriven": 0.0, "bests": [
        {"vehicleClass": "Hyper", "vehicle": "Hyper - A", "lapsFolder": "", "seconds": 90.0},
        {"vehicleClass": "LMP3", "vehicle": "LMP3 - B", "lapsFolder": "Portimao - LMP3", "seconds": 99.0}]}
    entries = backend.raceActions(key)
    mine = [entry for entry in entries if entry["section"] == "mine"]
    assert [(entry["menu"], entry["text"], entry["enabled"]) for entry in mine] == [
        ("Driver Stats", "Hyper", True), ("Driver Stats", "LMP3", True), ("Recorded Laps", "Hyper", False),
        ("Recorded Laps", "LMP3", True), ("Prepare Race", "Hyper", True), ("Prepare Race", "LMP3", True)]
    menu = page.view.rootObject().findChild(QObject, "raceMenu")

    def item_at(index):
        return QMetaObject.invokeMethod(menu, "itemAt", Q_RETURN_ARG("QQuickItem*"), Q_ARG("int", index))

    QMetaObject.invokeMethod(menu, "fill", Q_ARG("QVariant", entries))
    items = [item_at(index) for index in range(menu.property("count"))]
    titles = ["|" if "Separator" in item.metaObject().className() else item.property("text") for item in items]
    # Race | reminder submenu & calendar | one submenu per action of my classes
    assert titles[titles.index("|") + 1].startswith("Remind Me Before ") and titles.count("|") == 2
    assert titles[-3:] == ["Driver Stats", "Recorded Laps", "Prepare Race"]
    assert items[titles.index("|") + 1].property("shortcut") == "10 min"  # reminder set shown on its row
    root = page.view.rootObject()

    def made():
        return [item.property("entry")["menu"] for item in root.findChildren(QObject, "raceMenuEntry")]

    assert len(made()) == len(entries) and made().count(titles[titles.index("|") + 1]) == 3 + 1  # with Cancel
    QMetaObject.invokeMethod(menu, "fill", Q_ARG("QVariant", entries))  # filled again: nothing left behind
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert menu.property("count") == len(titles) and len(made()) == len(entries)
    QCoreApplication.processEvents()
    assert not qml_warnings, qml_warnings


def test_championship_coop_and_server_tiles_open_their_menu(qml_warnings, page):  # noqa: F811
    from PySide6.QtCore import QMetaObject, QObject

    from tests.test_audit_g_qml_pages import click, items_of

    backend = page.backend
    backend.setOpenOnly(False)
    root = page.view.rootObject()
    for tab, name, rows in ((2, "championshipCard", backend.championships), (3, "coopCard", backend.coop),
                            (4, "serverRow", backend.servers)):
        backend.setTab(tab)
        backend.setView(0)
        pump(0.1)
        item = next(item for item in items_of(root) if item.objectName() == name and item.isVisible())
        root.setProperty("menuKey", "")
        click(page.view, item)
        pump(0.1)
        key = root.property("menuKey")
        assert key in [row["key"] for row in rows], name
        assert [entry["section"] for entry in backend.raceActions(key)][-1] == "mine"  # track stats at least
        QMetaObject.invokeMethod(root.findChild(QObject, "raceMenu"), "close")
        pump(0.1)
    QCoreApplication.processEvents()
    assert not qml_warnings, qml_warnings


def test_field_read_from_the_menu(page, monkeypatch):
    backend = page.backend
    backend.setOpenOnly(False)
    monkeypatch.setattr(info, "read_field", lambda kind, event_id: rs.FieldLevel(
        2, (("LMP2", 2),), (("Silver", 2),), (), True))
    key = backend.daily[0]["races"][0]["key"]
    backend.runRaceAction(key, "field", "")
    for _ in range(100):
        pump(0.02)
        if f"field:{key}" in backend.details:
            break
    assert backend.details[f"field:{key}"]["text"] == "2 drivers registered"
    assert backend.loadingDetails == []


def test_tile_clicks_never_lost(qml_warnings, page):  # noqa: F811
    """A click on a tile opens its menu, full size at once: menu of another tile open (its press closed it), menu
    fading out after an action or Esc; a click on the tile whose menu is open closes it"""
    from PySide6.QtCore import QMetaObject, QObject, QPoint, QPointF, Qt
    from PySide6.QtTest import QTest

    def hit(item):  # title line of a card, right side: never under its menu
        point = item.mapToScene(QPointF(item.width() - 30, 12))
        QTest.mouseClick(page.view, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                         QPoint(round(point.x()), round(point.y())))
        pump(0.4)

    page.backend.setOpenOnly(False)
    pump(0.2)
    root = page.view.rootObject()
    menu = root.findChild(QObject, "raceMenu")
    first, second = [item for item in items_of(root) if item.objectName() == "raceCard" and item.isVisible()][:2]

    def shown(card):
        return menu.property("visible") and menu.property("toggleSource") == card             and root.property("menuKey") == card.property("race")["key"]

    resized = []  # size changed while shown: the menu blinked (filled once shown, then grew & widened)
    for name in ("width", "height"):
        getattr(menu, f"{name}Changed").connect(lambda *_args: menu.property("visible") and resized.append(1))
    hidden = []  # menu hidden or faded while moved from a tile to another: it blinked
    menu.visibleChanged.connect(lambda: hidden.append(menu.property("visible")))
    hit(first)
    assert shown(first) and not resized
    hidden.clear()
    menu.opacityChanged.connect(lambda: menu.property("opacity") < 1 and hidden.append("faded"))
    hit(second)
    assert shown(second) and not hidden  # one click, moved at once (never closed & opened again)
    hit(first)
    assert shown(first) and not hidden
    for x, y in ((round(root.property("width")) - 40, 200), (round(root.property("width")) - 40, round(root.property("height")) - 20)):
        QTest.mouseClick(page.view, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(x, y))
        pump(0.4)
        assert not menu.property("visible"), (x, y)  # press beside the tiles, or below them: closed
        hit(second)
        assert shown(second)
    hit(second)
    assert not menu.property("visible")  # same tile: closed
    hit(second)
    assert shown(second)
    QMetaObject.invokeMethod(menu, "close")  # action picked: fading out
    pump(0.01)
    hit(second)
    assert shown(second)
    QTest.keyClick(page.view, Qt.Key.Key_Escape)
    pump(0.01)
    hit(first)
    assert shown(first)
    QMetaObject.invokeMethod(menu, "close")
    pump(0.4)
    QCoreApplication.processEvents()
    assert not qml_warnings, qml_warnings


def test_cards_kept_while_time_goes_by(qml_warnings, page, monkeypatch):  # noqa: F811
    """Lists told again at each tick update cards in place: none made again (a click or an open menu was lost to
    it), text moved on; timeline blocks kept too, placed from now"""
    from PySide6.QtCore import QMetaObject, QObject, QPoint, QPointF, Qt
    from PySide6.QtTest import QTest

    backend = page.backend
    backend.setOpenOnly(False)
    pump(0.2)
    root = page.view.rootObject()
    gone = []

    def watched(name):
        found = [item for item in items_of(root) if item.objectName() == name and item.isVisible()]
        for item in found:
            item.destroyed.connect(lambda *_args, item_name=name: gone.append(item_name))
        return found

    cards = watched("raceCard")
    until = [card.property("race")["until"] for card in cards]
    menu = root.findChild(QObject, "raceMenu")
    point = cards[0].mapToScene(QPointF(cards[0].width() - 30, 12))
    QTest.mouseClick(page.view, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                     QPoint(round(point.x()), round(point.y())))
    pump(0.4)
    assert menu.property("visible")
    lists = []
    backend.listsChanged.connect(lambda: lists.append(1))
    for step in range(1, 13):  # a minute of ticks: times to start move on
        monkeypatch.setattr(time, "time", lambda step=step: NOW + step * 5)
        backend.publish_all()
        pump(0.02)
    assert lists and not gone  # told again, nothing made again
    assert [card.property("race")["until"] for card in cards] != until
    assert menu.property("visible") and menu.property("toggleSource") == cards[0]  # menu still open on its card
    QMetaObject.invokeMethod(menu, "close")
    pump(0.4)
    backend.setView(2)
    pump(0.2)
    blocks = watched("timelineBlock")
    x = blocks[1].property("x")
    for step in range(13, 25):
        monkeypatch.setattr(time, "time", lambda step=step: NOW + step * 5)
        backend.publish_all()
        pump(0.02)
    assert not gone and blocks[1].property("x") < x  # same blocks, moved toward now
    QCoreApplication.processEvents()
    assert not qml_warnings, qml_warnings


def test_practice_servers_of_a_race(qml_warnings, page, monkeypatch):  # noqa: F811
    """Practice Servers of the menu: asked as the game asks (tier of a daily race, title of a weekly one), players
    & time left only, shown under the card; none open told"""
    asked = []
    monkeypatch.setattr(info, "_get", lambda path: asked.append(path) or [
        {"currentPlayers": 3, "maxPlayers": 20, "endsAt": iso(NOW + 1200), "host": "10.0.0.1", "password": "x"},
        {"currentPlayers": "20", "maxPlayers": 20, "endsAt": iso(NOW - 60)}, "junk"])
    found = schedule()
    daily = next(event for event in found.events if event.title == "LMP2 Fixed")
    weekly = next(event for event in found.events if event.kind != "daily")
    servers = info.read_practice(daily)
    assert asked[-1] == "api/v1/practice/servers/daily/beginner?eventTitle=LMP2%20Fixed"
    assert servers[0] == rs.PracticeServer(3, 20, NOW + 1200) and len(servers) == 3  # junk: empty server
    info.read_practice(weekly)
    assert asked[-1].startswith(f"api/v1/practice/servers/specialevent/{weekly.title.replace(' ', '%20')}?")
    monkeypatch.setattr(info, "_get", lambda path: None)
    assert info.read_practice(daily) is None  # not answered
    backend = page.backend
    backend.setOpenOnly(False)
    key = backend.daily[0]["races"][0]["key"]
    assert "practice" in [entry["id"] for entry in backend.raceActions(key) if entry["section"] == "race"]
    monkeypatch.setattr(info, "read_practice", lambda event: (rs.PracticeServer(3, 20, NOW + 1200),
                                                             rs.PracticeServer(20, 20, NOW - 60)))
    backend.runRaceAction(key, "practice", "")
    for _ in range(100):
        pump(0.02)
        if f"practice:{key}" in backend.details:
            break
    practice = backend.details[f"practice:{key}"]
    assert practice["servers"][0].startswith("Practice server: 3/20 players until")
    assert practice["servers"][1] == "Practice server: 20/20 players"
    pump(0.1)
    blocks = [item for item in items_of(page.view.rootObject())
              if item.objectName() == "practiceBlock" and item.isVisible()]
    assert len(blocks) == 1
    monkeypatch.setattr(info, "read_practice", lambda event: ())
    backend.runRaceAction(key, "practice", "")  # read again from the menu
    for _ in range(100):
        pump(0.02)
        if f"practice:{key}" in backend.details:
            break
    assert backend.details[f"practice:{key}"]["text"] == "No practice server open now"
    QCoreApplication.processEvents()
    assert not qml_warnings, qml_warnings


def test_page_tells_option_off(qml_warnings, page, monkeypatch):  # noqa: F811
    from neopedal import rank_info

    monkeypatch.setattr(rank_info, "online_enabled", lambda: False)
    monkeypatch.setattr(info, "public_enabled", lambda: False)
    page.backend.readAgain()
    for _ in range(100):
        pump(0.05)
        if page.backend.status.get("off"):
            break
    assert page.backend.status["off"] and page.backend.status["level"] == "warning"
    assert item_named(page.view.rootObject(), "statusNotice").isVisible()
    assert not qml_warnings, qml_warnings


def test_rank_unknown_told(page, monkeypatch):
    from neopedal.ui.quick import schedule_backend

    monkeypatch.setattr(schedule_backend, "player_safety", lambda: ("", 0))
    page.backend.publish_status()
    assert page.backend.status["rank"] == "SR unknown" and not page.backend.status["rankKnown"]


def test_rail_migration_adds_page_once():
    from neopedal.setting_preupdate import preupdate_global_setting

    old = {"application": {"rail_items": "home,race_results_viewer,preset"}}
    preupdate_global_setting((2, 51, 7), old)
    assert old["application"]["rail_items"] == "home,race_schedule_viewer,race_results_viewer,preset"
    preupdate_global_setting((2, 51, 7), old)
    assert old["application"]["rail_items"].count("race_schedule_viewer") == 1
    new = {"application": {"rail_items": "home,tools"}}
    preupdate_global_setting((2, 51, 8), new)
    assert new["application"]["rail_items"] == "home,tools"  # set up after the update: kept
    top = {"application": {"rail_items": "widget,preset"}}  # no Home: at the top
    preupdate_global_setting((2, 51, 7), top)
    assert top["application"]["rail_items"] == "race_schedule_viewer,widget,preset"


# Weekly leaderboards & online results
def board_answer(payload):
    """Leaderboard of 250 drivers (100 a page), the player 150th"""
    names = [f"Driver {rank}" for rank in range(1, 251)]
    if payload.get("aroundUserId"):
        return {"count": 3, "entries": [{"id": "me-id", "name": "Keenny Hess", "rank": 150, "score": 101000}]}
    if payload.get("carClass") == "Hyper":
        return {"count": 0, "entries": []}
    page, limit = payload.get("page", 1), payload["limit"]
    first = (page - 1) * limit
    return {"count": len(names), "entries": [
        {"id": "me-id" if first + index + 1 == 150 else f"id-{first + index}", "name": name,
         "rank": first + index + 1, "score": 100000 + first + index,
         "metadata": {"car": "Car", "class": "GT3", "compound": ["0,Medium", "0,Medium"], "sectors": [30.1, 35.2, 34.7],
                      "dr": {"rank": "Silver", "tier": 3}, "sr": {"rank": "Gold", "tier": 1}, "teamName": "Team"}}
        for index, name in enumerate(names[first:first + limit])]}


RESULT = {
    "eventId": "race-1", "splitNo": 2, "date": iso(NOW - 86400), "eventType": "daily", "tier": "beginner",
    "title": "LMP3 Fixed", "trackScene": "PortimaoWEC",
    "drivers": [{"name": "Keenny Hess", "driverRankAdjustment": 1, "safetyRankAdjustment": -2,
                 "drReasons": [{"impact": 2, "positive": True, "reason": "Race you finished 1st"},
                               {"impact": 0, "positive": False, "reason": "Split Strength"}],
                 "srReasons": [{"impact": 2, "positive": False, "reason": "Race contact"}]}],
    "race": {"sessionNo": 1, "races": [{"results": [
        {"name": "Other", "position": "2", "classPosition": "2", "carClass": "LMP3", "carNumber": "5",
         "bestLapTime": "101.5", "Laps": "9", "finishStatus": "DNF"},
        {"name": "Keenny Hess", "position": "1", "classPosition": "1", "gridPos": "3", "carClass": "LMP3",
         "carNumber": "4", "carType": "Ligier JS P325", "bestLapTime": "100.25", "finishTime": "990.5", "Laps": "10",
         "finishStatus": "Finished Normally"}]}]},
}


def test_leaderboard_keys_like_the_game_menu():
    found = schedule()
    beginner = next(event for event in found.events if event.title == "LMP2 Fixed")
    assert beginner.board == rs.Board("daily", "beginner", "PortimaoWEC", "6HoursofPortimao", "LMP2Fixed")
    weekly = next(event for event in found.events if event.kind == "weekly")
    assert weekly.board.event_type == "specialevent" and weekly.board.title == "WECWeekly"
    round_ = found.championships[0].current_round(NOW)
    assert round_.board == rs.Board("championship", "intermediate", "MonzaWEC", "Monza", "PrototypeChallengeWeek2")
    assert found.championships[0].rounds[0].board is None  # track without layout
    request = beginner.board.request("GT3", 3)
    assert (request["carClass"], request["page"], request["limit"], "aroundUserId" in request) == ("GT3", 3, 100, False)
    assert beginner.board.request(around="me")["aroundUserId"] == "me" and "page" not in beginner.board.request(
        around="me")
    assert rs.leaderboard_class("Hypercar") == "Hyper" and rs.leaderboard_class("GT3") == "GT3"


def test_leaderboard_and_result_parsed():
    board = rs.parse_leaderboard(board_answer({"page": 2, "limit": 100}))
    assert board.drivers == 250 and len(board.entries) == 100
    entry = board.entries[49]
    assert (entry.rank, entry.player_id, entry.seconds, entry.compound) == (150, "me-id", 100.149, "Medium")
    assert entry.driver_rank == ("Silver", 3) and entry.sectors == (30.1, 35.2, 34.7)
    assert rs.parse_leaderboard("junk") is None and rs.parse_leaderboard({}).drivers == 0
    result = rs.parse_result(RESULT)
    assert (result.event_id, result.split, result.tier, result.track) == ("race-1", 2, "beginner", "PortimaoWEC")
    mine = result.rows[0]  # sorted by position
    assert (mine.name, mine.grid, mine.best_lap, mine.laps, mine.dr_change, mine.sr_change) == (
        "Keenny Hess", 3, 100.25, 10, 1.0, -2.0)
    assert mine.reasons == ("Race you finished 1st (+2)", "Split Strength", "Race contact (-2)")
    assert result.rows[1].status == "DNF" and result.rows[1].dr_change is None
    assert rs.parse_result({"eventId": "x"}) is None


def test_player_id_kept_from_sign_in():
    from neopedal.process import raceos

    answers = {raceos.AUTH_URL: (200, json.dumps({"accessToken": "t", "expiresAt": iso(NOW + 3600),
                                                  "player": {"id": "rc-1", "name": "Keenny Hess"}}).encode())}
    client = raceos.RaceOSClient(lambda: "ticket", http=lambda method, url, *args: answers.get(url, (404, b"")),
                                 wall_clock=lambda: NOW)
    assert client.player == ("", "")
    client.sign_in()
    assert client.player == ("rc-1", "Keenny Hess")


def test_place_and_pages_read(fresh_info):
    fresh_info.data[info.LEADERBOARD_ROUTE] = board_answer
    board = rs.Board("daily", "beginner", "Track", "Layout", "Race")
    assert info.read_place(board) == (150, 250)
    assert info.read_place(board, "Hypercar") == (150, 0)  # asked as "Hyper" (nobody in this class here)
    assert fresh_info.posts[-1]["carClass"] == "Hyper"
    page = info.read_leaderboard(board, "", 3)
    assert [entry.rank for entry in page.entries[:2]] == [201, 202] and len(page.entries) == 50
    assert info.read_places({"a": board}) == {"a": (150, 250)}
    fresh_info.data["api/v1/results"] = [RESULT, {"bad": 1}]
    assert [result.event_id for result in info.read_results("daily")] == ["race-1"]
    assert info.results_take("specialevent") == 2 and info.results_take("daily") == info.RESULTS_TAKE


def test_leaderboard_and_result_rows(ui_env):
    from neopedal.ui.quick import schedule_view as view

    assert view.place_text(1204, 17836) == "#1,204 of 17,836" or view.place_text(1204, 17836).startswith("#1")
    assert view.place_text(0, 100) == "" and view.place_text(3, 0) == "#3"
    rows = view.leaderboard_rows(rs.parse_leaderboard(board_answer({"page": 2, "limit": 100})), "me-id")
    assert rows[0]["gap"] == "" and rows[1]["gap"] == "+0.001" and rows[49]["me"] and not rows[0]["me"]
    assert rows[0]["ranks"] == "DR Silver 3 · SR Gold 1" and rows[0]["carLine"] == "Car · Team · Medium"
    shown = view.result_view(rs.parse_result(RESULT), schedule(), "keenny hess#12", NOW, logo)
    assert shown["track"] == "Algarve International Circuit" and shown["split"] == "Split 2"
    assert shown["mine"]["position"] == "P1" and shown["mine"]["dr"] == "+1" and shown["mine"]["srTone"] == -1
    assert shown["rows"][1]["status"] == "DNF" and shown["rows"][1]["lapsLine"] == "9 laps · DNF"
    assert shown["rows"][0]["nameLine"] == "#4 Keenny Hess" and shown["rows"][0]["ranksLine"] == "DR +1 · SR -2"


def test_leaderboard_window_every_page(qml_warnings, page, monkeypatch):  # noqa: F811
    backend = page.backend
    backend.setOpenOnly(False)
    info.state()  # schedule of the fixture
    monkeypatch.setattr(info, "read_leaderboard",
                        lambda board, cls="", number=1: rs.parse_leaderboard(board_answer(
                            {"page": number, "limit": 100, "carClass": rs.leaderboard_class(cls)})))
    monkeypatch.setattr(info, "read_place", lambda board, cls="": (150, 250) if cls != "Hypercar" else (0, 0))
    monkeypatch.setattr(info, "read_places", lambda boards, _asked=None: {key: (150, 250) for key in boards})
    monkeypatch.setattr(info, "player_id", lambda: "me-id")
    backend.read_places_due(force=True)
    for _ in range(100):
        pump(0.02)
        if backend.daily and backend.daily[0]["races"][0]["place"]:
            break
    race = backend.daily[0]["races"][0]
    assert race["place"] and "board" in [entry["id"] for entry in backend.raceActions(race["key"])]

    def wait_board():
        for _ in range(100):
            pump(0.02)
            if not backend.board.get("loading"):
                return

    backend.runRaceAction(race["key"], "board", "")
    wait_board()
    board = backend.board
    assert board["open"] and board["page"] == 2 and board["pages"] == 3  # page of your place
    assert board["myPage"] == 2 and any(row["me"] for row in board["rows"])
    backend.boardPage(3)
    wait_board()
    assert backend.board["page"] == 3 and backend.board["rows"][0]["rank"] == "201"
    backend.boardPage(9)  # past the last page: nothing asked
    assert backend.board["page"] == 3
    backend.boardMine()
    wait_board()
    assert backend.board["page"] == 2
    backend.boardClass("Hypercar")
    wait_board()
    assert backend.board["rows"] == [] and backend.board["myPlace"] == "Not ranked this week"
    from PySide6.QtCore import QObject

    popup = page.view.rootObject().findChild(QObject, "boardPopup")  # in the overlay layer: not a child item
    assert popup is not None and popup.property("visible")  # "opened" waits for the end of its animation
    backend.closeBoard()
    assert backend.board == {"open": False}
    pump(0.1)
    assert not qml_warnings, qml_warnings


def test_reasons_in_app_language(ui_env):
    from neopedal import i18n
    from neopedal.ui.quick import schedule_view as view

    assert view.reason_text("Race 5 clean laps (+2)") == "Race: 5 clean laps (+2)"
    assert view.reason_text("Quali contact with Barrier (x3) (-1)") == "Qualifying: barrier contact (x3) (-1)"
    assert view.reason_text("Race contact with another vehicle John Mac#4393 (x2)") == "Race: contact with John Mac#4393 (x2)"
    assert view.reason_text("Qualifying you finished 3rd of 20") == "Qualifying: finished 3 of 20"
    assert view.reason_text("Something new (+1)") == "Something new (+1)"
    i18n.set_language("Français")
    try:
        assert view.reason_text("Race 5 clean laps (+2)").startswith("Course")
        assert view.reason_text("You were expected to finish 4th") == "Place attendue : 4"
    finally:
        i18n.set_language("English")


def test_standing_profile_server_and_progress(ui_env):
    from neopedal.ui.quick import schedule_view as view

    board = rs.parse_leaderboard(board_answer({"page": 1, "limit": 100}))
    assert view.standing_text(150, 250, 100.5, board) == "Top 60% · 0.500 s to the first"
    assert view.standing_text(1, 2000, 0, None) == "Top 0.1%" and view.standing_text(0, 10, 0, None) == ""
    assert rs.percentile(900, 300) == 100.0
    shown = view.profile_view(rs.Profile("A#1", "FR", ("Gold", 1), ("Silver", 2), "sr-clean"))
    assert (shown["nationality"], shown["dr"], shown["sr"]) == ("France", "Gold 1", "Silver 2")
    assert view.profile_view(None) == {"error": "Profile not found"}
    server = schedule().servers[1]
    assert view.server_row(server, schedule(), logo)["track"] == "Circuit de Spa-Francorchamps"
    result = rs.parse_result(RESULT)
    progress = view.championship_progress([result._replace(title="Sprint: Week 2"), result._replace(title="Sprint: Week 2"),
                                           result._replace(title="Sprint: Week 4")], 8, "Keenny Hess")
    assert progress["summary"] == "2 of 8 rounds driven"
    assert [(line["round"], line["races"], line["best"]) for line in progress["rounds"]] == [
        ("Round 2", "2 races", "P1"), ("Round 4", "1 race", "P1")]
    assert view.csv_text(["a", "b"], [["1", "x,y"]]) == 'a,b\n1,"x,y"\n'


def test_team_race_row_found_by_its_drivers(ui_env):
    from neopedal.ui.quick import schedule_view as view

    team = json.loads(json.dumps(RESULT))
    team["drivers"] = []
    team["teams"] = [{"name": "Team Falcon", "teamMembers": [{"name": "Somebody"}, {"name": "Keenny Hess"}]}]
    row = team["race"]["races"][0]["results"][1]
    row["name"], row["teamName"] = "Falcon #26", "Team Falcon"
    shown = view.result_view(rs.parse_result(team), schedule(), "Keenny Hess", NOW, logo)
    assert shown["mine"]["position"] == "P1" and shown["mine"]["drivers"] == "Somebody, Keenny Hess"
    assert shown["mine"]["reasons"] == "No detail given by RaceControl"


def test_friends_profile_find_and_progress_read(fresh_info):
    fresh_info.data[info.LEADERBOARD_ROUTE] = board_answer
    fresh_info.data["api/v1/player/friends-list"] = [{"id": "f-1", "name": "Friend"}, {"name": "no id"}]
    fresh_info.data["api/v1/players"] = [{"id": "me-id", "name": "Keenny Hess", "profile": {"nationality": "FR"},
                                          "driverRank": {"rank": "Silver", "tier": 2}}]
    monkey_friends = info._friends
    try:
        board = rs.Board("daily", "beginner", "Track", "Layout", "Race")
        assert info.read_friends() == (rs.Friend("f-1", "Friend"),)
        entries = info.read_friend_places(board)
        assert [entry.player_id for entry in entries] == ["me-id"]  # the friend is not ranked
        assert info.read_profile("Keenny Hess#12").nationality == "FR"
        assert info.find_driver(board, "", "Keenny Hess") == 150
        assert info.find_driver(board, "", "Nobody") == 0
        fresh_info.data["api/v1/results"] = [{**RESULT, "title": "Sprint: Week 3"}, {**RESULT, "title": "Other"}]
        assert [result.title for result in info.read_championship_results("Sprint")] == ["Sprint: Week 3"]
    finally:
        info._friends = monkey_friends


def test_leaderboard_friends_find_export_profile(page, monkeypatch, tmp_path):
    from PySide6.QtWidgets import QFileDialog

    backend = page.backend
    backend.setOpenOnly(False)
    monkeypatch.setattr(info, "read_leaderboard",
                        lambda board, cls="", number=1: rs.parse_leaderboard(board_answer({"page": number, "limit": 100})))
    monkeypatch.setattr(info, "read_place", lambda board, cls="": (150, 250))
    monkeypatch.setattr(info, "player_id", lambda: "me-id")
    asked = []
    monkeypatch.setattr(info, "read_friend_places", lambda board, cls="": asked.append(1) or list(
        rs.parse_leaderboard(board_answer({"page": 2, "limit": 100})).entries[49:50]))
    monkeypatch.setattr(info, "find_driver", lambda board, cls, name: 230 if name == "Driver 230" else 0)
    monkeypatch.setattr(info, "read_profile", lambda name: rs.Profile(name, "DE", ("Bronze", 3), ("Gold", 1), ""))

    def wait(condition):
        for _ in range(150):
            pump(0.02)
            if condition():
                return

    key = backend.daily[0]["races"][0]["key"]
    backend.openBoard(key)
    wait(lambda: not backend.board.get("loading"))
    assert backend.board["standing"].startswith("Top 60%")
    assert backend.board["classes"][0]["name"] == "LMP2_ELMS" and backend.board["classes"][0]["label"]
    reads = []
    monkeypatch.setattr(info, "read_leaderboard", lambda board, cls="", number=1: reads.append(number) or (
        rs.parse_leaderboard(board_answer({"page": number, "limit": 100}))))
    backend.boardPage(2)
    wait(lambda: not backend.board.get("loading"))
    backend.boardPage(1)  # read a moment ago (page opened first): no new ask
    wait(lambda: not backend.board.get("loading"))
    assert reads == [2] and backend.board["page"] == 1
    backend.boardFriends(True)
    wait(lambda: not backend.board.get("loading"))
    assert asked and [row["me"] for row in backend.board["rows"]] == [True] and backend.board["friends"]
    monkeypatch.setattr(info, "read_leaderboard",
                        lambda board, cls="", number=1: rs.parse_leaderboard(board_answer({"page": number, "limit": 100})))
    backend.boardFind("Driver 230")
    wait(lambda: not backend.board.get("loading") and backend.board.get("page") == 3)
    assert backend.board["page"] == 3 and backend.board["found"].startswith("#230")
    backend.boardFind("Nobody")
    wait(lambda: not backend.board.get("loading"))
    assert backend.board["found"] == "Nobody not ranked here"
    path = tmp_path / "board.csv"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args, **kwargs: (str(path), ""))
    backend.boardExport()
    assert path.read_text(encoding="utf-8").startswith("Rank,Driver,Lap")
    backend.showProfile("Driver 7")
    wait(lambda: not backend.profile.get("loading"))
    assert backend.profile["nationality"] == "Germany" and backend.profile["open"]
    backend.closeProfile()
    backend.closeBoard()


def test_places_asked_less_when_not_ranked(page, monkeypatch):
    backend = page.backend
    asked = []
    monkeypatch.setattr(info, "read_places", lambda boards, _asked=None: asked.append(sorted(boards)) or {
        key: (0, 0) for key in boards})
    backend.read_places_due(force=True)
    for _ in range(100):
        pump(0.02)
        if asked and not backend.jobs.is_busy("places"):
            break
    assert asked and asked[0]
    backend._places_time = -1e9  # due again
    backend.read_places_due()
    pump(0.2)
    assert len(asked) == 1  # nowhere ranked: not asked again before UNRANKED_SECONDS
    assert info.places() == backend._places


def test_timeline_hours_and_championship_progress(qml_warnings, page, monkeypatch):  # noqa: F811
    backend = page.backend
    backend.setOpenOnly(False)
    backend.setTimelineHours(12)
    assert backend.timeline["hours"] == 12 and backend.page_settings()["timeline_hours"] == 12
    backend.setTimelineHours(5)  # not a choice
    assert backend.timelineHours == 12
    monkeypatch.setattr(info, "read_championship_results", lambda name: [
        rs.parse_result(RESULT)._replace(title=f"{name}: Week 2")])
    monkeypatch.setattr(info, "player_name", lambda: "Keenny Hess")
    key = backend.championships[0]["key"]
    backend.readProgress(key)
    for _ in range(100):
        pump(0.02)
        if f"progress:{key}" in backend.details:
            break
    assert backend.details[f"progress:{key}"]["rounds"][0]["best"] == "P1"
    pump(0.1)
    assert not qml_warnings, qml_warnings


# Results & Replays: races driven online
@pytest.fixture
def online(ui_env, fresh_info, monkeypatch):
    from neopedal.ui.quick.online_results import OnlineResultsBackend

    monkeypatch.setattr(info, "player_name", lambda: "Keenny Hess")
    monkeypatch.setattr(info, "_state", info.State(schedule(NOW), info.READ, time.monotonic(), 1))
    backend = OnlineResultsBackend(None)
    yield backend
    backend.release()


def wait_online(backend):
    for _ in range(150):
        pump(0.02)
        if not backend.state["loading"] and not backend.jobs.is_busy("laps"):
            return


def test_online_results_list_and_race(online, monkeypatch, tmp_path):
    from PySide6.QtWidgets import QFileDialog

    from neopedal.ui.quick.online_results import local_session

    asked = []
    older = rs.parse_result({**RESULT, "eventId": "race-0", "date": iso(NOW - 3 * 86400)})
    monkeypatch.setattr(info, "read_results", lambda kind, page=1: asked.append((kind, page)) or (
        [rs.parse_result(RESULT)] * info.results_take(kind) if page == 1 else [older]))
    with_laps = json.loads(json.dumps(RESULT))
    with_laps["race"]["races"][0]["results"][1]["laps"] = [{"lapTime": "101", "p": "2"}, {"lapTime": "100", "p": "1"}]
    monkeypatch.setattr(info, "read_result", lambda event_id, split: rs.parse_result(with_laps))
    online.list_shown(True)
    wait_online(online)
    assert asked == [("daily", 1)] and len(online.rows) == 1 and online.state["more"]
    assert online.selected["title"] == "LMP3 Fixed" and online.chart["laps"] == 2  # laps read for the race picked
    assert online.chart["lines"][0]["me"] or any(line["me"] for line in online.chart["lines"])
    online.more()
    wait_online(online)
    assert len(online.rows) == 2 and not online.state["more"]
    assert online.summary["figures"][0]["value"] == "2"  # wins
    online.setKind(2)
    wait_online(online)
    assert asked[-1] == ("championship", 1) and online.state["kind"] == 2
    path = tmp_path / "race.csv"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args, **kwargs: (str(path), ""))
    online.exportClassification()
    assert path.read_text(encoding="utf-8").splitlines()[1].startswith("1,1,LMP3,4,Keenny Hess")
    track = "Algarve International Circuit"
    sessions = [type("Info", (), {"kind": "Race", "time": NOW - 86400 + 1500, "path": "race.xml", "track": track,
                                  "course": track})(),
                type("Info", (), {"kind": "Practice", "time": NOW - 86400, "path": "practice.xml", "track": track,
                                  "course": track})()]
    assert local_session(rs.parse_result(RESULT), sessions, track) == "race.xml"
    assert local_session(rs.parse_result(RESULT), sessions[1:], track) == ""
    wanted = []
    online.sessionWanted.connect(wanted.append)
    online.sessions = lambda: sessions
    online.openLocal()
    assert wanted == ["race.xml"]
    online.sessions = list
    online.openLocal()
    assert online.state["note"] == "No results file of this race on this computer"


def test_online_rank_lines():
    from neopedal.ui.quick.online_results import rank_level, rank_lines

    assert rank_level(("Bronze", 1)) == 1 and rank_level(("Platinum", 3)) == 12 and rank_level(("", 0)) == -1
    first = rs.parse_result(RESULT)
    ranked = json.loads(json.dumps(RESULT))
    ranked["drivers"][0]["driverRank"] = {"rank": "Silver", "tier": 2}
    ranked["drivers"][0]["safetyRank"] = {"rank": "Gold", "tier": 1}
    second = rs.parse_result(ranked)
    lines = rank_lines([second, second], "Keenny Hess")
    assert lines["drText"] == "Silver 2" and [point["x"] for point in lines["dr"]] == [0.0, 1.0]
    assert rank_lines([first], "Keenny Hess") == {}


def test_results_page_online_list(qml_warnings, ui_env, fresh_info, monkeypatch):  # noqa: F811
    from neopedal.ui.race_results_viewer import RaceResultsViewer

    monkeypatch.setattr(info, "player_name", lambda: "Keenny Hess")
    monkeypatch.setattr(info, "read_results", lambda kind, page=1: [rs.parse_result(RESULT)] if page == 1 else [])
    monkeypatch.setattr(info, "read_result", lambda event_id, split: None)
    viewer = RaceResultsViewer(None)
    viewer.resize(1300, 850)
    viewer.show()
    pump(0.3)
    try:
        viewer.show_online()
        wait_online(viewer.online)
        root = viewer.view.rootObject()
        assert viewer.backend.listMode == 2 and len(viewer.online.rows) == 1
        assert item_named(root, "onlineResultView").isVisible()
        assert item_named(root, "onlineClassification").isVisible()
        viewer.backend.setListMode(0)
        pump(0.1)
        assert not item_named(root, "onlineResultView").isVisible()
        assert not qml_warnings, qml_warnings
    finally:
        viewer.close()
        pump(0.1)


# Registration from the page (game menu requests, answers simulated: never a real registration)
OVERVIEW = {
    "id": "id-LMP2 Fixed", "type": "daily", "teamEvent": False, "registrations": [{"driver": {"id": "other"}}],
    "configuration": {"content": {"cars": [
        {"friendly": "Oreca_07_ELMS_2023", "sig": "s", "subItems": [
            {"name": "Vector #10:LM", "veh": "10.VEH"}, {"name": "Oreca Custom Team 2025 #397", "veh": "397.VEH"},
            {"name": "Unowned #11", "veh": "11.VEH"}]},
        {"friendly": "Ferrari_499P_2023", "subItems": [{"name": "AF Corse #50", "veh": "50.VEH"}]},
    ]}},
}
REGISTER_CARS = [*CARS,
                 {"vehFile": "C:\\LMU\\Installed\\Vehicles\\Oreca_07_ELMS_2023\\1.61\\397.VEH",
                  "fullPathTree": "ELMS 2025, LMP2_ELMS, Oreca 07", "owned": True},
                 {"vehFile": "C:\\LMU\\Installed\\Vehicles\\Oreca_07_ELMS_2023\\1.61\\11.VEH",
                  "fullPathTree": "ELMS 2025, LMP2_ELMS, Oreca 07", "owned": False}]


def test_registration_marked_cars_and_request():
    mine = race_config("LMP2 Fixed", NOW + 600)
    mine["registrations"] = [{"driver": {"id": "other", "name": "Somebody"}}, {"driver": {"id": "me-id"}}]
    team = {"registrations": [{"team": {"lineup": {"drivers": [{"driverId": "me-id", "name": "Me"}]}}}]}
    marked = rs.mark_registered({"list": [mine, team, race_config("Other", NOW)]}, "me-id")
    assert [item.get("registered") for item in marked["list"]] == [True, True, None]
    assert rs.mark_registered(mine, "") is mine  # player unknown: answers as given
    kept = rs.trimmed(marked)  # disk copy: the mark, never names
    assert kept["list"][0]["registered"] is True and kept["list"][0]["registrations"] == 2
    assert "Somebody" not in json.dumps(kept)
    data = {**answers(), "daily_beginner": [marked["list"][0]]}
    found = rs.parse_schedule(data, rs.parse_car_catalog(CARS), rs.parse_track_catalog(TRACKS), NOW)
    start = next(item for event in found.events if event.title == "LMP2 Fixed" for item in event.starts
                 if item.event_id == "id-LMP2 Fixed")
    assert start.registered
    # Cars: owned liveries of the event only, custom team liveries left out (game team car flow)
    cars = rs.car_choices(OVERVIEW, REGISTER_CARS)
    assert cars == (rs.CarChoice("10.VEH", "LMP2_ELMS", "Oreca 07", "Vector #10:LM"),)
    request = rs.register_request(OVERVIEW, cars[0])
    assert request == {"eventType": "daily", "eventId": "id-LMP2 Fixed", "carClass": "LMP2_ELMS", "team": None,
                       "car": {"friendly": "Oreca_07_ELMS_2023", "sig": "s",
                               "subItems": [{"name": "Vector #10:LM", "veh": "10.VEH"}]}}
    assert rs.register_request({**OVERVIEW, "teamEvent": True}, cars[0]) is None
    assert rs.register_request(OVERVIEW, cars[0]._replace(veh="99.VEH")) is None
    assert rs.answer_ok(200, {"status": "OK"}) and not rs.answer_ok(400, {"status": "ERROR"})
    assert not rs.answer_ok(200, {"status": "ERROR"})
    assert rs.answer_message({"status": "ERROR", "message": "Closed", "errors": ["Too late", "x"]}) == "Closed Too late"
    assert rs.answer_message(None) == ""


def test_raceos_send_keeps_refusal_answer():
    from neopedal.process import raceos

    sent = []

    def http(method, url, body, headers, timeout):
        if url == raceos.AUTH_URL:
            return 200, json.dumps({"accessToken": "t", "expiresAt": iso(NOW + 3600), "player": {}}).encode()
        sent.append((method, url, json.loads(body) if body else None))
        return 400, json.dumps({"status": "ERROR", "message": "Registration closed"}).encode()

    client = raceos.RaceOSClient(lambda: "ticket", http=http, wall_clock=lambda: NOW)
    assert client.send("DELETE", rs.UNREGISTER_ROUTE, {"eventId": "e"}) == (
        400, {"status": "ERROR", "message": "Registration closed"})
    assert sent[-1] == ("DELETE", f"{raceos.RACEOS_URL}/{rs.UNREGISTER_ROUTE}", {"eventId": "e"})
    assert client.post(rs.REGISTER_ROUTE, {}) is None  # reads still give nothing on an error status


def test_register_and_leave_through_service(fresh_info, monkeypatch):
    from neopedal import rank_info

    monkeypatch.setattr(info, "_registered", {})
    sent = []
    replies = {"POST": (200, {"status": "OK"}), "DELETE": (200, {"status": "OK"})}

    def send(method, path, payload, account=""):
        sent.append((method, path, payload))
        return replies[method]

    fresh_info.send = send
    monkeypatch.setattr(info, "FORCE_SECONDS", 0.0)  # refreshes asked one after another all read
    info.read()
    fresh_info.data["api/v1/event/overview"] = OVERVIEW

    def registered() -> bool:
        return next(start.registered for event in info.state().schedule.events for start in event.starts
                    if start.event_id == "id-LMP2 Fixed")

    event = info.read_overview("daily", "id-LMP2 Fixed")
    assert event is OVERVIEW and fresh_info.posts[-1] == {"game": "lmu", "eventType": "daily",
                                                         "eventId": "id-LMP2 Fixed"}
    car = rs.car_choices(event, REGISTER_CARS)[0]
    serial = info.state().serial
    assert info.register(event, car) == (True, "")
    assert sent[-1][:2] == ("POST", rs.REGISTER_ROUTE) and registered() and info.state().serial > serial
    info.read(force=True)  # lists not caught up yet: still told registered
    assert registered()
    mine = race_config("LMP2 Fixed", NOW + 600)
    mine["registrations"] = [{"driver": {"id": "me-id"}}]
    fresh_info.data["daily_beginner"] = [mine]
    info.read(force=True)  # lists agree: page change forgotten, lists followed from now on
    assert registered() and info._registered_now() == {}
    assert info.unregister("daily", "id-LMP2 Fixed") == (True, "")
    assert sent[-1] == ("DELETE", rs.UNREGISTER_ROUTE, {"eventType": "daily", "eventId": "id-LMP2 Fixed"})
    assert not registered()
    # Refused: RaceControl reason given, nothing changed
    replies["POST"] = (400, {"status": "ERROR", "message": "Closed", "errors": ["Registration closed"]})
    assert info.register(event, car) == (False, "Closed Registration closed")
    assert not registered()
    assert info.register({**OVERVIEW, "teamEvent": True}, car) == (False, "")  # never sent
    monkeypatch.setattr(rank_info, "online_enabled", lambda: False)
    count = len(sent)
    assert info.unregister("daily", "id-LMP2 Fixed") == (False, "") and len(sent) == count


def test_register_and_leave_from_the_menu(qml_warnings, page, monkeypatch):  # noqa: F811
    from neopedal.ui.quick import dialogs, replays_common, schedule_reminders

    backend = page.backend
    backend.setOpenOnly(False)
    race = backend.daily[0]["races"][0]
    key = race["key"]
    ids = [entry["id"] for entry in backend.raceActions(key)]
    assert ids[0] == "register" and ids.index("register") < ids.index("remind:5")  # first: the menu's main action
    assert next(entry for entry in backend.raceActions(key) if entry["id"] == "register")["enabled"]
    weekly = backend.events[0]["races"][0]["key"] if "races" in backend.events[0] else backend.events[0]["key"]
    assert "unregister" in [entry["id"] for entry in backend.raceActions(weekly)]  # registered in RaceControl lists
    # Game closed: started first (RaceControl signs in with it)
    monkeypatch.setattr(info, "_state", info.state()._replace(status=info.NO_GAME))
    started = []
    monkeypatch.setattr(replays_common, "start_game", lambda: started.append(1) or True)
    assert "launch" in [entry["id"] for entry in backend.raceActions(key)]
    backend.runRaceAction(key, "launch", "")
    assert started == [1]
    backend.publish_status()
    assert backend.status["noGame"] is True
    monkeypatch.setattr(info, "_state", info.state()._replace(status=info.READ))
    # Register: event & cars read, car chosen, reminder set before the start
    monkeypatch.setattr(info, "read_overview", lambda kind, event_id: OVERVIEW)
    monkeypatch.setattr(info, "game_cars", lambda: REGISTER_CARS)
    monkeypatch.setattr(info, "player_id", lambda: "me-id")
    asked = []
    reply = [(False, "Closed")]
    monkeypatch.setattr(info, "register", lambda event, car: asked.append((event["id"], car.veh)) or reply[0])
    backend.runRaceAction(key, "register", "")
    assert backend.registration["open"] is True and backend.registration["loading"] is True
    for _ in range(100):
        pump(0.02)
        if backend.registration.get("loading") is False:
            break
    assert backend.registration["cars"] == [{"index": 0, "vehicleClass": "LMP2_ELMS", "model": "Oreca 07",
                                             "livery": "Vector #10:LM"}]
    from PySide6.QtCore import QObject

    dialog = page.view.rootObject().findChild(QObject, "registrationDialog")
    pump(0.2)
    assert dialog.property("opened") and dialog.property("chosenIndex") == 0  # first class, car & livery chosen
    assert dialog.property("chosenModel") == "Oreca 07"
    backend.confirmRegistration(0)
    for _ in range(100):
        pump(0.02)
        if backend.registration.get("busy") is False:
            break
    assert asked == [("id-LMP2 Fixed", "10.VEH")] and "Closed" in backend.registration["error"]
    assert backend.registration["open"] is True  # refusal told in the dialog
    reply[0] = (True, "")
    backend.confirmRegistration(0)
    for _ in range(100):
        pump(0.02)
        if backend.registration.get("open") is False:
            break
    assert backend.registration == {"open": False}
    pump(0.3)
    assert not dialog.property("visible")
    assert schedule_reminders.reminders().minutes_of(race["startKey"]) == 10
    # Already registered, team race, no car owned: told, nothing to choose
    for event, cars, words in ((dict(OVERVIEW, registrations=[{"driver": {"id": "me-id"}}]), REGISTER_CARS,
                                "already registered"),
                               (dict(OVERVIEW, teamEvent=True), REGISTER_CARS, "Team races"),
                               (OVERVIEW, CARS[1:], "None of the cars")):
        backend.set_registration({"open": True, "eventId": "id-LMP2 Fixed"})
        backend.registration_read("id-LMP2 Fixed", event, cars)
        assert words in backend.registration["error"] and backend.registration["cars"] == []
    backend.closeRegistration()
    pump(0.1)
    # Leave: confirmed first, then RaceControl asked
    left = []
    monkeypatch.setattr(dialogs, "confirm", lambda parent, title, text, action, on_result, **kwargs: on_result(True))
    monkeypatch.setattr(info, "unregister", lambda kind, event_id: left.append((kind, event_id)) or (True, ""))
    backend.runRaceAction(weekly, "unregister", "")
    for _ in range(100):
        pump(0.02)
        if left:
            break
    assert left == [("specialevent", "weekly-1")]
    QCoreApplication.processEvents()
    assert not qml_warnings, qml_warnings


def test_registration_entry_states(page, monkeypatch):
    backend = page.backend
    backend.setOpenOnly(False)
    row, source = backend._sources[backend.daily[0]["races"][0]["key"]]
    chosen = backend.menu_start(row, source)
    entry = backend.registration_entries(row, source, {**chosen, "opens": NOW + 600}, NOW)[0]
    assert entry["id"] == "register" and not entry["enabled"] and entry["text"].startswith("Registration Opens")
    entry = backend.registration_entries(row, source._replace(team=True), chosen, NOW)[0]
    assert entry["id"] == "register" and not entry["enabled"]
    entry = backend.registration_entries({**row, "open": 0}, source, chosen, NOW)[0]
    assert entry["id"] == "register" and not entry["enabled"]  # Safety Rank too low
    entry = backend.registration_entries(row, source, {**chosen, "eventId": ""}, NOW)[0]
    assert not entry["enabled"]  # start without event id (beyond the next races listed)
    monkeypatch.setattr(info, "_state", info.state()._replace(status=info.OFF))
    assert not backend.registration_entries(row, source, chosen, NOW)[0]["enabled"]


def test_popups_parented_to_the_page_overlay():
    """Leaderboard, profile & registration windows on the overlay of the page's window now (page made before the
    app shows it: a popup's own Overlay.overlay stayed on the former window, no parent, never opened: Weekly
    Leaderboard and Register… did nothing in the app; offscreen tests keep one window, see TpDialogHost)"""
    from pathlib import Path

    import neopedal

    text = (Path(neopedal.__file__).parent / "ui" / "qml" / "analysis" / "RaceSchedule.qml").read_text(encoding="utf-8")
    for name in ("boardPopup", "profilePopup", "registrationDialog"):
        block = text[text.index(f'objectName: "{name}"'):][:600]
        assert "parent: page.Overlay.overlay" in block, name
    assert "parent: Overlay.overlay" not in text


# Live reading: page every LIVE_READ_SECONDS, fields of close starts, your races followed (answers simulated)
def test_split_parsed_without_address():
    split = rs.parse_split({"splitNo": "2", "numOfSplits": 3,
                            "server": {"host": "10.0.0.9", "port": 64290, "password": "secret", "auth": "x"}})
    assert split == rs.SplitState(True, 2, 3)
    assert "10.0.0.9" not in repr(split) and "secret" not in repr(split)  # ready or not: address never kept
    assert rs.parse_split({"server": {"host": "10.0.0.9", "password": ""}}) == rs.SplitState(False)
    assert rs.parse_split({}) == rs.SplitState(False) and rs.parse_split(None) is None
    assert rs.event_cancelled({"status": "Cancelled"}) and not rs.event_cancelled({"status": "Waiting"})
    event = next(item for item in schedule().events if item.title == "LMP2 Fixed")
    assert rs.race_end(event, event.starts[0]) == event.starts[0].time + event.total


def test_live_read_every_minute_while_page_shows(fresh_info, monkeypatch):
    info.read()
    tried = info.state().tried
    # Just past the interval: (tried + 600) - tried is 599.9999999999999 for some read times (909.593: CI runner
    # started 15 minutes before), never asked exactly on it
    assert not info.due(tried + info.LIVE_READ_SECONDS - 1, live=True)
    assert info.due(tried + info.LIVE_READ_SECONDS + 0.01, live=True)
    assert not info.due(tried + info.LIVE_READ_SECONDS + 0.01, live=False)  # Home: every READ_SECONDS
    # LIVE_READ_SECONDS later (1 s more, same rounding): clocks moved on, not the last read moved back (below 0,
    # "never read": due for Home too, on a machine started less than LIVE_READ_SECONDS ago, its monotonic clock
    # counting from boot: CI runners)
    monotonic = time.monotonic
    monkeypatch.setattr(time, "monotonic", lambda: monotonic() + info.LIVE_READ_SECONDS + 1)
    later = time.time() + info.LIVE_READ_SECONDS
    monkeypatch.setattr(time, "time", lambda: later)
    count = len(fresh_info.paths)
    info.read()
    assert len(fresh_info.paths) == count  # not due for Home
    answered = set(info._answers[1])
    slots = info.state().schedule.frequency
    info.read(live=True)  # routes that rarely change not asked again (recent answer), page ones asked
    asked = [key for key in rs.ROUTES
             if key != "hosted" and (key not in info.SLOW_ROUTES or key not in answered)
             and not (key.startswith("daily_") and slots.get(key[6:], 0) - info.FRESH_MARGIN > info.LIVE_READ_SECONDS)]
    assert fresh_info.paths[count:] == [rs.ROUTES[key] for key in asked]
    assert not set(info.state().schedule.missing) & info.SLOW_ROUTES & answered  # not asked: not missing
    count = len(fresh_info.paths)
    assert info.hosted_stale()
    info.read(live=True, servers=True)  # Hosted Servers tab shown: its route asked, others recent (unless failed)
    unanswered = [rs.ROUTES[key] for key in rs.ROUTES if key not in info._known() and key != "hosted"]
    assert fresh_info.paths[count:] == [*unanswered, rs.ROUTES["hosted"]] and not info.hosted_stale()
    fresh_info.data["api/v1/event/my-split/specialevent/a b"] = {"server": {"host": "h", "password": "p"}}
    assert info.read_split("specialevent", "a b") is None  # id quoted in the path
    assert fresh_info.paths[-1] == "api/v1/event/my-split/specialevent/a%20b"
    fresh_info.data["api/v1/event/my-split/daily/id-1"] = {"server": {"host": "h", "password": "p"}}
    assert info.read_split("daily", "id-1") == rs.SplitState(True)


def test_ranks_read_soon_after_your_race():
    from neopedal.process import driver_ranks as dr

    clock = [100.0]
    watcher = dr.RankWatcher(lambda: dr.Located("", "", ()), clock=lambda: clock[0])
    watcher.read_soon()
    assert watcher._online_due == [100.0 + delay for delay in dr.ONLINE_RESULTS_DELAYS]
    clock[0] = 110.0
    watcher.read_soon()  # merged, sorted
    assert len(watcher._online_due) == 2 * len(dr.ONLINE_RESULTS_DELAYS) and watcher._online_due == sorted(
        watcher._online_due)


def test_your_race_followed_live(ui_env, fresh_info, monkeypatch):
    from neopedal import rank_info
    from neopedal.ui.quick import race_watch as rw
    from neopedal.ui.quick import schedule_reminders

    monkeypatch.setattr(schedule_reminders, "_reminders", None)
    data = answers()
    mine = race_config("LMP2 Fixed", NOW + 600)
    mine["registrations"] = [{"driver": {"id": "me-id"}}]
    data["daily_beginner"] = [mine]
    fresh_info.data = data
    info.read()
    event = next(item for item in info.state().schedule.events if item.title == "LMP2 Fixed")
    start = next(item for item in event.starts if item.event_id == "id-LMP2 Fixed")
    assert start.registered
    assert rw.watched_starts(info.state().schedule, start.time - 120) == []  # not yet
    assert rw.watched_starts(info.state().schedule, start.time - 30) == [(event, start)]
    clock = [start.time - 30]
    told: list[str] = []
    from neopedal.ui.notification import message_text

    monkeypatch.setattr(rw.RaceWatch, "tell", staticmethod(lambda message, *args, **kwargs: told.append(message_text(message))))
    monkeypatch.setattr(info, "player_id", lambda: "me-id")
    overview = {"id": "id-LMP2 Fixed", "status": "Waiting", "registrations": [{"driver": {"id": "me-id"}}]}
    split = [rs.SplitState(False)]
    asked = []
    monkeypatch.setattr(info, "read_overview", lambda kind, key: asked.append(("overview", kind, key)) or overview)
    monkeypatch.setattr(info, "read_split", lambda kind, key: asked.append(("split", kind, key)) or split[0])
    monkeypatch.setattr(info, "read", lambda *args, **kwargs: info.state())
    read_soon = []
    monkeypatch.setattr(rank_info.ranks, "read_soon", lambda: read_soon.append(1))
    watch = rw.RaceWatch(None, clock=lambda: clock[0])
    watch._timer.stop()
    ready = []
    watch.changed.connect(lambda: ready.append(1))

    def check():
        watch.check()
        for _ in range(100):
            pump(0.02)
            if not watch._jobs.running:
                break

    check()  # registration checked first: still registered, nothing told
    assert asked == [("overview", "daily", "id-LMP2 Fixed")] and told == []
    check()  # server not given yet
    assert asked[-1] == ("split", "daily", "id-LMP2 Fixed") and told == [] and not watch.is_ready("id-LMP2 Fixed")
    split[0] = rs.SplitState(True, 1, 2)
    check()
    assert watch.is_ready("id-LMP2 Fixed") and ready == [1] and len(told) == 1
    assert told[0].startswith("Server ready: LMP2 Fixed") and "Split 1 of 2" in told[0]
    count = len(asked)
    check()  # told once, nothing read again
    assert len(asked) == count and len(told) == 1
    clock[0] = rs.race_end(event, start) + 5  # race over: your ranks read again, once
    check()
    check()
    assert read_soon == [1]
    # Registration removed, race cancelled: told when the race opens
    for answer, words in (({"status": "Waiting", "registrations": []}, "No longer registered"),
                          ({"status": "Cancelled", "registrations": [{"driver": {"id": "me-id"}}]}, "cancelled")):
        told.clear()
        other = rw.RaceWatch(None, clock=lambda: start.time - 30)
        other._timer.stop()
        monkeypatch.setattr(other, "tell", lambda message, *args, **kwargs: told.append(message_text(message)))
        overview = answer
        other.check()
        for _ in range(100):
            pump(0.02)
            if not other._jobs.running:
                break
        assert len(told) == 1 and words in told[0]
        assert other.is_ready("id-LMP2 Fixed")  # nothing more read for it
    monkeypatch.setattr(info, "player_id", lambda: "")  # not signed in yet: never told removed
    told.clear()
    overview = {"status": "Waiting", "registrations": []}
    third = rw.RaceWatch(None, clock=lambda: start.time - 30)
    third._timer.stop()
    third.registration_read(event, start, overview)
    assert told == []


def test_close_fields_read_live_on_the_page(qml_warnings, page, monkeypatch):  # noqa: F811
    from neopedal.ui.quick import race_watch as rw
    from neopedal.ui.quick import schedule_backend

    backend = page.backend
    backend.setOpenOnly(False)
    reads = []
    level = [rs.FieldLevel(2, (("LMP2", 2),), (("Silver", 2),), (), True)]
    monkeypatch.setattr(info, "read_field", lambda kind, event_id: reads.append(event_id) or level[0])

    def later():  # LIVE_FIELD_EVERY gone by (pump needs the real clock)
        backend._live_fields = {key: when - schedule_backend.LIVE_FIELD_EVERY
                                for key, when in backend._live_fields.items()}

    def wait():
        for _ in range(100):
            pump(0.02)
            if not backend.jobs.running:
                break

    backend.read_live_fields(NOW)
    wait()
    close = [race for group in backend.daily for race in group["races"]
             if 0 < race["startTime"] - NOW <= schedule_backend.LIVE_FIELD_SECONDS and race["eventId"]]
    assert close and sorted(reads) == sorted(race["eventId"] for race in close)
    key = close[0]["key"]
    assert backend.details[f"field:{key}"]["text"] == "2 drivers registered"
    backend.read_live_fields(NOW)  # read again only every LIVE_FIELD_EVERY
    wait()
    assert len(reads) == len(close)
    later()
    level[0] = None  # not read this time: last field kept
    backend.read_live_fields(NOW)
    wait()
    assert len(reads) == 2 * len(close) and backend.details[f"field:{key}"]["text"] == "2 drivers registered"
    backend.setTab(2)  # championships shown: no field read
    later()
    backend.read_live_fields(NOW)
    assert len(reads) == 2 * len(close)
    backend.setTab(0)
    # Server of your race ready: told on its card
    monkeypatch.setattr(rw.race_watch(), "_ready", {close[0]["eventId"]: close[0]["startTime"]})
    backend.publish_all()
    assert next(race for group in backend.daily for race in group["races"] if race["key"] == key)["serverReady"]
    pump(0.2)
    from tests.test_audit_g_qml_pages import items_of

    pills = [item for item in items_of(page.view.rootObject()) if item.objectName() == "serverReady"]
    assert any(item.isVisible() for item in pills)
    QCoreApplication.processEvents()
    assert not qml_warnings, qml_warnings


def test_requests_paced_whichever_thread_asks():
    """RaceControl refused a burst (403 on 5 requests sent at once, then on the sign in): REQUEST_GAP between two"""
    from neopedal.process import raceos

    clock = [0.0]
    slept = []

    def sleep(seconds):
        slept.append(round(seconds, 3))
        clock[0] += seconds

    def http(method, url, body, headers, timeout):
        clock[0] += 0.1  # answer time
        if url == raceos.AUTH_URL:
            return 200, json.dumps({"accessToken": "t", "expiresAt": iso(NOW + 3600), "player": {}}).encode()
        return 200, b"[]"

    client = raceos.RaceOSClient(lambda: "ticket", http=http, clock=lambda: clock[0], wall_clock=lambda: NOW,
                                 pace=True, sleep=sleep)
    for _ in range(3):
        client.get("api/v1/hosted")
    gap = round(raceos.REQUEST_GAP - 0.1, 3)
    assert slept == [gap, gap, gap]  # sign in, then each read REQUEST_GAP after the one before
    assert raceos.RaceOSClient(lambda: "", http=http).__dict__["_pace_requests"] is False  # tests: never paced
    assert raceos.RaceOSClient(lambda: "")._pace_requests  # the service itself: paced


def test_forbidden_list_keeps_the_sign_in():
    """403 on the entry list of some events (live 2026-11-02): token kept, no new sign in (signing in again at once
    was refused too); 401, or 403 on a new token, still sign in again"""
    from neopedal.process import raceos

    calls = []
    replies = {"api/v1/event/entries/daily/private": 403, "api/v1/hosted": 200, "api/v1/expired": 401}

    def http(method, url, body, headers, timeout):
        path = url.replace(f"{raceos.RACEOS_URL}/", "")
        calls.append("auth" if url == raceos.AUTH_URL else path)
        if url == raceos.AUTH_URL:
            return 200, json.dumps({"accessToken": "t", "expiresAt": iso(NOW + 3600), "player": {}}).encode()
        return replies[path], b"[]"

    client = raceos.RaceOSClient(lambda: "ticket", http=http, wall_clock=lambda: NOW)
    assert client.get("api/v1/hosted") == []
    assert client.get("api/v1/event/entries/daily/private") is None
    assert client.get("api/v1/hosted") == [] and calls.count("auth") == 1  # same sign in
    assert client.get("api/v1/expired") is None
    client.get("api/v1/hosted")
    assert calls.count("auth") == 2  # 401: signed in again


def test_forbidden_field_not_asked_again_live(page, monkeypatch):
    from neopedal.ui.quick import schedule_backend

    backend = page.backend
    backend.setOpenOnly(False)
    reads = []
    monkeypatch.setattr(info, "read_field", lambda kind, event_id: reads.append(event_id))  # never answered

    def round_of_reads():
        backend._live_fields = {}
        backend.read_live_fields(NOW)
        for _ in range(100):
            pump(0.02)
            if not backend.jobs.running:
                break

    round_of_reads()
    count = len(reads)
    assert count
    for _ in range(schedule_backend.LIVE_FIELD_MISSES):
        round_of_reads()
    assert len(reads) == count * schedule_backend.LIVE_FIELD_MISSES  # stopped after LIVE_FIELD_MISSES misses


def test_refused_connection_stops_every_request():
    """Live 2026-11-02 17:31: RaceControl answered 403 to every request of this connection (sign in, public routes,
    the game's too): nothing asked for BLOCK_SECONDS (doubled), sign ins included; entry lists' 403 alone is not"""
    from neopedal.process import raceos

    clock = [0.0]
    calls = []
    replies = {"auth": 403}

    def http(method, url, body, headers, timeout):
        path = "auth" if url == raceos.AUTH_URL else url.replace(f"{raceos.RACEOS_URL}/", "")
        calls.append(path)
        status = replies.get(path, 200)
        if path == "auth" and status == 200:
            return 200, json.dumps({"accessToken": "t", "expiresAt": iso(NOW + 3600), "player": {}}).encode()
        return status, b"{}"

    client = raceos.RaceOSClient(lambda: "ticket", http=http, clock=lambda: clock[0], wall_clock=lambda: NOW)
    assert client.get("api/v1/hosted") is None and calls == ["auth"]
    assert client.blocked_for() == raceos.BLOCK_SECONDS
    clock[0] = raceos.BLOCK_SECONDS - 1
    assert client.get("api/v1/hosted") is None and client.fetch() is None and client.sign_in() is None
    assert calls == ["auth"]  # nothing sent while refused
    replies["auth"] = 200
    clock[0] = raceos.BLOCK_SECONDS + raceos.RETRY_MAX_SECONDS  # sign in retry wait over too
    assert client.get("api/v1/hosted") == {} and client.blocked_for() == 0
    replies["api/v1/event/entries/daily/x"] = 403  # one list forbidden: connection still fine
    assert client.get("api/v1/event/entries/daily/x") is None and client.blocked_for() == 0
    replies["api/v1/daily/schedule"] = 403  # any other read refused: connection refused
    assert client.get("api/v1/daily/schedule") is None and client.blocked_for() == raceos.BLOCK_SECONDS
    count = len(calls)
    assert client.get("api/v1/hosted") is None and len(calls) == count


def test_requests_per_minute_capped():
    from neopedal.process import raceos

    clock = [0.0]
    sent = []

    def http(method, url, body, headers, timeout):
        sent.append(url)
        if url == raceos.AUTH_URL:
            return 200, json.dumps({"accessToken": "t", "expiresAt": iso(NOW + 3600), "player": {}}).encode()
        return 200, b"[]"

    def sleep(seconds):
        clock[0] += seconds

    client = raceos.RaceOSClient(lambda: "ticket", http=http, clock=lambda: clock[0], wall_clock=lambda: NOW,
                                 pace=True, sleep=sleep)
    answers = [client.get("api/v1/hosted") for _ in range(raceos.MAX_PER_MINUTE + 5)]
    assert len(sent) == raceos.MAX_PER_MINUTE and answers[-1] is None  # sign in counted: 29 reads, then none
    clock[0] += 60.0
    assert client.get("api/v1/hosted") == [] and len(sent) == raceos.MAX_PER_MINUTE + 1


def test_page_tells_refused_connection(page, monkeypatch):
    monkeypatch.setattr(info, "blocked_minutes", lambda: 15)
    page.backend.publish_status()
    assert page.backend.status["level"] == "warning" and "15 min" in page.backend.status["note"]
    monkeypatch.setattr(info, "blocked_minutes", lambda: 0)
    page.backend.publish_status()
    assert "refuses" not in page.backend.status["note"]


def test_game_closed_note_tells_when_races_were_read():
    # Game closed: races last read stay shown, the note tells when they were read (game only needed to update them)
    from neopedal.ui.quick.schedule_backend import status_note

    read = time.time() - 3600
    level, note = status_note(info.NO_GAME, rs.EMPTY._replace(read_time=read))
    assert level == "info" and time.strftime("%H:%M", time.localtime(read)) in note and "update" in note
    assert "%1" not in note
    assert "with the game sign in" in status_note(info.NO_GAME, rs.EMPTY)[1]  # never read: told why
