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


def pit_frame(time, laps, in_pit, last=0.0, pitstops=0):
    return [car(1, 1, laps=laps, in_pit=in_pit, last=last, pitstops=pitstops, speed=20.0 if in_pit else 50.0),
            car(2, 2, laps=laps, distance=200.0)]


PIT_LAP = [(100.0, 10, False, 0.0, 0), (101.0, 10, True, 0.0, 0), (102.0, 10, True, 0.0, 0),
           (103.0, 11, True, 92.0, 0), (104.0, 11, False, 92.0, 1), (105.0, 11, False, 92.0, 1)]


# B-010: replay rewound through a lap & a pit stop: recorded once
def test_b010_rewind_never_records_laps_and_stops_twice():
    watcher = dr.RaceWatcher()
    for time, laps, pit, last, stops in PIT_LAP:
        watcher.update(pit_frame(time, laps, pit, last, stops), (), time, "RACE1", TRACK)
    watcher.update(pit_frame(99.5, 10, False), (), 99.5, "RACE1", TRACK)  # rewound
    for time, laps, pit, last, stops in PIT_LAP:
        watcher.update(pit_frame(time + 0.3, laps, pit, last, stops), (), time + 0.3, "RACE1", TRACK)
    assert [record.lap for record in watcher.laps[1]] == [11]
    assert [stop.lap for stop in watcher.pit_stops[1]] == [11]


# B-025: replay rewound into a pit stop already seen: no second pit exit with a shorter time
def test_b025_no_pit_exit_for_a_stop_already_closed():
    watcher = dr.RaceWatcher()
    watcher.update(pit_frame(100.0, 10, False), (), 100.0, "RACE1", TRACK)
    for time in range(101, 131):
        watcher.update(pit_frame(float(time), 10, True), (), float(time), "RACE1", TRACK)
    events = watcher.update(pit_frame(131.0, 11, False, pitstops=1), (), 131.0, "RACE1", TRACK)
    assert [(event.kind, event.value) for event in events if event.kind == dr.PIT_OUT] == [(dr.PIT_OUT, 30.0)]
    for time in range(105, 131):  # rewound into the stop (started before: kept, closed)
        watcher.update(pit_frame(float(time), 10, True), (), float(time), "RACE1", TRACK)
    events = watcher.update(pit_frame(131.0, 11, False, pitstops=1), (), 131.0, "RACE1", TRACK)
    assert [event for event in events if event.kind == dr.PIT_OUT] == []
    assert [stop.duration for stop in watcher.pit_stops[1]] == [30.0]


# B-014: two cars side by side swapping places: one battle, told once, its length kept
def test_b014_battle_kept_when_cars_swap_places():
    watcher = dr.RaceWatcher()
    watcher.update([car(1, 1, distance=1000.0), car(2, 2, distance=500.0)], (), 99.0, "RACE1", TRACK)  # apart
    battles = []
    for step in range(8):
        first, second = (1, 2) if step % 2 == 0 else (2, 1)
        cars = [car(first, 1, distance=1000.0 + step * 50.0), car(second, 2, distance=999.0 + step * 50.0)]
        battles += [event for event in watcher.update(cars, (), 100.0 + step, "RACE1", TRACK)
                    if event.kind == dr.BATTLE]
    assert len(battles) == 1
    (battle,) = watcher.battles.values()
    assert battle.since == 100.0


# B-015: story on air (marked seen when cut to) keeps its full score: no cut every urgent_after
def test_b015_story_on_air_not_halved_by_seen():
    director = dr.Director()
    cars = [car(slot, slot, distance=1000.0 - 300 * slot) for slot in range(1, 7)]
    events, seen, cuts = [], set(), []
    for clock in range(20):
        now = 100.0 + clock
        if clock in (0, 3, 6, 9):  # contacts of one crash, a few seconds apart
            slot = 1 + clock // 3
            events.append(dr.Event(f"contact|{now}|{slot}", dr.CONTACT, now, (slot, slot + 1), ("a", "b"), "GT3"))
        pick = director.decide(director.candidates(events, [], cars, now, float(clock), True, seen=seen), float(clock))
        if pick is not None:
            director.take(pick, float(clock))
            seen.add(pick.key)  # page: story cut to marked seen
            cuts.append(clock)
    assert cuts[:2] == [0, 8]  # shortest shot kept: same priority never cuts it short


# B-016: car stopped on track during the first lap of a green race is told
def test_b016_car_stopped_on_first_lap_told():
    from neopedal.process.game_info import SessionState

    green = SessionState(phase=dr.GREEN_PHASE)
    watcher = dr.RaceWatcher()

    def field_at(time):
        return [car(slot, slot, laps=0, distance=3000.0 - 250 * slot + (0 if slot == 5 else 50 * (time - 100)),
                    speed=0.0 if slot == 5 else 50.0) for slot in range(1, 11)]

    events = []
    for time in range(100, 110):
        events += watcher.update(field_at(time), (), float(time), "RACE1", TRACK, info=green)
    assert [event.slots for event in events if event.kind == dr.STOPPED] == [(5,)]
    # Before the start (grid, formation lap): never told
    watcher = dr.RaceWatcher()
    events = []
    for time in range(100, 110):
        events += watcher.update(field_at(time), (), float(time), "RACE1", TRACK, info=SessionState(phase=3))
    assert [event for event in events if event.kind == dr.STOPPED] == []


# B-031: session time frozen (replay paused): one speed sample per car, not one per answer
def test_b031_speed_history_bounded_while_time_frozen():
    watcher = dr.RaceWatcher()
    cars = [car(1, 1), car(2, 2, distance=500.0)]
    watcher.update(cars, (), 100.0, "RACE1", TRACK)
    for _ in range(500):
        watcher.update(cars, (), 101.0, "RACE1", TRACK)
    assert len(watcher.cars[1].speeds) <= 2


# B-043: replay played fast (steps over JUMP, all alike) is watched, not taken for a seek at every answer
def test_b043_fast_replay_steps_are_no_seek():
    watcher = dr.RaceWatcher()
    for step in range(8):
        time = 100.0 + step * 20.8  # x16 replay, an answer every 1.3 s
        laps = 10 + step // 4
        watcher.update([car(1, 1, laps=laps, last=90.0, distance=1000.0), car(2, 2, laps=laps, distance=990.0)],
                       (), time, "RACE1", TRACK)
    assert [record.lap for record in watcher.laps[1]] == [11] and watcher.battles
    # A real seek (one step far from the others) still watches again from there
    watcher.update([car(1, 1, laps=12), car(2, 2, laps=12, distance=990.0)], (), 2000.0, "RACE1", TRACK)
    assert [battle.since for battle in watcher.battles.values()] == [2000.0]


# B-045: two cars stopped after one crash in a small field: told (not a halted race)
def test_b045_small_field_two_stopped_cars_told():
    watcher = dr.RaceWatcher()
    stopped = (2, 3)

    def field_at(time):
        return [car(slot, slot, distance=3000.0 - 400 * slot + (0 if slot in stopped else 50 * (time - 100)),
                    speed=0.0 if slot in stopped else 50.0) for slot in range(1, 6)]

    events = []
    for time in range(100, 110):
        events += watcher.update(field_at(time), (), float(time), "RACE1", TRACK)
    assert sorted(event.slots for event in events if event.kind == dr.STOPPED) == [(2,), (3,)]


# B-046: overtake on the finish line (both cars finished as the new place settles) is told
def test_b046_overtake_on_the_finish_line_told():
    watcher = dr.RaceWatcher()
    watcher.update([car(1, 1, finish="FSTAT_FINISHED"), car(2, 2, distance=3990.0), car(3, 3, distance=3985.0)], (),
                   100.0, "RACE1", TRACK)
    line = [car(1, 1, finish="FSTAT_FINISHED"), car(3, 2, laps=11, distance=5.0, finish="FSTAT_FINISHED"),
            car(2, 3, laps=11, distance=3.0, finish="FSTAT_FINISHED")]
    events = watcher.update(line, (), 100.5, "RACE1", TRACK) + watcher.update(line, (), 101.6, "RACE1", TRACK)
    assert [(event.kind, event.slots) for event in events if event.kind == dr.OVERTAKE] == [(dr.OVERTAKE, (3, 2))]
    # Long after the flag, places of finished cars changing are no overtake
    later = [car(1, 1, finish="FSTAT_FINISHED"), car(2, 2, laps=11, finish="FSTAT_FINISHED"),
             car(3, 3, laps=11, finish="FSTAT_FINISHED")]
    events = watcher.update(later, (), 130.0, "RACE1", TRACK) + watcher.update(later, (), 131.5, "RACE1", TRACK)
    assert [event for event in events if event.kind == dr.OVERTAKE] == []


# B-047: two cars with the same position, answer order flipping: no lead change told
def test_b047_duplicate_positions_never_swap_places():
    watcher = dr.RaceWatcher()
    watcher.update([car(1, 1), car(2, 1, distance=990.0)], (), 100.0, "RACE1", TRACK)
    events = watcher.update([car(2, 1, distance=990.0), car(1, 1)], (), 101.0, "RACE1", TRACK)
    events += watcher.update([car(2, 1, distance=990.0), car(1, 1)], (), 102.5, "RACE1", TRACK)
    assert [event for event in events if event.kind in (dr.LEAD, dr.OVERTAKE)] == []
    assert dr.class_places([car(2, 1, distance=990.0), car(1, 1)]) == {1: 1, 2: 2}  # car ahead on track first


# B-011: sponsor carousel timer started again only when the sponsors or their seconds change (not every answer)
def test_b011_sponsor_timer_kept_between_answers():
    script = director_script()
    brand = script.split("const items=(info.sponsors||[])", 1)[1].split("function draw(){", 1)[0]
    assert "if(timerKey!==sponsorTimerKey){sponsorTimerKey=timerKey;clearInterval(sponsorTimer);" in brand
    assert brand.count("clearInterval(sponsorTimer)") == 1


# B-017: page carousels follow the page count & seconds of now, a new board starts at its first page
def test_b017_page_carousel_reads_current_count():
    script = director_script()
    cycle = script.split("function cyclePages(", 1)[1].split("function stopPages(", 1)[0]
    assert "pageCounts[id]=count" in cycle and "%Math.max(pageCounts[id]||1,1)" in cycle
    assert "seconds!==pageSeconds[id]" in cycle and "if(count<=1){if(pageTimers[id])stopPages(id);return}" in cycle
    assert 'cyclePages("champ",page.count,champ,info.title+"|"+info.subtitle)' in script


# B-018: running lap clock of qualifying counted from when its own time came (other answers never set it back)
def test_b018_quali_clock_from_its_own_answer():
    script = director_script()
    assert 'if(data.full||first||"quali" in (data.state||{}))received=Date.now()' in script
    assert ';received=Date.now();' not in script


def director_css() -> str:
    from neopedal import stream_director

    return stream_director.director_html("en", "Director").split("<style>", 1)[1].split("</style>", 1)[0]


# B-019: tower marks (tyres, stops, penalty, fastest lap) never take the name's room nor push the gap out
def test_b019_tower_marks_bounded():
    css = director_css()
    marks = css.split(".tmarks{", 1)[1].split("}", 1)[0]
    assert "max-width:calc(var(--u)*10)" in marks and "overflow:hidden" in marks
    assert "marks.append(...items.slice(0,TOWER_MARKS))" in director_script()
    assert "white-space:nowrap" in css.split(".tpen{", 1)[1].split("}", 1)[0]


# B-024: driver card shrinks its text to the card (long names end with an ellipsis, never cut mid-word)
def test_b024_driver_card_text_shrinks():
    css = director_css()
    assert "min-width:0" in css.split("#cardBody{", 1)[1].split("}", 1)[0]
    assert "min-width:0" in css.split("#cardName{", 1)[1].split("}", 1)[0]
    assert "flex-wrap:wrap" in css.split("#cardStats{", 1)[1].split("}", 1)[0] and "#cardStats>*{white-space:nowrap}" in css


# B-041: banner texts & onboard driver name kept on screen (ellipsis)
def test_b041_banner_and_onboard_name_bounded():
    css = director_css()
    text = css.split(".banner .txt{", 1)[1].split("}", 1)[0]
    assert "max-width:calc(var(--u)*70)" in text and "min-width:0" in text
    for rule in (".banner .txt b{", ".banner .txt span{", ".ob-head span{"):
        assert "text-overflow:ellipsis" in css.split(rule, 1)[1].split("}", 1)[0], rule


# B-026: countdown sent as seconds left, its end counted by the browser clock (OBS on another computer)
def test_b026_countdown_seconds_left(director_page):  # noqa: F811
    graphics = director_page.backend._graphics
    graphics.startCountdown(1.5, "Race starts in")
    state = graphics.countdown_state()
    assert "endsAt" not in state and 89.0 <= state["endsIn"] <= 90.0
    script = director_script()
    assert "countdownEnd=Date.now()+state.countdown.endsIn*1000" in script
    assert "info.endsIn!=null?(countdownEnd-Date.now())/1000" in script
    graphics.countdown_end = 0.0


# B-032: banners told & recent texts forgotten once out of the state / older than 30 s (24 h race)
def test_b032_banner_sets_pruned():
    banners = director_script().split("function banners(){", 1)[1].split("function nextBanner(", 1)[0]
    assert "for(const id of shownBanners)if(!ids.has(id))shownBanners.delete(id)" in banners
    assert "for(const [same,time] of recentBanners)if(now-time>=30000)recentBanners.delete(same)" in banners


# B-023: answers name the app run: a source of the previous run asks everything again (no state of that run kept)
def test_b023_answer_names_the_run():
    import json

    from neopedal import stream_director

    data = json.loads(stream_director.answer(0))
    assert data["run"] == stream_director.RUN and len(stream_director.RUN) >= 8
    assert "if(data.run&&runId&&data.run!==runId&&!data.full){runId=data.run;version=0;setTimeout(poll,0);return}" \
        in director_script()


# B-027: layout editor asks again until its first answer, never saves before (empty layout to another preset)
def test_b027_layout_editor_first_load_retried():
    script = director_script()
    assert "else if(edit&&chosenPreset===null)setTimeout(poll,1000);" in script
    assert '$("tbSave").onclick=async()=>{if(chosenPreset===null)return;' in script


# B-049: the live feed (onboard, map cars) asked only by sources showing the onboard or the map
def test_b049_live_feed_only_when_shown():
    live = director_script().split("async function pollLive(){", 1)[1].split("\n}", 1)[0]
    assert "if(!liveWanted()){setTimeout(pollLive,2000);return}" in live
    assert "function liveWanted(){" in director_script()
