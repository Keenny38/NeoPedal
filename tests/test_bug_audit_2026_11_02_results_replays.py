"""Bug audit of the Results & Replays page (2026-11-02): regression tests of the fixes (B-xxx: report numbers)"""

import os
import re
import sys
import time
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QCoreApplication

from tests.test_dialog_pages import window  # noqa: F401 (window: fixture)
from tests.test_game_info import GAME_ANSWERS, answered, replays_page, wait_commands, wait_requests  # noqa: F401 (fixtures)
from tests.test_race_results import results_folder  # noqa: F401 (fixture)

CTRL = 0x04000000  # Qt.KeyboardModifier.ControlModifier
QML = os.path.join(os.path.dirname(__file__), "..", "neopedal", "ui", "qml", "analysis")


def page_of_replays(replays_page, folder, names: str):  # noqa: F811
    """Replays page listing a replay file of folder for each name (newest last)"""
    folder.mkdir()
    for name in names:
        (folder / f"{name}.Vcr").write_bytes(b"replay")
    listed = [{"id": index, "replayName": name, "size": 1000, "timestamp": 1791165314 + index, "metadata": {}}
              for index, name in enumerate(names)]
    return answered(replays_page, {**GAME_ANSWERS, "/rest/watch/replays": listed,
                                   "/rest/watch/replay/getReplayFolder": {"custom": "", "default": str(folder)}})


# B-001: replay deselected with Ctrl stayed the replay given to the actions of the selection (Delete key, Delete of
# the selection bar, Export & Protect of the menu): it was moved to the recycle bin instead of the selected ones
def test_b001_ctrl_deselected_replay_not_deleted(replays_page, monkeypatch, tmp_path):  # noqa: F811
    from neopedal.ui.quick import dialogs, replay_files

    backend = page_of_replays(replays_page, tmp_path / "Replays", "ABC")
    backend.clickReplay("C", 0)
    backend.clickReplay("B", CTRL)
    backend.clickReplay("A", CTRL)
    backend.clickReplay("A", CTRL)  # A deselected: B & C left, A stays the current row (Shift range anchor)
    assert backend.checked == {"B", "C"} and backend.selectedReplay == "A"
    assert backend.selectionKey() in {"B", "C"}
    trashed: list[str] = []

    def move_to_trash(path: str) -> bool:
        trashed.append(path)
        return True

    monkeypatch.setattr(dialogs, "confirm", lambda *args, **kwargs: args[4](True))
    monkeypatch.setattr(replay_files, "QFile", SimpleNamespace(moveToTrash=move_to_trash))
    backend.deleteReplays(backend.selectionKey())
    wait_requests(backend.request_trash)
    assert sorted(os.path.basename(path) for path in trashed) == ["B.Vcr", "C.Vcr"]


def test_b001_selection_key_is_current_replay_otherwise(replays_page, tmp_path):  # noqa: F811
    backend = page_of_replays(replays_page, tmp_path / "Replays", "ABC")
    backend.clickReplay("C", 0)
    assert backend.selectionKey() == "C"
    backend.clickReplay("A", CTRL)
    assert backend.selectionKey() == "A"  # current replay selected
    backend.clickReplay("A", CTRL)
    backend.clickReplay("C", CTRL)  # nothing selected: current replay alone
    assert backend.checked == set() and backend.selectionKey() == backend.selectedReplay == "C"


def test_b001_selection_actions_of_page_use_selection_key():
    with open(os.path.join(QML, "ReplayList.qml"), encoding="utf-8") as file:
        source = file.read()
    for action in ("deleteReplays", "exportReplays", "toggleProtected"):
        assert not re.search(rf"{action}\(replays\.selectedReplay\)", source), action
    assert len(re.findall(r"(?:deleteReplays|exportReplays|toggleProtected)\(replays\.selectionKey\(\)\)", source)) == 5


SHOW_HUD = [("POST", "/rest/hud/toggleAllComponents/true"), ("POST", "/rest/sessions/setHudOnWatchScreen", "true"),
            ("POST", "/rest/watch/replay/setReplayUIVisible", "true")]


# B-002: HUD hidden from the page stayed hidden once the replay was left (in the next race too)
def test_b002_hud_hidden_in_replay_shown_again_once_replay_left(replays_page):  # noqa: F811
    backend = answered(replays_page, GAME_ANSWERS)
    assert backend.gameState == "replay"
    backend.setHudShown(False)
    wait_commands(backend)
    assert ("POST", "/rest/hud/toggleAllComponents/false") in replays_page.sent
    replays_page.sent.clear()
    answered(replays_page, {**GAME_ANSWERS, "/rest/replay/isActive": False})  # back to the live session
    wait_commands(backend)
    assert backend.gameState == "session" and replays_page.sent == SHOW_HUD
    replays_page.sent.clear()
    answered(replays_page, {**GAME_ANSWERS, "/rest/replay/isActive": None})  # shown once only
    wait_commands(backend)
    assert replays_page.sent == []


def test_b002_hud_part_hidden_shown_again_and_live_session_asks_first(replays_page, monkeypatch):  # noqa: F811
    from neopedal.ui.quick import dialogs

    backend = answered(replays_page, GAME_ANSWERS)
    backend.toggleHudComponent("chat")  # shown in GAME_ANSWERS: hidden by the page
    wait_commands(backend)
    replays_page.sent.clear()
    answered(replays_page, {**GAME_ANSWERS, "/rest/replay/isActive": False,
                            "/rest/hud": {"chat": False, "mfd": True, "speedo": False}})
    wait_commands(backend)
    assert replays_page.sent == [("POST", "/rest/hud/toggle/chat")]  # speedo hidden in game: left as it is
    # Live session: hidden only once confirmed
    asked: list[str] = []
    monkeypatch.setattr(dialogs, "confirm", lambda parent, title, text, action, on_result, **kwargs: asked.append(text))
    replays_page.sent.clear()
    backend.setHudShown(False)
    wait_commands(backend)
    assert asked and "session" in asked[0] and replays_page.sent == []


def test_b002_hud_hidden_shown_again_when_page_closed(replays_page):  # noqa: F811
    import time

    backend = answered(replays_page, GAME_ANSWERS)
    backend.setHudShown(False)
    wait_commands(backend)
    replays_page.sent.clear()
    backend.release_resources()  # page closed while the replay is open
    end = time.monotonic() + 5
    while replays_page.sent != SHOW_HUD and time.monotonic() < end:
        time.sleep(0.01)
    assert replays_page.sent == SHOW_HUD


# B-004: end of a copy wrote over a replay that took its name during the copy (renamed in the page, saved by game)
def test_b004_copy_never_writes_over_a_replay_named_meanwhile(tmp_path):
    from neopedal.ui.quick import replay_files

    game, downloads = tmp_path / "Replays", tmp_path / "Downloads"
    game.mkdir()
    downloads.mkdir()
    (game / "Spa R1 1.Vcr").write_bytes(b"game replay")
    (game / "My best race.Vcr").write_bytes(b"precious")
    source = downloads / "Spa R1 1.Vcr"
    source.write_bytes(b"z" * (replay_files.CHUNK_SIZE * 2))
    renamed: list[str] = []

    def progress(_value: float):
        if not renamed:  # during the copy: renamed in the page to the name the copy will take, game saves one too
            renamed.append(replay_files.rename_replay(str(game), "My best race", "Spa R1 1 (2)"))
            (game / "Spa R1 1 (2).Vcr").write_bytes(b"saved by game")

    result = replay_files.copy_replays([str(source)], str(game), progress)
    assert renamed == ["name already used"]  # name of the replay being copied refused
    assert (game / "My best race.Vcr").read_bytes() == b"precious"
    assert (game / "Spa R1 1 (2).Vcr").read_bytes() == b"saved by game"  # never written over
    assert result.added == ["Spa R1 1 (3)"] and (game / "Spa R1 1 (3).Vcr").stat().st_size == source.stat().st_size
    assert not list(game.glob("*.part"))


# B-005: on a drive without recycle bin (USB stick, network drive), "moved to the recycle bin" deleted replays for good
def test_b005_no_recycle_bin_asks_to_delete_for_good(replays_page, monkeypatch, tmp_path):  # noqa: F811
    from neopedal.ui.quick import dialogs, replay_files

    backend = page_of_replays(replays_page, tmp_path / "Replays", "AB")
    asked: list[tuple[str, str]] = []

    def confirm(parent, title, text, action, on_result, **kwargs):
        asked.append((text, action))
        on_result(True)

    monkeypatch.setattr(dialogs, "confirm", confirm)
    monkeypatch.setattr(replay_files, "QFile", SimpleNamespace(moveToTrash=lambda path: True))
    monkeypatch.setattr(replay_files, "recycle_bin", lambda folder: False)
    backend.deleteReplays("A")
    wait_requests(backend.request_trash)
    assert "for good" in asked[0][0] and "no recycle bin" in asked[0][0] and asked[0][1] == "Delete Permanently"
    assert backend.noticeText == "1 replay(s) deleted for good"
    monkeypatch.setattr(replay_files, "recycle_bin", lambda folder: True)  # usual drive: recycle bin as before
    backend.deleteReplays("B")
    wait_requests(backend.request_trash)
    assert "recycle bin?" in asked[1][0] and backend.noticeText == "1 replay(s) moved to the recycle bin"


@pytest.mark.skipif(sys.platform != "win32", reason="drive types of Windows")
def test_b005_recycle_bin_of_drives(tmp_path):
    from neopedal.ui.quick import replay_files

    assert replay_files.recycle_bin(str(tmp_path))  # fixed drive
    assert not replay_files.recycle_bin("//no-such-server/share/Replays")  # network share


# B-003: action of a replay taken as open from a stale state (page hidden, polling stopped, game left the replay) sent
# its focus & time to the game at once, without confirmation
def test_b003_action_on_stale_state_asks_and_opens_replay(replays_page, monkeypatch):  # noqa: F811
    from neopedal.ui.quick import dialogs
    from neopedal.ui.quick.replays_common import ReplayAction

    backend = answered(replays_page, GAME_ANSWERS)
    asked: list[str] = []
    monkeypatch.setattr(dialogs, "confirm", lambda parent, title, text, action, on_result, **kwargs: asked.append(text))
    backend.playing = "Bahrain R1"  # opened from the page, open in game (told by the answer just received)
    action = ReplayAction("Bahrain R1", 300.0, ("Kevin Ramirez",))
    replays_page.sent.clear()
    backend.watch("Bahrain R1", action)  # recent answer: done at once
    wait_commands(backend)
    assert not asked and ("PUT", "/rest/watch/replaytime/295") in replays_page.sent
    replays_page.sent.clear()
    backend.state_time -= 60  # page hidden for a minute: the game may have left the replay
    backend.watch("Bahrain R1", action)
    wait_commands(backend)
    assert asked and "Open replay" in asked[0] and replays_page.sent == []


# B-006: map of a replay drew its cars at positions read in shared memory, frozen during replays (another session's)
def test_b006_replay_map_never_uses_shared_memory(replays_page, monkeypatch):  # noqa: F811
    from tests.test_replay_map_motion import FakeReader

    backend = replays_page.backend
    reader = FakeReader([(7, 890.0, -241.0)])  # slot of the replay, position of another session
    monkeypatch.setattr(type(backend), "reader", staticmethod(lambda: reader))
    backend.setPanel(2)
    answered(replays_page, GAME_ANSWERS)  # replay open
    replays_page.resize(1400, 860)
    replays_page.show()
    for _ in range(10):
        QCoreApplication.processEvents()
    assert backend.gameState == "replay" and backend.map_center and backend._shown
    backend.read_live_positions()
    assert not backend.live_wanted() and backend.mapLive == {}


# B-007: one click on an incident in a live session sent the game to its replay, without confirmation
def test_b007_jump_in_live_session_asks_first(replays_page, monkeypatch):  # noqa: F811
    from neopedal.ui.quick import dialogs

    backend = answered(replays_page, {**GAME_ANSWERS, "/rest/replay/isActive": False})
    assert backend.gameState == "session"
    answers: list[bool] = [False]
    asked: list[str] = []

    def confirm(parent, title, text, action, on_result, **kwargs):
        asked.append(text)
        on_result(answers[0])

    monkeypatch.setattr(dialogs, "confirm", confirm)
    key = backend.incidentRows.rows[1]["key"]
    replays_page.sent.clear()
    backend.jumpTo(key, "")  # cancelled: the game stays live
    wait_commands(backend)
    assert asked and "session" in asked[0] and replays_page.sent == []
    answers[0] = True
    backend.jumpTo(key, "")
    wait_commands(backend)
    assert ("POST", "/rest/replay/toggleactive") in replays_page.sent


# B-008: replay of the live session showed live time & laps (standings stay live), lap steps never reached their lap,
# and the jump sent right after the replay opened could be ignored by the game
def test_b008_replay_of_live_session_time_and_laps_unknown(replays_page, monkeypatch):  # noqa: F811
    backend = answered(replays_page, GAME_ANSWERS)
    assert backend.replayTime > 0 and backend.cameraLap > 0  # replay of a recorded session: from standings
    backend.rewatching = True  # replay of the live session opened by a jump
    answered(replays_page, GAME_ANSWERS)
    assert backend.replayTime == -1 and backend.cameraLap == 0
    replays_page.sent.clear()
    backend.stepLap(1)
    wait_commands(backend)
    assert replays_page.sent == [] and backend.noticeError and "timeline" in backend.noticeText


def test_b008_live_replay_waits_before_taking_commands(monkeypatch):
    from neopedal.ui.quick import replays_common

    slept: list[float] = []
    monkeypatch.setattr(replays_common.time, "sleep", slept.append)
    active = iter([False, False, True])
    connection = SimpleNamespace(get=lambda resource: next(active), send=lambda *args: True)
    assert replays_common.enter_replay(connection)
    assert slept[-1] == replays_common.REPLAY_READY  # replay open: commands after a moment


# B-044: LMU answers nothing for minutes while it loads a replay from its menus: the open command timing out was taken
# as refused ("Game did not accept the command"), the replay opened from the page and its action forgotten
def test_b044_replay_loading_without_answer_is_not_refused(replays_page, monkeypatch):  # noqa: F811
    from neopedal.ui import game_rest
    from neopedal.ui.quick import dialogs
    from neopedal.ui.quick.replays_common import ReplayAction

    game = replays_page.game
    backend = answered(replays_page, {**GAME_ANSWERS, "/rest/replay/isActive": None})  # game in its menus
    monkeypatch.setattr(dialogs, "confirm", lambda parent, title, text, action, on_result, **kwargs: on_result(True))
    connect = game.connection

    def connection(*args, **kwargs):
        link = connect(*args, **kwargs)
        send = link.send

        def sending(method, resource, body=None):
            if resource.startswith("/rest/watch/play/"):  # loading: no answer
                send(method, resource, body)
                link.failed = True
                return False
            return send(method, resource, body)

        link.send = sending
        link.answered = True
        return link

    monkeypatch.setattr(game_rest, "GameConnection", connection)
    backend.watch("Bahrain R1", ReplayAction("Bahrain R1", 300.0, ("Kevin Ramirez",)))
    wait_commands(backend)
    assert not backend.noticeError and backend.openingReplay == "Bahrain R1"
    game.answers = {}  # still loading: no answer at all
    backend.refresh()
    wait_requests(backend.request_replays, backend.request_state)
    assert backend.openingReplay == "Bahrain R1" and backend.action is not None
    monkeypatch.setattr(game_rest, "GameConnection", connect)
    answered(replays_page, GAME_ANSWERS)  # replay loaded
    assert backend.playingReplay == "Bahrain R1"


# B-009: another replay opened in game while the page saw no menu (page hidden) kept the name, cars, laps & "back to
# live" of the former one; a replay never open in game stayed "opening" for good
def test_b009_other_replay_open_in_game_forgets_former_one(replays_page):  # noqa: F811
    backend = answered(replays_page, GAME_ANSWERS)
    backend.playing, backend.rewatching = "Bahrain R1", True
    backend.lap_starts = {7: {2: 100.0}}
    other = {**GAME_ANSWERS["/rest/watch/sessionInfo"], "trackName": "Bahrain International Circuit"}
    answered(replays_page, {**GAME_ANSWERS, "/rest/watch/sessionInfo": other})
    assert backend.gameState == "replay" and backend.playingReplay == "" and not backend.canGoLive
    assert 2 not in backend.lap_starts.get(7, {})


def test_b009_replay_never_open_no_longer_opening(replays_page, monkeypatch):  # noqa: F811
    import time

    backend = answered(replays_page, {**GAME_ANSWERS, "/rest/replay/isActive": None})
    backend.playing, backend.opening_until = "Bahrain R1", time.monotonic() + 100
    answered(replays_page, {**GAME_ANSWERS, "/rest/replay/isActive": None})
    assert backend.openingReplay == "Bahrain R1"
    backend.opening_until = time.monotonic() - 1  # given up
    answered(replays_page, {**GAME_ANSWERS, "/rest/replay/isActive": None})
    assert backend.openingReplay == ""


# B-011: page freed while hidden (unused a while, window minimized) during a copy: copy stopped, nothing told
def test_b011_page_kept_while_replays_are_copied(replays_page, monkeypatch):  # noqa: F811
    from neopedal.ui.app_tab_view import kept_when_hidden

    backend = replays_page.backend
    assert not kept_when_hidden(replays_page.page)
    backend.request_copy.busy = True  # copy running: never freed while hidden
    try:
        assert kept_when_hidden(replays_page.page)
    finally:
        backend.request_copy.busy = False


# B-012: protected replays of an unreadable settings file were lost without a word (written over by the next settings
# saved: bulk deletions could then trash them); "protected": null stopped the page from opening
def test_b012_unreadable_protections_kept_and_bulk_deletion_off(window, monkeypatch, tmp_path):  # noqa: F811
    from neopedal.ui.quick import dialogs, page_settings, replays_backend, replays_common

    monkeypatch.setattr(page_settings, "settings_path", lambda name: str(tmp_path / name))
    path = tmp_path / replays_common.SETTINGS_FILE
    path.write_text('{"protected": null}', encoding="utf-8")
    assert replays_common.read_protected() is None and (tmp_path / "game_replays.json.bad").exists()
    path.write_text('{"protected": ["A"', encoding="utf-8")  # cut while written
    assert replays_common.read_protected() is None and not path.exists()
    path.write_text('{"protected": ["A", 3]}', encoding="utf-8")
    assert replays_common.read_protected() == {"A"}
    path.write_text("{oops", encoding="utf-8")
    backend = replays_backend.GameReplaysBackend(window)
    assert backend.protections_lost and backend.protected == set()
    asked: list[str] = []
    monkeypatch.setattr(dialogs, "ask_number", lambda *args, **kwargs: asked.append(args[1]))
    backend.deleteOlderThan()
    backend.keepLatest()
    assert asked == [] and backend.noticeError and "game_replays.json.bad" in backend.noticeText
    backend.release_resources()


# B-018: every reload (page shown again, F5, a new file of another session) showed the same session again with its
# lists reset to the top and the chart animated again
def test_b018_reload_keeps_views_of_same_session(results_backend):
    from tests.test_race_results import PRACTICE_NAME, wait_until

    backend = results_backend
    backend.select(next(info.path for info in backend.sessions if info.path.endswith(PRACTICE_NAME)))
    assert wait_until(lambda: backend.shown_key.endswith(PRACTICE_NAME))
    resets: list[str] = []
    backend.classificationModel.modelReset.connect(lambda: resets.append("classification"))
    backend.eventModel.modelReset.connect(lambda: resets.append("events"))
    backend.chartChanged.connect(lambda: resets.append("chart"))
    backend.page_hidden()
    backend.page_shown()  # nothing changed on disk
    assert wait_until(lambda: not backend.loading)
    for _ in range(30):
        QCoreApplication.processEvents()
    assert resets == [] and backend.shown_key.endswith(PRACTICE_NAME)


@pytest.fixture
def results_backend(results_folder):  # noqa: F811
    from PySide6.QtCore import QEvent

    from neopedal.ui.quick.results_backend import RaceResultsBackend
    from tests.test_race_results import wait_until

    backend = RaceResultsBackend()
    backend.page_shown()
    assert wait_until(lambda: backend.loaded_once)
    yield backend
    backend.release()
    backend.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


# B-019: with the newest session shown, a reload kept the session object shown: the replay the game saves after the
# results file never got its Watch Replay button & tab, a rewritten file was shown stale
def test_b019_newest_session_read_again_with_its_new_replay(tmp_path, ui_env, monkeypatch):
    from PySide6.QtCore import QEvent

    from neopedal.process import results_file
    from neopedal.ui.quick.results_backend import RaceResultsBackend
    from tests.test_race_results import PRACTICE_XML, RACE_NAME, RACE_XML, wait_until, write_results

    root = tmp_path / "Le Mans Ultimate"
    folder = root / "UserData" / "Log" / "Results"
    write_results(folder, {RACE_NAME: RACE_XML, "2026_09_21_18_00_00-10P1.xml": PRACTICE_XML.format(laps=5)})
    (root / "UserData" / "Replays").mkdir(parents=True)
    monkeypatch.setattr(results_file, "find_results_folders", lambda libraries=None: {"LMU": str(folder)})
    page = RaceResultsBackend()
    try:
        page.page_shown()
        assert wait_until(lambda: page.loaded_once)
        assert page.selectedKey.endswith(RACE_NAME) and page.sessionHeader["replay"] == ""  # newest, no replay yet
        replay = root / "UserData" / "Replays" / "24 Heures du Mans R1 1.Vcr"  # saved by the game once session left
        replay.write_bytes(b"vcr")
        written = os.path.getmtime(folder / RACE_NAME)
        os.utime(replay, (written + 60, written + 60))
        page.reload()  # F5 (replay folder not watched)
        assert wait_until(lambda: page.sessionHeader.get("replay") == "24 Heures du Mans R1 1")
    finally:
        page.release()
        page.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


# B-021: lap without recorded file (invalid lap, not saved) took the file of the next lap of about the same time, that
# lap then had no telemetry link
def test_b021_telemetry_link_never_takes_file_of_next_lap(tmp_path):
    from neopedal.ui.quick.results_telemetry import lap_folders, recorded_laps
    from tests.test_ui_audit_2026_10_29_analysis_results import START, entry, lap, lap_file, session

    laps = [lap(1, 75.40, start=0.0), lap(2, 75.43, start=75.40), lap(3, 75.42, start=150.83), lap(4, 75.90, start=226.25)]
    player = entry("Me", laps, player=True)
    result = session([player])
    folder = tmp_path / lap_folders(result, player)[0]
    folder.mkdir()
    files = {item.number: lap_file(folder, START + item.start + item.time + 3, item.number, item.time)
             for item in laps if item.number != 2}  # lap 2 invalid: not saved by the recorder
    assert recorded_laps(str(tmp_path), result, player) == files  # lap 2 none, lap 3 its own file


# B-022: contacts with objects other than "Immovable" (Post, Sign, Cone, Wheel, Wing) were counted as car contacts
def test_b022_object_contacts_never_counted_as_car_contacts():
    from neopedal.process import results_file as rf
    from tests.test_race_results import RACE_NAME, RACE_XML

    objects = "\n".join(f'<Incident et="{400 + index * 10}.0">Carl Slow(2) reported contact (50.00) with {name}</Incident>'
                        for index, name in enumerate(("Post", "Sign", "Cone", "Wheel", "Wing")))
    xml = RACE_XML.replace('<Incident et="300.0">', f'{objects}\n<Incident et="300.0">', 1)
    result = rf.parse_results(xml.encode("utf-8"), RACE_NAME, ["alice driver"])
    contacts = [event for event in result.events if event.kind == "contact" and event.driver == "Carl Slow"]
    assert len(contacts) == 6 and {event.other for event in contacts} == {rf.IMMOVABLE}
    assert "with Post" in contacts[1].text or any("with Post" in event.text for event in contacts)
    counts = rf.contact_counts(result.events)
    assert counts["Carl Slow"] == (0, 6) and not set(counts) & {"Post", "Sign", "Cone", "Wheel", "Wing"}


# B-023: race restarts & races left before the start (one results file each, no lap) counted as races, and clean ones
def test_b023_race_record_leaves_out_races_without_lap():
    from neopedal.process import results_file as rf
    from neopedal.process import results_index as ri

    def race(laps: int, status: str = rf.FINISHED, position: int = 2):
        return ri.ResultSummary._make([None] * len(ri.ResultSummary._fields))._replace(
            kind="Race", status=status, class_position=position, contacts=0, penalties=0, laps=laps)

    record = ri.race_record([race(12), race(0, "None", 5), race(0, "DNF", 0)])
    assert record.races == 1 and record.clean == 1 and record.podiums == 1


# B-013: replay renamed was no longer selected (selection kept its former name, dropped once the list was updated)
def test_b013_renamed_replay_stays_selected(replays_page, tmp_path):  # noqa: F811
    backend = page_of_replays(replays_page, tmp_path / "Replays", "ABC")
    backend.selectReplay("B")
    assert backend.rename_replay("B", "B2")
    assert backend.checked == {"B2"} and backend.selectedReplay == "B2"
    assert [(row["key"], row["checked"]) for row in backend.replayRows.rows if row["checked"]] == [("B2", True)]


# B-014: renaming to the name of a replay still listed (file deleted outside the app, list not asked again) made two
# rows of the same name, actions on that row acting on both
def test_b014_rename_refuses_name_still_listed(replays_page, tmp_path):  # noqa: F811
    backend = page_of_replays(replays_page, tmp_path / "Replays", "ABC")
    (tmp_path / "Replays" / "A.Vcr").unlink()  # deleted outside the app: still listed
    assert not backend.rename_replay("B", "a")
    assert backend.noticeError and "name already used" in backend.noticeText
    assert sorted(replay.name for replay in backend.replays) == ["A", "B", "C"]


# B-015: rename accepted Windows device names (CON, NUL, COM1...), doubled a typed extension, and raised on a NUL
def test_b015_rename_refuses_device_names_and_drops_typed_extension(tmp_path):
    from neopedal.ui.quick import replay_files

    (tmp_path / "A.Vcr").write_bytes(b"replay")
    for name in ("CON", "nul", "COM1", "Lpt9", "NUL.txt", "conin$", "x\x00y", "tab\there"):
        assert replay_files.rename_replay(str(tmp_path), "A", name) == "invalid name", name
    assert replay_files.rename_replay(str(tmp_path), "A", "Best race.vcr") == ""
    assert sorted(path.name for path in tmp_path.iterdir()) == ["Best race.Vcr"]
    assert replay_files.rename_replay(str(tmp_path), "Best race", "Console") == ""  # only the device names


# B-016: replay left half copied (app ended during a copy: <name>.Vcr.part) never cleaned, never even seen
def test_b016_half_copied_replays_cleaned_with_temporary_files(tmp_path):
    from neopedal.ui.quick import replay_files

    (tmp_path / "Spa R1 1.Vcr.part").write_bytes(b"half")
    (tmp_path / "_vcr12.tmp").write_bytes(b"tmp")
    (tmp_path / "Spa R1 2.Vcr").write_bytes(b"replay")
    found = replay_files.temp_files(str(tmp_path), now=4e9)
    assert sorted(os.path.basename(path) for path in found) == ["Spa R1 1.Vcr.part", "_vcr12.tmp"]
    assert replay_files.temp_files(str(tmp_path)) == []  # just written: maybe being copied or recorded


# B-017: file actions used the replay folder of the page for every replay, not the folder the game told for it
def test_b017_replay_file_in_folder_told_by_game(replays_page, tmp_path):  # noqa: F811
    from neopedal.ui.quick.replays_backend import GameReplay

    backend = page_of_replays(replays_page, tmp_path / "Replays", "AB")
    other = tmp_path / "Other"
    other.mkdir()
    (other / "C.Vcr").write_bytes(b"replay")
    replay = GameReplay(5, "C", "", "", "", 1.0, 6, "", str(other))
    assert backend.file_of(replay) == os.path.join(str(other), "C.Vcr")
    assert backend.file_of(replay._replace(folder="")) == os.path.join(backend.replay_folder(), "C.Vcr")
    backend.replays = [*backend.replays, replay]
    assert backend.rename_replay("C", "C2") and (other / "C2.Vcr").exists()


# B-020: results file read while the game still wrote it (Windows tells only its creation to the watched folder):
# never read again, the session never showed
def test_b020_file_read_while_written_read_again(results_backend, results_folder):  # noqa: F811
    from tests.test_race_results import RACE_XML, wait_until

    backend = results_backend
    count = backend.sessionCount
    path = results_folder / "2026_09_22_20_00_00-15R1.xml"
    text = RACE_XML.replace("1790", "1791")
    half = len(text) // 2
    with open(path, "w", encoding="utf-8") as file:  # game writing it: first half
        file.write(text[:half])
        file.flush()
        backend.reload()
        assert wait_until(lambda: not backend.loading)
        end = time.monotonic() + 3  # reload of the folder event of its creation over too
        while time.monotonic() < end:
            QCoreApplication.processEvents()
            time.sleep(0.01)
        assert backend.sessionCount == count  # unreadable yet
        file.write(text[half:])  # written to the end, same file open: no folder event
    assert wait_until(lambda: backend.sessionCount == count + 1)


# B-024: laps this client did not see (online session joined later) read as position 105 & compound "N/A"
def test_b024_unseen_laps_have_no_position_nor_compound():
    from neopedal.process import results_file as rf
    from tests.test_race_results import RACE_NAME, RACE_XML

    seen = '<Lap num="1" p="1" et="100.0" s1="30.0" s2="40.0" s3="30.5" topspeed="300.5" fcompound="0,Medium"'
    unseen = '<Lap num="1" p="105" et="--.---" s1="30.0" s2="40.0" s3="30.5" topspeed="300.5" fcompound="15,N/A"'
    assert seen in RACE_XML
    result = rf.parse_results(RACE_XML.replace(seen, unseen, 1).encode("utf-8"), RACE_NAME)
    lap = next(entry for entry in result.entries if entry.laps and entry.laps[0].number == 1 and
               entry.laps[0].position != 2).laps[0]
    assert lap.position == 0 and lap.compound == ""


# B-025: notices of penalties served (no Driver attribute) listed and counted as penalties ("" driver)
def test_b025_served_penalty_notices_not_penalties():
    from neopedal.process import results_file as rf
    from tests.test_race_results import RACE_NAME, RACE_XML

    notice = '<Penalty ID="1" et="420.0">Bob Racer served 1st Stop/Go penalty</Penalty>\n'
    xml = RACE_XML.replace("<Penalty Driver=", notice + "<Penalty Driver=", 1)
    result = rf.parse_results(xml.encode("utf-8"), RACE_NAME)
    penalties = [event for event in result.events if event.kind == "penalty"]
    assert len(penalties) == 1 and penalties[0].driver == "Bob Racer"
    assert rf.penalty_counts(result.events) == {"Bob Racer": 1}


# B-026: track limits points of "no further action" warnings left out (points of a driver 0 instead of 2.5)
def test_b026_track_limits_points_count_no_further_action():
    from neopedal.process import results_file as rf
    from neopedal.ui.quick import results_backend as rb
    from tests.test_race_results import RACE_NAME, RACE_XML

    warning = ('<TrackLimits Driver="Alice Driver" ID="0" Lap="3" WarningPoints="2.5" CurrentPoints="2.5" '
               'Resolution="7" et="500.0">Over Limit</TrackLimits>\n')
    xml = RACE_XML.replace("<TrackLimits Driver=", warning + "<TrackLimits Driver=", 1)
    result = rf.parse_results(xml.encode("utf-8"), RACE_NAME)
    assert rf.track_limit_points(result.events)["Alice Driver"] == 2.5
    listed = rb.merged_contacts(result.events)
    assert not [event for event in listed if event.driver == "Alice Driver" and "Over Limit" in event.text]


# B-027: track limits written again after the penalty they gave (same time, not in a row) listed twice
def test_b027_track_limits_repeated_around_penalty_listed_once():
    from neopedal.process import results_file as rf
    from tests.test_race_results import RACE_NAME, RACE_XML

    limit = ('<TrackLimits Driver="Carl Slow" ID="2" Lap="3" WarningPoints="1" CurrentPoints="3" Resolution="1" '
             'et="600.0">Penalty given</TrackLimits>\n')
    penalty = ('<Penalty Driver="Carl Slow" ID="2" Penalty="Drive Thru" Time="0" Laps="3" Reason="Track Limits" '
               'et="600.0">Carl Slow received Drive Thru penalty for Track Limits</Penalty>\n')
    xml = RACE_XML.replace("<TrackLimits Driver=", limit + penalty + limit + "<TrackLimits Driver=", 1)
    result = rf.parse_results(xml.encode("utf-8"), RACE_NAME)
    assert [event.kind for event in result.events if event.time == 600.0] == ["track_limits", "penalty"]


# B-028: race time a fraction of a millisecond below a whole minute shown as "59:60.000"
def test_b028_race_time_never_shows_60_seconds():
    from neopedal.process.results_text import race_time_text

    assert race_time_text(3599.9996) == "1:00:00.000"
    assert race_time_text(59.9996) == "1:00.000"
    assert race_time_text(83.4561) == "1:23.456"


# B-029: another name on the untimed lap 1 only (practice, qualifying) shown as a co-driver of the player's car
def test_b029_no_phantom_driver_on_untimed_first_lap():
    from neopedal.process import results_file as rf
    from neopedal.process.results_text import driver_names
    from tests.test_race_results import PRACTICE_NAME, PRACTICE_XML

    swaps = ('<Swap startLap="1" endLap="1">Someone Else</Swap>\n<Swap startLap="2" endLap="5">Offline Player</Swap>\n'
             '<Lap num="1" p="2" et="10.0">--.----</Lap>\n<Lap num="2" p="2" et="120.0">107.5000</Lap>\n')
    xml = PRACTICE_XML.format(laps=5).replace("<Name>Offline Player</Name>", "<Name>Offline Player</Name>\n" + swaps)
    player = rf.parse_results(xml.encode("utf-8"), PRACTICE_NAME, ["offline player"]).player_entry
    assert driver_names(player) == ["Offline Player"]
    team = xml.replace("--.----", "110.2000")  # timed first lap: a real stint, kept
    assert driver_names(rf.parse_results(team.encode("utf-8"), PRACTICE_NAME, ["offline player"]).player_entry) == [
        "Someone Else", "Offline Player"]


# B-030: texts written by LMU never translated ("Drive Thru", "Disqualify", reasons), reason cut on " for " of names
def test_b030_game_texts_of_penalties_translated(ui_env):
    from neopedal import i18n
    from neopedal.process import results_file as rf
    from neopedal.process.results_text import game_text
    from tests.test_race_results import RACE_NAME, RACE_XML

    penalty = ('<Penalty Driver="Ford for Speed" ID="3" Penalty="Drive Thru" Time="0" Laps="3" Reason="Speeding" '
               'et="610.0">Ford for Speed received Drive Thru penalty for Speeding. Result: penalties=1</Penalty>\n')
    xml = RACE_XML.replace("<Penalty Driver=", penalty + "<Penalty Driver=", 1)
    event = next(event for event in rf.parse_results(xml.encode("utf-8"), RACE_NAME).events if event.time == 610.0)
    assert (event.other, event.reason) == ("Drive Thru", "Speeding")
    assert game_text("Drive Thru") == "Drive-through" and game_text("Disqualify") == "Disqualified from the session"
    i18n.set_language("Français")
    try:
        assert game_text("Speeding") == "Excès de vitesse" and game_text("Disqualify") == "Disqualifié de la session"
        assert game_text("Exceeded energy allowance limit.") == "Dépassement de l'énergie allouée"
    finally:
        i18n.set_language("English")


# B-031: online session where no driver has a profile name (watched as spectator): its only human taken as the player
def test_b031_spectated_online_session_has_no_player():
    from neopedal.process import results_file as rf
    from tests.test_race_results import RACE_NAME, RACE_XML

    one_human = RACE_XML.replace("<isPlayer>1</isPlayer>", "<isPlayer>0</isPlayer>", 1)  # only one human left
    online = rf.parse_results(one_human.encode("utf-8"), RACE_NAME, ["someone else"])
    assert online.setting == "Multiplayer" and online.player_entry is None
    offline = one_human.replace("<Setting>Multiplayer</Setting>", "<Setting>Race Weekend</Setting>")
    assert rf.parse_results(offline.encode("utf-8"), RACE_NAME, ["someone else"]).player_entry is not None
    assert rf.parse_results(one_human.encode("utf-8"), RACE_NAME).player_entry is not None  # no profile name known


# B-032: cars without status ("None": disconnected, not started) of a race others finished shown classified, with a gap
def test_b032_cars_without_status_not_classified(ui_env):
    from neopedal.process import results_file as rf
    from neopedal.process.results_text import classified, entry_gap
    from tests.test_race_results import RACE_NAME, RACE_XML

    result = rf.parse_results(RACE_XML.encode("utf-8"), RACE_NAME)
    leader = result.entries[0]
    assert leader.status == rf.FINISHED
    gone = result.entries[1]._replace(status="None")
    assert not classified(result, gone) and entry_gap(result, gone, leader, False) == ("Not classified", "dim")
    nobody = result._replace(entries=tuple(entry._replace(status="None") for entry in result.entries))
    assert classified(nobody, gone)  # race left before anyone finished: cars still running


# B-033: track logos fetched while the page was hidden never shown in the sessions list
def test_b033_logos_fetched_while_hidden_shown(results_backend, monkeypatch):
    from neopedal.ui.quick import game_pictures
    from tests.test_race_results import wait_until

    backend = results_backend
    monkeypatch.setattr(type(backend.logos), "track", lambda self, *names: "file:///logo.png")  # made meanwhile
    backend.page_hidden()
    game_pictures.notifier().changed.emit()  # told while hidden
    backend.page_shown()
    assert wait_until(lambda: not backend.loading)
    assert all(row["trackLogo"] == "file:///logo.png" for row in backend.sessionModel.rows)


# B-034: session asked from another page (hidden by the list filters): filters cleared for it, then saved cleared
def test_b034_session_asked_keeps_saved_filters(results_backend, results_folder):  # noqa: F811
    from neopedal.ui.quick.results_backend import load_page_settings
    from tests.test_race_results import EMPTY_NAME

    backend = results_backend
    backend.setKindFilter(3)  # races only, sessions without laps hidden (default)
    backend.setTab(2)  # events: Show Results goes back to classification (setting saved)
    backend.showResults(os.path.join(str(results_folder), EMPTY_NAME))  # Driver Stats: practice without lap
    backend.page_file.flush()
    saved = load_page_settings()
    assert (saved["session_kind"], saved["hide_empty"]) == ("Race", True)
    backend.setHideEmpty(True)  # changed by the user again: saved as shown
    backend.page_file.flush()
    assert (load_page_settings()["session_kind"], load_page_settings()["hide_empty"]) == ("", True)


# B-035: lap saved in the hour repeated when daylight saving time ends: its local file name read an hour off, no link
def test_b035_lap_saved_in_repeated_hour_linked(tmp_path, monkeypatch):
    from neopedal.ui.quick import results_telemetry
    from neopedal.ui.quick.results_telemetry import lap_folders, recorded_laps
    from tests.test_ui_audit_2026_10_29_analysis_results import START, entry, lap, lap_file, session

    first = lap(1, 103.2, start=0.0)
    player = entry("Me", [first], player=True)
    result = session([player])
    folder = tmp_path / lap_folders(result, player)[0]
    folder.mkdir()
    end = START + first.start + first.time
    named = end - 3600 + 2  # local name read as the first of the two same hours: an hour before the lap end
    path = lap_file(folder, named, 1, 103.2)
    real = time.localtime
    repeated = named + 1800  # from there local clock shows the same hour again (fake time zone, daylight saving end)
    monkeypatch.setattr(results_telemetry.time, "localtime",
                        lambda seconds=None: real(seconds - 3600 if seconds is not None and seconds >= repeated
                                                  else seconds))
    assert recorded_laps(str(tmp_path), result, player) == {1: path}


# B-036 (follow-up of BUG-032): an empty track map answer (track still loading) was taken as the map: never asked
# again for that track, map panel empty; F5 did not ask it again either
def test_b036_empty_track_map_asked_again(replays_page):  # noqa: F811
    backend = replays_page.backend
    backend.setPanel(2)
    answered(replays_page, {**GAME_ANSWERS, "/rest/watch/trackmap": []})  # loading: empty list
    assert not backend.map_center and backend.map_track is None  # not taken as the map
    answered(replays_page, GAME_ANSWERS)
    assert backend.map_center  # asked again, map shown
    backend.map_track, backend.map_center = "Circuit de la Sarthe", []  # given up (MAP_TRIES answers missed)
    backend.refresh()  # F5
    wait_requests(backend.request_replays, backend.request_state)
    assert backend.map_center


# B-037: replay rate measured across a jump: +40 s shown as "40x", playhead running off until the next answer
def test_b037_rate_kept_across_a_jump(replays_page):  # noqa: F811
    backend = answered(replays_page, GAME_ANSWERS)
    backend.replay_rate, backend.replay_time = 1.0, 10.0  # playing at 1x, far from the time answered next
    backend.time_received -= 1.0  # last answer a second ago (rate measured from either)
    if hasattr(backend, "_answered"):
        backend._answered -= 1.0
    backend.seek(1500.0)
    wait_commands(backend)
    backend.refresh_state()  # page not shown: state asked by the test once the jump is done
    wait_requests(backend.request_state)
    assert backend.replayTime > 1000 and backend.replayRate == 1.0  # not the jump over a second ("1500x")
