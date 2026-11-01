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


def forget_follow(backend):
    """Overlays follow turned off again in the page settings file (next tests start without it)"""
    backend.follow_overlays = False
    backend.save_settings()
    backend.flush_settings()


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
    forget_follow(backend)


def test_b001_director_cuts_again_once_player_back_in_garage(director_page):  # noqa: F811
    page, backend = director_page, director_page.backend
    cars = (car(1, 1, distance=2000.0, garage=True), car(2, 2, distance=1000.0), car(3, 3, distance=400.0))
    poll(page, player_answers(100.0, *cars))
    assert not backend.player_driving()  # in its garage stall: watching others is fine
    poll(page, race_answers(101.0, *cars, replay=True))
    assert not backend.player_driving()  # replay: never the driver's view


# B-007: automatic mode turned on during an instant replay waits for live
def test_b007_automatic_mode_during_instant_replay_never_cuts(director_page):  # noqa: F811
    page, backend = director_page, director_page.backend
    cars = (car(1, 1, distance=2000.0), car(2, 2, distance=1000.0), car(3, 3, distance=400.0))
    poll(page, race_answers(100.0, *cars, focus=3))
    backend.director.shot = backend.director.shot._replace(start=-100.0)  # shot long enough: director may cut
    backend.instant = True  # instant replay playing
    page.game.sent.clear()
    backend.setMode(2)
    wait_commands(backend.camera)
    assert backend.mode == "auto" and page.game.sent == [] and backend.on_air_slot == 3
    backend.instant = False


# B-002: instant replay forgotten while the game did not answer: left once it answers again
def test_b002_instant_replay_left_when_game_answers_again(director_page):  # noqa: F811
    page, backend = director_page, director_page.backend
    cars = (car(1, 1, distance=2000.0), car(2, 2, distance=1000.0))
    poll(page, race_answers(100.0, *cars))
    backend.instant = True  # instant replay playing
    for _ in range(4):  # game not answering (remote game unreachable a few seconds)
        poll(page, {})
    assert backend.gameState in ("menu", "offline") and not backend.instantReplay
    page.game.sent.clear()
    poll(page, race_answers(101.0, *cars, replay=True))  # game answers again, still in the replay
    wait_commands(backend.camera)
    assert ("POST", "/rest/replay/toggleactive") in page.game.sent


def director_script() -> str:
    from neopedal import stream_director

    html = stream_director.director_html("en", "Director")
    return html.split("<script>", 1)[1].split("</script>", 1)[0]


# B-003: two cars with the same number in one class each have their tower line
def test_b003_tower_lines_keyed_by_slot(director_page):  # noqa: F811
    page, backend = director_page, director_page.backend
    poll(page, race_answers(100.0, car(1, 1, number="7"), car(2, 2, number="7"), car(3, 3)))
    tower = backend._graphics.graphics_state()["tower"]
    assert [row["slot"] for row in tower] == [1, 2, 3]
    script = director_script()
    assert 'key="c|"+carId(row)' in script and "lapKey=carId(row)" in script
    assert "function carId(row)" in script


# B-004: graphics hidden when the app no longer answers (never left frozen on air)
def test_b004_graphics_hidden_after_failed_requests():
    from neopedal import stream_director

    script = director_script()
    poll_body = script.split("async function poll(){", 1)[1].split("async function pollLive(){", 1)[0]
    assert "serverLost(false)" in poll_body and poll_body.count("serverLost(true)") == 2
    assert "function serverLost(lost)" in script and "LOST_MS=5000" in script
    assert ".lost>.g{opacity:0!important}" in stream_director.director_html("en", "Director")


TRACK = 4000.0


def finished(*cars):
    return [item._replace(finish="FSTAT_FINISHED") for item in cars]


# B-005: the class winner is the class leader taking the flag in a race (never a lapped car, never qualifying)
def test_b005_winner_is_class_leader_in_races_only():
    watcher = dr.RaceWatcher()
    hyper, gt3_leader, gt3_lapped = car(1, 1, car_class="Hyper"), car(10, 2), car(11, 3, laps=9)
    watcher.update([hyper, gt3_leader, gt3_lapped], (), 1000.0, "RACE1", TRACK)
    events = watcher.update([*finished(hyper), gt3_leader, *finished(gt3_lapped)], (), 1001.0, "RACE1", TRACK)
    assert sorted((event.kind, event.slots) for event in events if event.kind in (dr.WINNER, dr.FINISH)) == [
        (dr.FINISH, (11,)), (dr.WINNER, (1,))]
    events = watcher.update(finished(hyper, gt3_leader, gt3_lapped), (), 1020.0, "RACE1", TRACK)
    assert [(event.kind, event.slots) for event in events] == [(dr.WINNER, (10,))]
    qualifying = dr.RaceWatcher()
    cars = [car(1, 1), car(2, 2)]
    qualifying.update(cars, (), 100.0, "QUALIFY1", TRACK)
    events = qualifying.update([*finished(cars[1]), cars[0]], (), 101.0, "QUALIFY1", TRACK)
    assert [event.kind for event in events] == [dr.FINISH]


# B-006: slot taken by another car between two answers: nothing of the former car (laps, stops, events)
def test_b006_slot_reused_within_one_answer_starts_afresh():
    watcher = dr.RaceWatcher()
    former = car(5, 2, laps=30, best=90.0, team="Team A")
    watcher.update([car(1, 1), former], (), 100.0, "RACE1", TRACK)
    watcher.update([car(1, 1), former._replace(laps=31, last=91.0)], (), 101.0, "RACE1", TRACK)
    assert [record.lap for record in watcher.laps[5]] == [31]
    newcomer = car(5, 2, laps=0, best=85.0, penalties=1, team="Team B", driver="New Driver")
    events = watcher.update([car(1, 1), newcomer], (), 102.0, "RACE1", TRACK)
    assert [event.kind for event in events if 5 in event.slots and event.kind != dr.BATTLE] == []
    assert 5 not in watcher.laps and 5 not in watcher.pit_stops
    watcher.update([car(1, 1), newcomer._replace(laps=1, last=99.0)], (), 103.0, "RACE1", TRACK)
    assert [record.lap for record in watcher.laps[5]] == [1]
    # Same car, laps going down (same livery picked by the newcomer): another car too
    watcher.update([car(1, 1), newcomer._replace(laps=0, team="Team B")], (), 104.0, "RACE1", TRACK)
    assert 5 not in watcher.laps


# B-042: a car missing from one answer keeps its history
def test_b042_car_missing_from_one_answer_keeps_history():
    watcher = dr.RaceWatcher()
    cars = [car(1, 1, laps=10), car(2, 2)]
    watcher.update(cars, (), 100.0, "RACE1", TRACK)
    watcher.update([car(1, 1, laps=11, last=95.0), car(2, 2)], (), 101.0, "RACE1", TRACK)
    watcher.update([car(2, 1)], (), 102.0, "RACE1", TRACK)  # answer without car 1
    events = watcher.update([car(1, 1, laps=11), car(2, 2)], (), 103.0, "RACE1", TRACK)
    assert [record.lap for record in watcher.laps[1]] == [11] and not [e for e in events if e.kind != dr.BATTLE]


# B-008: overlays follow a car chosen in the game too
def test_b008_overlays_follow_car_chosen_in_game(director_page, monkeypatch):  # noqa: F811
    from neopedal.setting import cfg

    monkeypatch.setitem(cfg.api, "enable_player_index_override", True)
    monkeypatch.setitem(cfg.api, "player_index", 1)
    monkeypatch.setattr(type(cfg), "save", lambda *args, **kwargs: None)
    page, backend = director_page, director_page.backend
    cars = (car(1, 1, distance=2000.0), car(2, 2, distance=1000.0), car(3, 3, distance=400.0))
    poll(page, race_answers(100.0, *cars, focus=1))
    backend.follow_overlays = True
    backend.last_cut = 0.0
    poll(page, race_answers(101.0, *cars, focus=3))  # operator chose car 3 in the game
    assert backend.on_air_slot == 3 and cfg.api["player_index"] == 3
    forget_follow(backend)


# B-009: page closed: spectate mode turned on by the director turned off (overlays back on the player car)
def test_b009_page_closed_stops_overlays_following(director_page, monkeypatch):  # noqa: F811
    from neopedal.setting import cfg

    monkeypatch.setitem(cfg.api, "enable_player_index_override", False)
    monkeypatch.setitem(cfg.api, "player_index", -1)
    monkeypatch.setattr(type(cfg), "save", lambda *args, **kwargs: None)
    page, backend = director_page, director_page.backend
    poll(page, race_answers(100.0, car(1, 1), car(2, 2), focus=1))
    backend.setFollowOverlays(True)
    backend.cutToCar(2)
    assert cfg.api["enable_player_index_override"] and cfg.api["player_index"] == 2
    backend.follow_overlays = True
    backend.release_resources()
    assert not cfg.api["enable_player_index_override"]
    forget_follow(backend)
