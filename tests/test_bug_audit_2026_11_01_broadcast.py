"""Bug audit of the broadcast part (2026-11-01, audit_bugs_broadcast_2026-11-01.md): Broadcast Director, broadcast
graphics, stream sources & Spectate. One regression test (or more) per bug B-XXX, game faked (never a real game)"""

from neopedal.process import director as dr
from tests.test_broadcast_director import car, director_page, poll, race_answers  # noqa: F401  (fixture)
from tests.test_game_info import wait_commands


def player_answers(session_time, *cars, player=1, **values):
    """Live session where the local player drives car of slot player"""
    answers = race_answers(session_time, *cars, **values)
    for row in answers["/rest/watch/standings"]:
        row["player"] = row["slotID"] == player
    return answers


def focus_commands(game):
    return [command for command in game.sent if command[1].startswith("/rest/watch/focus/")]


# B-001: no game command by itself while the player drives
def test_b001_no_automatic_cut_instant_replay_or_follow_while_player_drives(director_page, monkeypatch):  # noqa: F811
    from neopedal.setting import cfg

    monkeypatch.setitem(cfg.api, "enable_player_index_override", False)
    monkeypatch.setitem(cfg.api, "player_index", -1)
    page, backend = director_page, director_page.backend
    cars = (car(1, 1, distance=2000.0), car(2, 2, distance=1000.0), car(3, 3, distance=400.0))
    poll(page, player_answers(100.0, *cars))
    assert backend.player_driving()
    backend.follow_overlays = True
    backend.setMode(2)
    backend.director.hold_until = 0.0
    poll(page, player_answers(101.0, *cars, contacts=((100.5, "Driver 3", "Driver 2"),)))
    wait_commands(backend.camera)
    assert backend.mode == "auto" and focus_commands(page.game) == []  # stories listed, never cut to
    assert backend.candidates
    key = next(row["key"] for row in backend.feedRows.rows if row["kind"] == dr.CONTACT)
    backend.replayEvent(key)
    wait_commands(backend.camera)
    assert not backend.instantReplay and ("POST", "/rest/replay/toggleactive") not in page.game.sent
    # Operator cut still allowed (explicit action), overlays stay on the player car
    backend.cutToCar(2)
    wait_commands(backend.camera)
    assert ("PUT", "/rest/watch/focus/2") in page.game.sent
    assert not cfg.api["enable_player_index_override"]


def test_b001_director_cuts_again_once_player_back_in_garage(director_page):  # noqa: F811
    page, backend = director_page, director_page.backend
    cars = (car(1, 1, distance=2000.0, garage=True), car(2, 2, distance=1000.0), car(3, 3, distance=400.0))
    poll(page, player_answers(100.0, *cars))
    assert not backend.player_driving()  # in its garage stall: watching others is fine
    poll(page, race_answers(101.0, *cars, replay=True))
    assert not backend.player_driving()  # replay: never the driver's view
